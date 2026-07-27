# ===========================
# interview/interview_engine.py
# Full Interview Flow:
#   Camera (top, browser-permission gated) · Question card · Mic button · Next → Complete
#   Real-time emotion sampling (via WebRTC) · End-of-interview summary
# ===========================

import os
import time
import streamlit as st
import json
from dotenv import load_dotenv
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration

load_dotenv()

# Local modules
from interview.emotion_tracker import (
    EmotionVideoProcessor,
    compute_emotion_summary,
)
from interview.speech_handler import (
    BrowserAudioRecorder,
    transcribe_audio,
    evaluate_answer,
    compute_speech_clarity,
)


# ───────────────────────────────────────────
# SESSION STATE KEYS  (all prefixed iv2_)
# ───────────────────────────────────────────

_KEYS = {
    "phase":          "iv2_phase",           # ready | briefing | question | evaluating | done
    "questions":      "iv2_questions",
    "current_q":      "iv2_current_q",
    "answers":        "iv2_answers",         # {idx: text}
    "scores":         "iv2_scores",          # {idx: {score,feedback,correct,...}}
    "emotion_tl":     "iv2_emotion_timeline",# list of emotion dicts
    "completed_at":   "iv2_completed_at",
    "job_ctx":        "job_interview_context",  # set by application_history_tab
    "mic_result":     "iv2_mic_result",      # last recorded transcript
    "is_recording":   "iv2_is_recording",     # mic recording toggle
    "report_b64":     "iv2_report_b64",
    "emotion_summary":"iv2_emotion_summary",
}


def _ss(key: str, default=None):
    k = _KEYS.get(key, key)
    return st.session_state.get(k, default)


def _set(key: str, value):
    st.session_state[_KEYS.get(key, key)] = value


# ───────────────────────────────────────────
# FRAGMENT COMPAT SHIM
# st.fragment must be declared at module level (not created dynamically)
# so run_every actually ticks (used for live object-detection alerts).
# ───────────────────────────────────────────
_fragment = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None)


def _reset_interview():
    """Clear all interview session state."""
    for k in _KEYS.values():
        if k in st.session_state:
            del st.session_state[k]


# ───────────────────────────────────────────
# BROWSER CAMERA WIDGET  (asks for permission)
# Uses a FIXED key so the same connection persists across
# reruns while we're in the briefing/question phases — the
# candidate is only ever asked for permission once per session.
# ───────────────────────────────────────────

_RTC_CONFIG = RTCConfiguration({
    "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
})


def _get_webrtc_ctx():
    """
    Renders the camera widget with restricted size and layout control.
    Uses CSS to ensure the widget stays compact and prevents duplicate key errors.
    """
    # CSS injection to limit camera container size and ensure layout consistency
    st.markdown("""
        <style>
        [data-testid="stWebRTC"] {
            width: 100% !important;
            max-width: 400px !important;
            margin: 0 auto;
        }
        </style>
    """, unsafe_allow_html=True)
    
    try:
        # Optimized constraints: Resolution set to 400x300 for better performance
        # on laptop hardware and to keep the camera widget compact.
        return webrtc_streamer(
            key="iv2_camera",
            mode=WebRtcMode.SENDRECV,
            rtc_configuration=_RTC_CONFIG,
            media_stream_constraints={
                "video": {"width": {"ideal": 400}, "height": {"ideal": 300}},
                "audio": True,
            },
            video_processor_factory=EmotionVideoProcessor,
            audio_processor_factory=BrowserAudioRecorder,
            async_processing=True,
        )
    except Exception as e:
        st.error(
            "⚠️ Camera component failed to load. Make sure `streamlit-webrtc` "
            f"and `av` are installed. ({e})"
        )
        return None


def _camera_ready(webrtc_ctx) -> bool:
    return bool(webrtc_ctx and webrtc_ctx.state.playing and webrtc_ctx.video_processor)


# ───────────────────────────────────────────
# QUESTION GENERATION  (Gemini / fallback)
# ───────────────────────────────────────────

# ───────────────────────────────────────────
# QUESTION GENERATION  (Updated to use recruiter-defined num_questions)
# ───────────────────────────────────────────

