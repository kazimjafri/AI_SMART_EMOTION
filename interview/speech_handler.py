# ===========================
# interview/speech_handler.py
# Browser-based Mic Recording (WebRTC) · Speech-to-Text · Answer Evaluation
# ===========================

import os
import json
import threading
from typing import List
import numpy as np
import av
import streamlit as st
import speech_recognition as sr
from streamlit_webrtc import AudioProcessorBase


@st.cache_resource
def get_whisper_model():
    """
    Load the faster-whisper model ONCE and cache it across reruns.
    'base' is a good speed/accuracy tradeoff for interview answers (short clips).
    Use 'small' or 'medium' for noticeably better accuracy if your machine can handle it.
    """
    from faster_whisper import WhisperModel
    return WhisperModel("base", device="cpu", compute_type="int8")


# ───────────────────────────────────────────
# BROWSER AUDIO RECORDER
# Receives the candidate's mic audio frames from their browser
# over WebRTC (same connection as the camera). Buffers PCM only
# while "recording" is True (toggled by Start/Stop buttons in
# interview_engine.py), then hands back an sr.AudioData object
# for Google STT — no server-side microphone access involved.
#
# Uses recv_queued() (batch) instead of recv() (one-at-a-time):
# recv() drops frames if processing falls even slightly behind
# real-time (e.g. while the video thread is busy running DeepFace),
# which was cutting words out of the recording. recv_queued() gets
# ALL buffered frames at once, so nothing is silently lost.
# ───────────────────────────────────────────

class BrowserAudioRecorder(AudioProcessorBase):
    def __init__(self):
        self.lock = threading.Lock()
        self.recording = False
        self.buffer = bytearray()
        self.sample_rate = 16000
        self._resampler = av.AudioResampler(format="s16", layout="mono", rate=self.sample_rate)

    async def recv_queued(self, frames: List[av.AudioFrame]) -> List[av.AudioFrame]:
        if self.recording:
            for frame in frames:
                try:
                    resampled = self._resampler.resample(frame)
                    if not isinstance(resampled, list):
                        resampled = [resampled]
                    for rf in resampled:
                        pcm = rf.to_ndarray().astype(np.int16).flatten()
                        with self.lock:
                            self.buffer.extend(pcm.tobytes())
                except Exception:
                    pass
        return frames

    def start_recording(self):
        with self.lock:
            self.buffer = bytearray()
            self.recording = True

    def stop_recording(self) -> "sr.AudioData | None":
        with self.lock:
            self.recording = False
            data = bytes(self.buffer)
            self.buffer = bytearray()
        if not data:
            return None
        return sr.AudioData(data, self.sample_rate, 2)  # 16-bit PCM = sample_width 2

    def is_recording(self) -> bool:
        with self.lock:
            return self.recording


# ───────────────────────────────────────────
# SPEECH → TEXT
# ───────────────────────────────────────────

def transcribe_audio_bytes(wav_bytes: bytes) -> str:
    """
    Transcribe raw WAV audio bytes (e.g. straight from st.audio_input) using
    faster-whisper. This bypasses the WebRTC per-frame audio pipeline entirely —
    the browser records the full clip natively and hands it over as one complete
    file, so there's no frame-drop/CPU-contention risk during recording.
    Falls back to Google Web Speech if Whisper fails.
    """
    try:
        import io
        model = get_whisper_model()
        buf = io.BytesIO(wav_bytes)
        segments, _ = model.transcribe(buf, language="en", vad_filter=True)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        if text:
            return text
        raise ValueError("Empty Whisper transcript")
    except Exception:
        try:
            import io
            recognizer = sr.Recognizer()
            with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
                audio_data = recognizer.record(source)
            return recognizer.recognize_google(audio_data, language="en-US").strip()
        except Exception:
            return ""


def transcribe_audio(audio_data: sr.AudioData) -> str:
    """
    Convert recorded audio to text.
    Primary: faster-whisper (local, high accuracy — handles accents/noise well).
    Fallback: Google Web Speech API (if Whisper isn't installed/fails).
    """
    try:
        import io
        import wave

        # sr.AudioData -> temp WAV bytes (whisper needs a file-like/array input)
        wav_bytes = audio_data.get_wav_data()
        buf = io.BytesIO(wav_bytes)

        model = get_whisper_model()
        segments, _ = model.transcribe(buf, language="en", vad_filter=True)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        if text:
            return text
        raise ValueError("Empty Whisper transcript")

    except Exception:
        # ── Fallback: Google Web Speech (only if Whisper unavailable/fails) ──
        recognizer = sr.Recognizer()
        try:
            text = recognizer.recognize_google(audio_data, language="en-US")
            return text.strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError:
            return ""
        except Exception:
            return ""


# ───────────────────────────────────────────
# ANSWER EVALUATION  (Gemini under the hood)
# ───────────────────────────────────────────

