# ===========================
# interview/speech_handler.py
# Browser-based Mic Recording (WebRTC) · Speech-to-Text · Answer Evaluation
# ===========================

import os
import json
import threading
import numpy as np
import av
import streamlit as st
import speech_recognition as sr
from streamlit_webrtc import AudioProcessorBase


# ───────────────────────────────────────────
# BROWSER AUDIO RECORDER
# Receives the candidate's mic audio frames from their browser
# over WebRTC (same connection as the camera). Buffers PCM only
# while "recording" is True (toggled by Start/Stop buttons in
# interview_engine.py), then hands back an sr.AudioData object
# for Google STT — no server-side microphone access involved.
# ───────────────────────────────────────────

class BrowserAudioRecorder(AudioProcessorBase):
    def __init__(self):
        self.lock = threading.Lock()
        self.recording = False
        self.buffer = bytearray()
        self.sample_rate = 16000
        self._resampler = av.AudioResampler(format="s16", layout="mono", rate=self.sample_rate)

    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        if self.recording:
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
        return frame

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

def transcribe_audio(audio_data: sr.AudioData) -> str:
    """
    Convert recorded audio to text.
    Uses Google Web Speech API (free, no key needed).
    Falls back to empty string on failure.
    """
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

@st.cache_resource
def get_gemini_model():
    """
    Configure and load Gemini model ONCE.
    This prevents the app from pausing/reconfiguring on every API call.
    """
    import google.generativeai as genai_sdk
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    genai_sdk.configure(api_key=api_key)
    return genai_sdk.GenerativeModel("gemini-1.5-flash")

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
    Uses Gemini API; falls back to heuristic scoring if unavailable.
    """
    if not answer.strip():
        return {
            "score":        0,
            "feedback":     "No answer was provided.",
            "correct":      False,
            "word_count":   0,
            "keywords_hit": 0,
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

Note: This was a spoken answer, so minor grammar issues are acceptable.

Respond ONLY with valid JSON (no markdown, no extra text):
{{"score": <0-100>, "feedback": "<2 sentences of constructive feedback>", "correct": <true if score>=60>}}"""

    model = get_gemini_model()
    
    try:
        if not model:
            raise ValueError("No model available (missing API key?)")

        response = model.generate_content(prompt)
        raw = response.text.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw.strip())
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
        }

    except Exception:
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