def _generate_questions(profile: dict, job_ctx: dict) -> list:
    """
    Generate interview questions tailored to candidate profile + job context.
    Uses recruiter-defined 'num_questions' from job_ctx.
    """

    job_title    = job_ctx.get("job_title", "General Role")
    company      = job_ctx.get("company_name", "")
    num_q        = job_ctx.get("num_questions", 10) # if no. of questions not specified, default to 10
    job_desc     = job_ctx.get("job_description", "")
    core_skills  = job_ctx.get("core_skills", [])
    int_type     = job_ctx.get("interview_type", "Mixed")
    years_exp    = profile.get("years_experience", 1)
    exp_level    = job_ctx.get("experience_level", "Mid")
    candidate_skills = profile.get("primary_skills", "")
    

    prompt = f"""You are an expert technical interviewer. Generate exactly {num_q} interview questions.

Role: {job_title}
Company: {company}
Interview type: {int_type}
Candidate experience: {years_exp} years
Candidate skills: {candidate_skills}
Candidate Experience Level: {exp_level}
Core skills required: {', '.join(core_skills) if core_skills else 'General'}
Job description: {job_desc[:500] if job_desc else 'N/A'}

Rules:
- Questions must be relevant to the role and skills listed
- Mix difficulty based on experience level
- For Mixed type: blend Technical, Behavioral, and HR questions
- Each question needs 2-4 expected_keywords

Respond ONLY with a valid JSON array (no markdown):
[
  {{
    "question": "...",
    "category": "Technical|Behavioral|HR",
    "expected_keywords": ["kw1", "kw2", "kw3"]
  }}  
]"""

    try:
        api_key = os.environ.get("GEMINI_API_KEY", "")    
        if not api_key:
            raise ValueError("No API Key found in .env")

        import google.generativeai as genai_sdk
        import json
        genai_sdk.configure(api_key=api_key)
        model    = genai_sdk.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        raw      = response.text.strip()

        # Clean potential markdown if Gemini ignores instructions
        if raw.startswith("```"):
            parts = raw.split("```")
            raw   = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]

        questions = json.loads(raw.strip())
        if isinstance(questions, list) and questions:
            # Recruiter ke number ke mutabiq slice
            return questions[:num_q]
        raise ValueError("Empty result")

    except Exception:
        # Fallback mein bhi num_q use karein
        return _fallback_questions(job_title, company, core_skills, int_type, num_q)


def _fallback_questions(job_title, company, core_skills, int_type, num_q) -> list:
    """Curated fallback question bank."""
    skills_str = ", ".join(core_skills[:3]) if core_skills else "relevant technologies"

    bank = {
        "Technical": [
            {"question": f"Explain how you would architect a scalable system for {job_title} tasks. Walk me through your design decisions.",
             "category": "Technical", "expected_keywords": ["scalable", "architecture", "design", "system"]},
            {"question": f"How do you approach debugging a critical production issue? Describe your process step by step.",
             "category": "Technical", "expected_keywords": ["debug", "logs", "reproduce", "fix", "monitor"]},
            {"question": f"Describe your experience with {skills_str}. Give a specific example of a project where you used these.",
             "category": "Technical", "expected_keywords": ["experience", "project", "implement", "solution"]},
            {"question": "What is the difference between synchronous and asynchronous programming? When would you choose each?",
             "category": "Technical", "expected_keywords": ["async", "sync", "blocking", "non-blocking", "performance"]},
            {"question": "How do you ensure code quality in your projects? What practices do you follow?",
             "category": "Technical", "expected_keywords": ["testing", "review", "clean code", "documentation", "CI"]},
            {"question": "Explain a complex technical concept you recently learned and how you applied it.",
             "category": "Technical", "expected_keywords": ["learn", "apply", "concept", "implementation"]},
            {"question": "How do you handle performance bottlenecks in an application?",
             "category": "Technical", "expected_keywords": ["profiling", "optimize", "cache", "database", "bottleneck"]},
        ],
        "Behavioral": [
            {"question": "Tell me about a time you had a disagreement with a teammate. How did you resolve it?",
             "category": "Behavioral", "expected_keywords": ["conflict", "communicate", "resolve", "team", "outcome"]},
            {"question": "Describe a project where you had to learn something new under a tight deadline. How did you manage?",
             "category": "Behavioral", "expected_keywords": ["learn", "deadline", "manage", "prioritize", "outcome"]},
            {"question": "Give an example of when you took ownership of a problem beyond your assigned responsibilities.",
             "category": "Behavioral", "expected_keywords": ["ownership", "initiative", "problem", "result", "impact"]},
            {"question": "Tell me about a time you failed at something. What did you learn from it?",
             "category": "Behavioral", "expected_keywords": ["failure", "learn", "improve", "reflect", "change"]},
            {"question": "How do you prioritize when you have multiple urgent tasks competing for your time?",
             "category": "Behavioral", "expected_keywords": ["prioritize", "organize", "deadline", "communication", "manage"]},
        ],
        "HR": [
            {"question": f"Why are you interested in the {job_title} role at {company}?",
             "category": "HR", "expected_keywords": ["interest", "growth", "skills", "company", "role"]},
            {"question": "Where do you see yourself professionally in the next 3 to 5 years?",
             "category": "HR", "expected_keywords": ["goal", "growth", "career", "develop", "leadership"]},
            {"question": "What is your greatest professional strength and how does it make you effective in your work?",
             "category": "HR", "expected_keywords": ["strength", "effective", "skill", "impact", "example"]},
            {"question": "How do you stay up to date with the latest trends and developments in your field?",
             "category": "HR", "expected_keywords": ["learn", "read", "courses", "community", "practice"]},
            {"question": "Describe your ideal work environment and team culture.",
             "category": "HR", "expected_keywords": ["collaborate", "culture", "team", "environment", "communicate"]},
        ],
    }

    import random
    if int_type == "Mixed":
        pool = []
        for t in ["Technical", "Behavioral", "HR"]:
            pool.extend(bank[t])
    else:
        pool = bank.get(int_type, bank["Technical"])

    random.shuffle(pool)
    return pool[:num_q]