def _load_gemini_api_keys() -> list:
    """
    Load one or more Gemini API keys from .env. Supports:
      GEMINI_API_KEY=key1                      (single)
      GEMINI_API_KEY=key1,key2,key3             (comma-separated)
      GEMINI_API_KEY_1=key1 / GEMINI_API_KEY_2=key2 / ...   (numbered)
    IMPORTANT: each key must belong to a DIFFERENT Google Cloud project to
    actually get separate quota — Google's free-tier quota is per-project,
    not per-key, so multiple keys in the SAME project share one quota pool.
    """
    keys = []
    single = os.environ.get("GEMINI_API_KEY", "")
    if single:
        keys.extend([k.strip() for k in single.split(",") if k.strip()])
    i = 1
    while True:
        k = os.environ.get(f"GEMINI_API_KEY_{i}", "")
        if not k:
            break
        keys.append(k.strip())
        i += 1
    seen, unique_keys = set(), []
    for k in keys:
        if k not in seen:
            unique_keys.append(k); seen.add(k)
    return unique_keys


def _is_quota_error(e: Exception) -> bool:
    s = str(e).lower()
    return "429" in str(e) or "quota" in s or "rate limit" in s or "resourceexhausted" in s


def _call_gemini_with_rotation(prompt: str) -> str:
    """
    Try each configured Gemini API key in turn. On a quota/rate-limit error,
    move to the next key automatically. Raises the last error if every key
    is exhausted (caller should catch this and fall back to heuristics).
    """
    import google.generativeai as genai_sdk

    keys = _load_gemini_api_keys()
    if not keys:
        raise ValueError("No Gemini API key configured in .env")

    last_err = None
    for idx, key in enumerate(keys):
        try:
            genai_sdk.configure(api_key=key)
            model = genai_sdk.GenerativeModel("gemini-2.5-flash-lite")
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            last_err = e
            if _is_quota_error(e) and idx < len(keys) - 1:
                print(f"[gemini] Key #{idx+1} hit quota/rate limit, trying key #{idx+2}...")
                continue
            raise
    raise last_err


def _strip_json_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def evaluate_interview_batch(
    questions: list,
    answers: dict,
    job_title: str = "",
    company: str = "",
) -> dict:
    """
    Score ALL answers of the interview in ONE Gemini call instead of one
    call per question — this is much friendlier to the free-tier daily
    request quota (e.g. a 10-question interview now costs 1 request
    instead of 10).
    Returns: {question_index: {score, feedback, correct, word_count, keywords_hit, scored_by}}
    Falls back to per-question evaluate_answer() (which has its own
    heuristic fallback) if the batch call fails for any reason.
    """
    total_q = len(questions)
    if total_q == 0:
        return {}

    qa_blocks = []
    for i, q_obj in enumerate(questions):
        answer = answers.get(i, "").strip()
        qa_blocks.append(
            f"--- Question {i+1} [{q_obj.get('category','General')}] "
            f"(expected keywords/themes: {', '.join(q_obj.get('expected_keywords', [])) or 'N/A'}) ---\n"
            f"Question: {q_obj.get('question','')}\n"
            f"Candidate's spoken answer: {answer or '(No answer was provided)'}"
        )

    prompt = f"""You are a strict but fair interview evaluator. Evaluate ALL {total_q} spoken interview answers below in one pass.

Role being interviewed for: {job_title or "General"}
Company: {company or "N/A"}

For each answer, evaluate: Relevance, Depth (sufficient for its category), Clarity, Accuracy.
Note: these are spoken answers, so minor grammar issues are acceptable. Score PURELY on how well the
answer actually addresses and demonstrates knowledge of the question — NOT on how long the answer is.
A short, precise, correct answer should score higher than a long, vague, or padded one.
If an answer says "(No answer was provided)", score it 0 with correct=false.

{chr(10).join(qa_blocks)}

Respond ONLY with a valid JSON array (no markdown, no extra text), with exactly {total_q} objects
in the SAME order as the questions above:
[
  {{"score": <0-100>, "feedback": "<2 sentences of constructive feedback>", "correct": <true if score>=60>}},
  ...
]"""

    try:
        raw = _call_gemini_with_rotation(prompt)
        parsed = json.loads(_strip_json_fences(raw))
        if not isinstance(parsed, list) or len(parsed) != total_q:
            raise ValueError(f"Expected {total_q} results, got {len(parsed) if isinstance(parsed, list) else 'non-list'}")

        results = {}
        for i, q_obj in enumerate(questions):
            answer = answers.get(i, "").strip()
            item = parsed[i]
            score = max(0, min(100, int(item.get("score", 0))))
            expected_keywords = q_obj.get("expected_keywords", [])
            results[i] = {
                "score":        score,
                "feedback":     item.get("feedback", "—") if answer else "No answer was provided.",
                "correct":      bool(item.get("correct", score >= 60)),
                "word_count":   len(answer.split()) if answer else 0,
                "keywords_hit": sum(1 for kw in expected_keywords if kw.lower() in answer.lower()) if (expected_keywords and answer) else 0,
                "scored_by":    "gemini_batch",
            }
        return results

    except Exception as e:
        print(f"[evaluate_interview_batch] Batch scoring failed, falling back to per-question scoring: {e}")
        # ── Fallback: score each question individually (still tries Gemini + key rotation per question) ──
        results = {}
        for i, q_obj in enumerate(questions):
            results[i] = evaluate_answer(
                question=q_obj.get("question", ""),
                answer=answers.get(i, ""),
                category=q_obj.get("category", "General"),
                expected_keywords=q_obj.get("expected_keywords", []),
                job_title=job_title,
                company=company,
            )
        return results