# ───────────────────────────────────────────
# CSS  for interview page
# ───────────────────────────────────────────

def _inject_interview_css():
    st.markdown("""
<style>
/* ═══════════════════════
   INTERVIEW LAYOUT
═══════════════════════ */
.iv-page-wrap {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 0.5rem;
}

/* Question card */
.iv-q-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1.6rem 1.75rem;
  margin: 1.25rem 0;
  box-shadow: var(--shadow-card);
}
.iv-q-eyebrow {
  font-family: 'DM Mono', monospace;
  font-size: 0.65rem;
  color: var(--text-mono);
  text-transform: uppercase;
  letter-spacing: 2px;
  margin-bottom: 0.6rem;
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.iv-q-cat-badge {
  background: var(--tag-bg);
  border: 1px solid var(--tag-border);
  border-radius: 4px;
  padding: 1px 8px;
  font-size: 0.6rem;
  color: var(--tag-txt);
  letter-spacing: 0.8px;
}
.iv-q-text {
  font-family: 'Sora', sans-serif;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-h);
  line-height: 1.55;
  letter-spacing: -0.2px;
}

/* Progress bar */
.iv-prog-wrap {
  background: var(--border);
  border-radius: 50px;
  height: 5px;
  margin: 0.6rem 0 0.3rem;
  overflow: hidden;
}
.iv-prog-fill {
  height: 100%;
  border-radius: 50px;
  background: linear-gradient(90deg, #059669, #34d399);
  transition: width 0.4s ease;
}

                
/* Mic button */
.iv-mic-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 1.2rem 0 0.6rem;
}

/* Transcript card */
.iv-transcript {
  background: var(--bg-card-2);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 1rem 1.25rem;
  font-family: 'Sora', sans-serif;
  font-size: 0.88rem;
  color: var(--text-body);
  line-height: 1.65;
  min-height: 60px;
  margin-bottom: 0.75rem;
}
.iv-transcript-label {
  font-family: 'DM Mono', monospace;
  font-size: 0.62rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1.5px;
  margin-bottom: 0.4rem;
}

/* Score card (after eval) */
.iv-score-pass { border-left: 3px solid #059669 !important; }
.iv-score-fail { border-left: 3px solid #dc2626 !important; }
.iv-score-card {
  background: var(--bg-card-2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.85rem 1.1rem;
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 0.75rem;
}
.iv-score-num {
  font-family: 'Sora', sans-serif;
  font-size: 1.6rem;
  font-weight: 800;
  color: var(--accent);
  line-height: 1;
  white-space: nowrap;
}
.iv-score-label {
  font-family: 'DM Mono', monospace;
  font-size: 0.62rem;
  color: var(--text-muted);
  letter-spacing: 0.5px;
}
.iv-score-feedback {
  font-family: 'Sora', sans-serif;
  font-size: 0.8rem;
  color: var(--text-body);
  line-height: 1.55;
  font-style: italic;
}

/* Nav dots */
.iv-dots {
  display: flex;
  justify-content: center;
  gap: 6px;
  margin-top: 0.75rem;
}

/* Final hero */
.iv-final-hero {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 2.5rem 2rem;
  text-align: center;
  margin-bottom: 1.5rem;
  box-shadow: var(--shadow-card);
}
.iv-final-score {
  font-family: 'Sora', sans-serif;
  font-size: 4rem;
  font-weight: 800;
  letter-spacing: -3px;
  line-height: 1;
  margin: 0.6rem 0 0.2rem;
}
.iv-final-label {
  font-family: 'DM Mono', monospace;
  font-size: 0.7rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 2px;
  margin-bottom: 0.75rem;
}
.iv-verdict-pass {
  background: rgba(5,150,105,0.10);
  border: 1px solid rgba(5,150,105,0.30);
  color: #059669;
  border-radius: 50px;
  padding: 4px 18px;
  font-family: 'DM Mono', monospace;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.5px;
}
.iv-verdict-fail {
  background: rgba(239,68,68,0.08);
  border: 1px solid rgba(239,68,68,0.25);
  color: #dc2626;
  border-radius: 50px;
  padding: 4px 18px;
  font-family: 'DM Mono', monospace;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.5px;
}

/* Emotion summary card */
.iv-emotion-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1.4rem 1.5rem;
  box-shadow: var(--shadow-card);
  margin-bottom: 1rem;
}
.iv-emotion-title {
  font-family: 'DM Mono', monospace;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--text-muted);
  margin-bottom: 1rem;
}
.iv-emotion-bar-wrap {
  background: var(--border);
  border-radius: 50px;
  height: 8px;
  overflow: hidden;
  margin: 4px 0 10px;
}
.iv-bar-conf { background: linear-gradient(90deg, #059669, #34d399); height: 100%; border-radius: 50px; }
.iv-bar-anx  { background: linear-gradient(90deg, #ef4444, #f87171); height: 100%; border-radius: 50px; }
.iv-bar-comp { background: linear-gradient(90deg, #3b82f6, #60a5fa); height: 100%; border-radius: 50px; }
</style>
""", unsafe_allow_html=True)


# ───────────────────────────────────────────
# BRIEFING SCREEN  (camera permission gate lives here)
# ───────────────────────────────────────────

def _render_briefing(job_ctx: dict, profile: dict, webrtc_ctx):
    job_title = job_ctx.get("job_title", "Interview")
    company   = job_ctx.get("company_name", "")
    num_q_est = 5 if profile.get("years_experience", 1) <= 1 else (7 if profile.get("years_experience", 1) <= 3 else 10)

    st.markdown(f"""
    <div class="page-hero">
      <span class="eyebrow">// AI Interview · Camera + Voice Mode</span>
      <h1>Ready to begin?</h1>
      <p class="sub">
        <strong>{job_title}</strong>{f' at {company}' if company else ''}<br>
        {num_q_est} questions &nbsp;·&nbsp; Voice answers &nbsp;·&nbsp; Camera on throughout
      </p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3, gap="medium")
    tips = [
        ("🎙️", "Speak clearly", "Press the mic button, answer, then press stop. Speak at a natural pace."),
        ("📷", "Camera on", "Allow camera access below. Sit in a well-lit area facing the camera."),
        ("⏭️", "Skip if needed", "You can skip any question using the Skip button and move on when ready."),
    ]
    for col, (icon, title, desc) in zip([c1, c2, c3], tips):
        with col:
            st.markdown(f"""
            <div class="feat-card">
              <span class="feat-icon">{icon}</span>
              <div class="feat-title">{title}</div>
              <div class="feat-desc">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Camera permission gate ──
    st.markdown('<div class="section-heading">📷 Camera Check</div>', unsafe_allow_html=True)
    st.caption("Click **START** below and allow camera access when your browser asks.")

    cam_ready = _camera_ready(webrtc_ctx)

    if cam_ready:
        st.success("✅ Camera connected — you're ready to begin.")
    elif webrtc_ctx is not None:
        st.warning("⏳ Waiting for camera permission. Click **START** on the widget above.")
    else:
        st.error("⚠️ Camera component unavailable. Check the setup notes below.")

    st.markdown("<br>", unsafe_allow_html=True)

    bc1, bc2, bc3 = st.columns([1, 1.5, 1])
    with bc2:
        if st.button(
            "🚀  Begin Interview",
            use_container_width=True,
            key="iv2_begin_btn",
            disabled=not cam_ready,
        ):
            # Clear any leftover data from a previous attempt
            if webrtc_ctx and webrtc_ctx.video_processor:
                webrtc_ctx.video_processor.reset()

            # --- MODERN ANIMATED SPINNER ---
            with st.status("🤖 Generating role-specific questions...", expanded=True) as status:
                questions = _generate_questions(profile, job_ctx)
                status.update(label="✅ Questions ready!", state="complete", expanded=False)

            _set("questions",  questions)
            _set("current_q",  0)
            _set("answers",    {})
            _set("scores",     {})
            _set("emotion_tl", [])
            _set("phase", "question")
            st.rerun()

        if not cam_ready:
            st.caption("Camera permission is required before the interview can start.")


# ───────────────────────────────────────────
# QUESTION SCREEN
# (camera widget is already rendered above this, by render_interview_page)
# ───────────────────────────────────────────

def _render_question_header(job_title: str, current: int, total: int):
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;">
      <span style="font-family:'DM Mono',monospace;font-size:0.65rem;color:var(--text-muted);
                   text-transform:uppercase;letter-spacing:2px;">// {job_title}</span>
      <span style="font-family:'DM Mono',monospace;font-size:0.7rem;color:var(--text-mono);">Q{current + 1} / {total}</span>
    </div>
    """, unsafe_allow_html=True)


def _stop_recording(webrtc_ctx):
    _set("is_recording", False)
    if webrtc_ctx and webrtc_ctx.audio_processor:
        try:
            webrtc_ctx.audio_processor.stop_recording()
        except Exception:
            pass


def _skip_current_question(current: int, total: int, webrtc_ctx):
    """Mark the current question as skipped and advance."""
    answers = _ss("answers", {})
    scores = _ss("scores", {})
    answers[current] = ""
    scores[current] = {
        "score": 0,
        "correct": False,
        "feedback": "⏭️ Question skipped by candidate.",
        "skipped": True,
    }
    _set("answers", answers)
    _set("scores", scores)
    _stop_recording(webrtc_ctx)

    if current < total - 1:
        _set("current_q", current + 1)
    else:
        if webrtc_ctx and webrtc_ctx.video_processor:
            _set("emotion_tl", webrtc_ctx.video_processor.get_timeline())
        _set("phase", "evaluating")


def _render_object_alert(webrtc_ctx):
    """Show prohibited-object alert; refreshes via fragment when available."""
    if not (webrtc_ctx and webrtc_ctx.video_processor):
        return

    alert = webrtc_ctx.video_processor.get_object_alert()
    if alert:
        labels = ", ".join(a.replace("_", " ").title() for a in alert)
        st.error(f"🚫 Prohibited object detected: **{labels}** — please remove it from camera view.")


if _fragment is not None:
    @_fragment(run_every=1)
    def _tick_object_alert(webrtc_ctx):
        _render_object_alert(webrtc_ctx)
else:
    def _tick_object_alert(webrtc_ctx):
        _render_object_alert(webrtc_ctx)


def _render_question_screen(job_ctx: dict, profile: dict, webrtc_ctx):
    """
    Renders the question card and recording controls. 
    Camera is already rendered in the parent column, so we just use the webrtc_ctx.
    """
    questions = _ss("questions", [])
    current   = _ss("current_q", 0)
    total     = len(questions)

    if not questions or current >= total:
        _set("phase", "evaluating")
        st.rerun()
        return

    job_title = job_ctx.get("job_title",    "Interview")
    company   = job_ctx.get("company_name", "")
    q_obj     = questions[current]
    q_text    = q_obj.get("question",  "—")
    category  = q_obj.get("category",  "General")
    keywords  = q_obj.get("expected_keywords", [])

    _render_question_header(job_title, current, total)

    # Progress bar
    pct = int((current / total) * 100)
    st.markdown(f"""
    <div class="iv-prog-wrap"><div class="iv-prog-fill" style="width:{pct}%;"></div></div>
    """, unsafe_allow_html=True)

    # ── QUESTION CARD ──
    st.markdown(f"""
    <div class="iv-q-card">
      <div class="iv-q-eyebrow">// question {current + 1} <span class="iv-q-cat-badge">{category.upper()}</span></div>
      <div class="iv-q-text">{q_text}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Transcript / Score display ──
    prev_answer = _ss("answers", {}).get(current, "")
    if prev_answer:
        st.markdown(f'<div class="iv-transcript-label">// your recorded answer</div><div class="iv-transcript">{prev_answer}</div>', unsafe_allow_html=True)

    # ── Recording Controls ──
    is_recording = _ss("is_recording", False)
    if not is_recording:
        btn_label = "🎙️ Start Recording" if not prev_answer else "🔄 Re-record Answer"
        if st.button(btn_label, use_container_width=True, key=f"iv2_mic_start_{current}"):
            if webrtc_ctx and webrtc_ctx.audio_processor:
                webrtc_ctx.audio_processor.start_recording()
                _set("is_recording", True)
                st.rerun()
            else:
                st.warning("⚠️ Microphone not accessible.")
    else:
        st.markdown('<div style="text-align:center;color:#dc2626;font-family:\'DM Mono\',monospace;font-size:0.72rem;">🔴 Recording...</div>', unsafe_allow_html=True)
        if st.button("⏹ Stop & Submit", use_container_width=True, key=f"iv2_mic_stop_{current}"):
            audio_data = webrtc_ctx.audio_processor.stop_recording() if webrtc_ctx and webrtc_ctx.audio_processor else None
            _set("is_recording", False)
            if audio_data:
                with st.status("Processing audio...", expanded=True) as status:
                    transcript = transcribe_audio(audio_data)
                    if transcript:
                        answers = _ss("answers", {}); answers[current] = transcript; _set("answers", answers)
                        score_res = evaluate_answer(q_text, transcript, category, keywords, job_title, company)
                        scores = _ss("scores", {}); scores[current] = score_res; _set("scores", scores)
                        status.update(label="✅ Answer processed!", state="complete", expanded=False)
                    else:
                        status.update(label="⚠️ Transcription failed.", state="error")
            st.rerun()

    # ── Navigation ──
    nav1, nav_skip, nav2 = st.columns([1, 1, 1])
    with nav1:
        if current > 0 and st.button("← Back", use_container_width=True, key=f"iv2_back_{current}"):
            _stop_recording(webrtc_ctx)
            _set("current_q", current - 1)
            st.rerun()
    with nav_skip:
        if st.button("⏭️ Skip", use_container_width=True, key=f"iv2_skip_{current}"):
            _skip_current_question(current, total, webrtc_ctx)
            st.rerun()
    with nav2:
        if current < total - 1:
            if st.button("Next →", use_container_width=True, key=f"iv2_next_{current}"):
                if not _ss("answers", {}).get(current, "").strip():
                    st.warning("Record an answer first, or use Skip.")
                else:
                    _stop_recording(webrtc_ctx)
                    _set("current_q", current + 1)
                    st.rerun()
        else:
            if st.button("✅ Finish Interview", use_container_width=True, key=f"iv2_finish_{current}"):
                if webrtc_ctx and webrtc_ctx.video_processor:
                    _set("emotion_tl", webrtc_ctx.video_processor.get_timeline())
                _set("phase", "evaluating")
                st.rerun()

    # ── Progress dots ──
    answers = _ss("answers", {})
    scores  = _ss("scores",  {})
    dots_html = ""
    for i in range(total):
        has_answer = bool(answers.get(i, "").strip())
        score_entry = scores.get(i)
        has_score  = score_entry is not None
        is_skipped = bool(score_entry and score_entry.get("skipped"))
        if i == current:
            col = "var(--accent)"
        elif is_skipped:
            col = "#94a3b8"
        elif has_score:
            col = "#10b981" if score_entry.get("correct") else "#ef4444"
        elif has_answer:
            col = "#d97706"
        else:
            col = "var(--border)"
        dots_html += (
            f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
            f'background:{col};margin:0 3px;cursor:default;" title="Q{i+1}"></span>'
        )

    st.markdown(
        f'<div class="iv-dots">{dots_html}</div>'
        f'<div style="text-align:center;font-family:\'DM Mono\',monospace;font-size:0.6rem;'
        f'color:var(--text-muted);margin-top:0.4rem;letter-spacing:0.5px;">'
        f'🟢 scored &nbsp; 🔴 needs work &nbsp; 🟡 recorded &nbsp; ⚪ pending &nbsp; ⬜ skipped</div>',
        unsafe_allow_html=True
    )


# ───────────────────────────────────────────
# EVALUATING SCREEN
# ───────────────────────────────────────────

def _render_evaluating(job_ctx: dict, profile: dict):
    st.markdown("""
    <div class="page-hero">
      <span class="eyebrow">// Processing Results</span>
      <h1>Calculating your results...</h1>
      <p class="sub">Scoring your responses and building your emotion report.</p>
    </div>
    """, unsafe_allow_html=True)

    questions = _ss("questions", [])
    answers   = _ss("answers",   {})
    scores    = _ss("scores",    {})
    job_title = job_ctx.get("job_title",    "")
    company   = job_ctx.get("company_name", "")

    unevaluated = [i for i in range(len(questions)) if i not in scores]
    
    # --- MODERN ANIMATED SPINNER (Replaces old st.progress loop) ---
    with st.status("📊 Finalizing Interview Results...", expanded=True) as status:
        if unevaluated:
            for step, i in enumerate(unevaluated):
                status.update(label=f"🤖 Scoring Q{i+1}...", state="running")
                q_obj  = questions[i]
                answer = answers.get(i, "")
                result = evaluate_answer(
                    question=q_obj.get("question", ""),
                    answer=answer,
                    category=q_obj.get("category", "General"),
                    expected_keywords=q_obj.get("expected_keywords", []),
                    job_title=job_title,
                    company=company,
                )
                scores[i] = result
                _set("scores", scores)

        status.update(label="📊 Building emotion analysis...", state="running")
        emotion_tl = _ss("emotion_tl", [])
        emotion_summary = compute_emotion_summary(emotion_tl)
        _set("emotion_summary", emotion_summary)
        
        status.update(label="✅ Interview processing complete!", state="complete", expanded=False)

    _set("completed_at", datetime.utcnow().isoformat())
    _set("phase", "done")
    st.rerun()


# ───────────────────────────────────────────
# DONE / RESULTS SCREEN
# ───────────────────────────────────────────

def _render_done(job_ctx: dict, profile: dict):
    from reports.pdf_generator import generate_interview_report_pdf
    from reports.firebase_saver import save_interview_report

    questions      = _ss("questions",     [])
    answers        = _ss("answers",       {})
    scores         = _ss("scores",        {})
    completed_at   = _ss("completed_at",  datetime.utcnow().isoformat())
    emotion_summary= _ss("emotion_summary", {})
    job_title      = job_ctx.get("job_title",    "Interview")
    company        = job_ctx.get("company_name", "")
    min_score      = job_ctx.get("min_score",    60)
    app_key        = job_ctx.get("app_key",      "")
    recruiter_uid  = job_ctx.get("recruiter_uid","")

    total_q    = len(questions)
    avg_score  = round(sum(scores.get(i, {}).get("score", 0) for i in range(total_q)) / total_q) if total_q else 0
    correct_c  = sum(1 for i in range(total_q) if scores.get(i, {}).get("correct", False))
    incorrect_c= total_q - correct_c
    passed     = avg_score >= min_score

    score_color  = "#059669" if passed else "#dc2626"
    verdict_cls  = "iv-verdict-pass" if passed else "iv-verdict-fail"
    verdict_txt  = f"PASS — meets {min_score}% threshold" if passed else f"FAIL — below {min_score}% threshold"

    # ── Final hero ──
    st.markdown(f"""
    <div class="iv-final-hero">
      <span style="font-family:'DM Mono',monospace;font-size:0.65rem;color:var(--text-muted);
                   text-transform:uppercase;letter-spacing:2px;">
        // interview complete · {job_title}{f' at {company}' if company else ''}
      </span>
      <div class="iv-final-score" style="color:{score_color};">
        {avg_score}<span style="font-size:1.6rem;color:var(--text-muted);">/100</span>
      </div>
      <div class="iv-final-label">overall score</div>
      <span class="iv-{verdict_cls.split('-',1)[1]}">{verdict_txt}</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Stats row ──
    s1, s2, s3, s4 = st.columns(4, gap="small")
    for col, (n, lbl) in zip([s1, s2, s3, s4], [
        (total_q,       "questions"),
        (correct_c,     "correct"),
        (incorrect_c,   "needs work"),
        (f"{avg_score}%","avg score"),
    ]):
        with col:
            st.markdown(
                f'<div class="stat-card"><div class="stat-num" style="font-size:1.5rem;">{n}</div>'
                f'<div class="stat-label">{lbl}</div></div>',
                unsafe_allow_html=True
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Emotion summary ──
    if emotion_summary and emotion_summary.get("total_samples", 0) > 0:
        st.markdown('<div class="section-heading">📊 Emotion Analysis</div>', unsafe_allow_html=True)
        avg_conf = emotion_summary.get("avg_confidence", 0)
        avg_anx  = emotion_summary.get("avg_anxiety",    0)
        avg_comp = emotion_summary.get("avg_composed",   0)
        dom_em   = emotion_summary.get("dominant_emotion","—")
        assess   = emotion_summary.get("assessment",      "")

        e1, e2, e3, e4 = st.columns(4, gap="small")
        for col, (n, lbl, bar_cls) in zip([e1, e2, e3, e4], [
            (f"{avg_conf}%", "confidence",      "iv-bar-conf"),
            (f"{avg_anx}%",  "anxiety",         "iv-bar-anx"),
            (f"{avg_comp}%", "composure",       "iv-bar-comp"),
            (dom_em,         "dominant emotion",""),
        ]):
            with col:
                st.markdown(
                    f'<div class="stat-card"><div class="stat-num" style="font-size:1.2rem;">{n}</div>'
                    f'<div class="stat-label">{lbl}</div></div>',
                    unsafe_allow_html=True
                )

        if assess:
            st.markdown(
                f'<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:12px;'
                f'padding:0.9rem 1.2rem;margin:0.75rem 0;font-family:\'Sora\',sans-serif;'
                f'font-size:0.85rem;color:var(--text-body);line-height:1.6;">'
                f'<span style="font-family:\'DM Mono\',monospace;font-size:0.6rem;color:var(--text-muted);">'
                f'// assessment</span><br>{assess}</div>',
                unsafe_allow_html=True
            )

    # ── Score breakdown ──
    st.markdown('<div class="section-heading">Score breakdown</div>', unsafe_allow_html=True)
    for i, q_obj in enumerate(questions):
        sc      = scores.get(i, {})
        score   = sc.get("score", 0)
        correct = sc.get("correct", False)
        result  = "✓" if correct else "✗"
        bar_col = "#059669" if correct else "#dc2626"
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem;">
          <span style="font-family:'DM Mono',monospace;font-size:0.65rem;color:var(--text-muted);
                       min-width:28px;">Q{i+1}</span>
          <span style="min-width:18px;font-weight:700;color:{bar_col};">{result}</span>
          <div style="flex:1;background:var(--border);border-radius:50px;height:7px;overflow:hidden;">
            <div style="width:{score}%;height:100%;background:{bar_col};border-radius:50px;"></div>
          </div>
          <span style="font-family:'DM Mono',monospace;font-size:0.65rem;color:var(--text-muted);
                       min-width:48px;text-align:right;">{score}/100</span>
          <span style="font-family:'DM Mono',monospace;font-size:0.6rem;color:var(--text-muted);
                       min-width:70px;">{q_obj.get('category','')}</span>
        </div>
        """, unsafe_allow_html=True)

    # ── Full answer review ──
    with st.expander("📋 Full answer review", expanded=False):
        for i, q_obj in enumerate(questions):
            sc       = scores.get(i, {})
            score    = sc.get("score",    0)
            correct  = sc.get("correct",  False)
            answer   = answers.get(i, "(No answer recorded)").strip() or "(No answer recorded)"
            feedback = sc.get("feedback", "")
            rc       = "#059669" if correct else "#dc2626"
            rl       = "✓ Correct" if correct else "✗ Needs Work"
            st.markdown(f"""
            <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:12px;
                        padding:1rem 1.25rem;margin-bottom:0.9rem;">
              <div style="font-family:'DM Mono',monospace;font-size:0.62rem;color:var(--text-muted);
                          margin-bottom:0.4rem;">
                // Q{i+1} · {q_obj.get('category','')} ·
                <span style="color:{rc};font-weight:700;">{rl} · {score}/100</span>
              </div>
              <div style="font-family:'Sora',sans-serif;font-size:0.92rem;font-weight:600;
                          color:var(--text-h);margin-bottom:0.6rem;line-height:1.5;">
                {q_obj.get('question','')}
              </div>
              <div style="font-family:'Sora',sans-serif;font-size:0.83rem;color:var(--text-body);
                          background:var(--bg-card-2);border-radius:8px;padding:0.65rem 0.9rem;
                          margin-bottom:0.5rem;line-height:1.6;">{answer}</div>
              <div style="font-family:'DM Mono',monospace;font-size:0.68rem;color:var(--text-muted);
                          font-style:italic;">💬 {feedback}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Generate + save PDF ──
    st.markdown('<div class="section-heading">📄 Your Report</div>', unsafe_allow_html=True)

    report_b64 = _ss("report_b64", "")

    if not report_b64:
        # ---ANIMATED SPINNER ---
        with st.status("📄 Compiling your final report...", expanded=True) as status:
            try:
                pdf_bytes = generate_interview_report_pdf(
                    candidate_name=profile.get("full_name", st.session_state.get("user_name", "Candidate")),
                    job_title=job_title,
                    company=company,
                    questions=questions,
                    answers=answers,
                    scores=scores,
                    completed_at=completed_at,
                    emotion_summary=emotion_summary,
                )

                # Save to Firebase
                uid = st.session_state.get("user_uid", "")
                if uid and app_key:
                    status.update(label="💾 Saving report to database...", state="running")
                    report_payload = {
                        "candidate_uid":    uid,
                        "candidate_name":   profile.get("full_name", st.session_state.get("user_name", "")),
                        "job_title":        job_title,
                        "company_name":     company,
                        "app_key":          app_key,
                        "overall_score":    avg_score,
                        "correct_count":    correct_c,
                        "incorrect_count":  incorrect_c,
                        "total_questions":  total_q,
                        "avg_confidence":   emotion_summary.get("avg_confidence", 0),
                        "avg_anxiety":      emotion_summary.get("avg_anxiety",    0),
                        "avg_composed":     emotion_summary.get("avg_composed",   0),
                        "emotion_behavioral_score": emotion_summary.get("overall_score", 50),
                        "dominant_emotion": emotion_summary.get("dominant_emotion","Neutral"),
                        "emotion_assessment": emotion_summary.get("assessment",   ""),
                        "completed_at":     completed_at,
                        "questions_data": [
                            {
                                "question": questions[i].get("question",  ""),
                                "category": questions[i].get("category",  ""),
                                "answer":   answers.get(i, ""),
                                "score":    scores.get(i, {}).get("score",    0),
                                "correct":  scores.get(i, {}).get("correct",  False),
                                "feedback": scores.get(i, {}).get("feedback", ""),
                            }
                            for i in range(total_q)
                        ],
                        "emotion_timeline": emotion_summary.get("timeline", []),
                    }
                    save_interview_report(uid, app_key, recruiter_uid, report_payload)

                import base64
                report_b64 = base64.b64encode(pdf_bytes).decode()
                _set("report_b64", report_b64)
                
                status.update(label="✅ Report generated and saved!", state="complete", expanded=False)
            except Exception as e:
                status.update(label="⚠️ Failed to generate report.", state="error")
                st.warning(f"⚠️ Could not generate PDF: {e}")

    if report_b64:
        import base64
        pdf_bytes_dl = base64.b64decode(report_b64)
        cand_name    = profile.get("full_name", "Candidate").replace(" ", "_")
        fname        = f"InterviewAI_{cand_name}_{completed_at[:10]}.pdf"
        dl1, dl2, dl3 = st.columns([1, 1.5, 1])
        with dl2:
            st.download_button(
                label="⬇️  Download PDF Report",
                data=pdf_bytes_dl,
                file_name=fname,
                mime="application/pdf",
                use_container_width=True,
                key="iv2_dl_pdf",
            )
        st.caption("// includes scores, feedback, and emotion analysis summary")
    else:
        st.info("PDF will be available shortly — please check your dashboard.")

    st.markdown("<br>", unsafe_allow_html=True)

    col_back1, col_back2, col_back3 = st.columns([1, 1.5, 1])
    with col_back2:
        if st.button("← Back to Dashboard", use_container_width=True, key="iv2_done_home"):
            _reset_interview()
            st.session_state.current_page = "dashboard"
            st.rerun()


# ───────────────────────────────────────────
# MAIN ENTRY POINT  (called from app.py)
# ───────────────────────────────────────────

def render_interview_page():
    """
    Main interview page renderer.
    Camera is initialized once at the top to avoid duplicate key errors.
    Layout splits into columns during the 'question' phase.
    """
    _inject_interview_css()

    from utils.firebase_helpers import load_candidate_profile

    uid     = st.session_state.get("user_uid", "")
    profile = load_candidate_profile(uid) if uid else {}
    job_ctx = st.session_state.get("job_interview_context")

    if not job_ctx:
        job_ctx = {
            "job_title":      "General Interview",
            "company_name":   "",
            "job_description":"",
            "core_skills":    [],
            "interview_type": "Mixed",
            "min_score":       60,
            "app_key":         f"general_{uid}_{int(time.time())}",
            "recruiter_uid":   "",
            "min_speech_clarity": 60,
        }

    # Initialize phase
    if _ss("phase") is None:
        _set("phase", "briefing")
    phase = _ss("phase")

    # Layout structure
    if phase == "briefing":
        # Full width for briefing
        webrtc_ctx = _get_webrtc_ctx()
        _render_briefing(job_ctx, profile, webrtc_ctx)

    elif phase == "question":
        # Split layout for questions: Question (2/3) + Camera (1/3)
        col_left, col_right = st.columns([2, 1])

        # Camera is rendered inside the right column
        with col_right:
            st.markdown("### 📷 Live Camera")
            webrtc_ctx = _get_webrtc_ctx()
            _tick_object_alert(webrtc_ctx)

        with col_left:
            _render_question_screen(job_ctx, profile, webrtc_ctx)

    elif phase == "evaluating":
        _render_evaluating(job_ctx, profile)

    elif phase == "done":
        _render_done(job_ctx, profile)

    else:
        _set("phase", "briefing")
        st.rerun()