def evaluate_answer(
    question: str,
    answer: str,
    category: str,
    expected_keywords: list,
    job_title: str = "",
    company: str = "",
) -> dict:
    """
    Score one spoken answer 0-100.
    Returns: {score, feedback, correct, word_count, keywords_hit}
    Uses Gemini API (with multi-key rotation); falls back to heuristic scoring if unavailable.
    """
    if not answer.strip():
        return {
            "score":        0,
            "feedback":     "No answer was provided.",
            "correct":      False,
            "word_count":   0,
            "keywords_hit": 0,
            "scored_by":    "no_answer",
        }

    word_count = len(answer.split())

    prompt = f"""You are a strict but fair interview evaluator assessing a spoken answer.

Role being interviewed for: {job_title or "General"}
Company: {company or "N/A"}
Question: {question}
Category: {category}
Expected keywords / themes: {', '.join(expected_keywords) if expected_keywords else 'N/A'}
Candidate's spoken answer: {answer}

Evaluate on:
- Relevance (does it address the question?)
- Depth (sufficient detail for {category} level?)
- Clarity (well-structured and coherent?)
- Accuracy (technically/factually correct?)

Note: This was a spoken answer, so minor grammar issues are acceptable. Score PURELY on how well the
answer addresses and demonstrates knowledge of the question — NOT on how long it is.

Respond ONLY with valid JSON (no markdown, no extra text):
{{"score": <0-100>, "feedback": "<2 sentences of constructive feedback>", "correct": <true if score>=60>}}"""

    try:
        raw = _call_gemini_with_rotation(prompt)
        result = json.loads(_strip_json_fences(raw))
        score = max(0, min(100, int(result.get("score", 50))))

        return {
            "score":        score,
            "feedback":     result.get("feedback", "Good attempt."),
            "correct":      bool(result.get("correct", score >= 60)),
            "word_count":   word_count,
            "keywords_hit": sum(
                1 for kw in expected_keywords
                if kw.lower() in answer.lower()
            ) if expected_keywords else 0,
            "scored_by":    "gemini",
        }

    except Exception as e:
        print(f"[evaluate_answer] Gemini scoring failed, using heuristic fallback: {e}")
        # ── Heuristic fallback ──
        kw_hits = sum(
            1 for kw in expected_keywords
            if kw.lower() in answer.lower()
        ) if expected_keywords else 0

        base   = min(85, 35 + word_count * 0.9 + kw_hits * 8)
        score  = int(min(95, base))
        correct = score >= 60

        return {
            "score":        score,
            "feedback":     (
                "Good spoken response with reasonable depth."
                if correct else
                "Response could use more detail and specific examples."
            ),
            "correct":      correct,
            "word_count":   word_count,
            "keywords_hit": kw_hits,
            "scored_by":    "heuristic_fallback",
        }


# ───────────────────────────────────────────
# SPEECH CLARITY SCORE  (basic heuristic)
# ───────────────────────────────────────────

def compute_speech_clarity(
    answer_text: str,
    word_count: int,
    recording_seconds: float = 0,
) -> dict:
    """
    Estimate speech clarity from transcription quality.
    Returns: {clarity_score, tempo_wpm, assessment}
    """
    if not answer_text or word_count == 0:
        return {"clarity_score": 0, "tempo_wpm": 0, "assessment": "No speech detected"}

    # WPM calculation
    tempo_wpm = 0
    if recording_seconds and recording_seconds > 0:
        tempo_wpm = int((word_count / recording_seconds) * 60)

    # Sentence structure score
    sentences       = [s.strip() for s in answer_text.split('.') if s.strip()]
    avg_sent_length = word_count / max(len(sentences), 1)

    # Ideal: 10-20 words/sentence, 100-160 wpm
    structure_score = min(100, max(0, 100 - abs(avg_sent_length - 15) * 3))
    length_score    = min(100, word_count * 2)   # longer = more content

    clarity_score = int((structure_score * 0.4 + length_score * 0.6))
    clarity_score = max(10, min(98, clarity_score))

    if clarity_score >= 80:
        assessment = "Excellent clarity and structure"
    elif clarity_score >= 60:
        assessment = "Good clarity with minor improvements needed"
    elif clarity_score >= 40:
        assessment = "Moderate clarity — focus on structure"
    else:
        assessment = "Needs significant improvement in delivery"

    return {
        "clarity_score": clarity_score,
        "tempo_wpm":     tempo_wpm,
        "assessment":    assessment,
    }