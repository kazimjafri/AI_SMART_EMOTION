# models/hire_advisor.py — Gemini hire/reject recommendation for recruiters
import os

import google.generativeai as genai_sdk
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


@st.cache_resource
def get_hire_advisor_model():
    """Gemini 1.5 Flash — used only when recruiter requests a hire/reject suggestion."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key and "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    if not api_key:
        return None
    genai_sdk.configure(api_key=api_key)
    return genai_sdk.GenerativeModel("gemini-1.5-flash")


def get_hire_recommendation(summary: dict) -> str:
    """
    Return a short Hire/Reject recommendation (2–3 lines) based on report summary.
    summary keys: candidate_name, job_title, overall_score, min_score, dominant_emotion, passed
    """
    candidate_name = summary.get("candidate_name", "Candidate")
    job_title = summary.get("job_title", "the role")
    overall_score = summary.get("overall_score", 0)
    min_score = summary.get("min_score", 60)
    dominant_emotion = summary.get("dominant_emotion", "Neutral")
    passed = summary.get("passed", overall_score >= min_score)
    threshold_label = "PASS (meets minimum)" if passed else "FAIL (below minimum)"

    prompt = f"""You are an expert hiring advisor helping a recruiter decide on a candidate.

Candidate: {candidate_name}
Role: {job_title}
Overall AI interview score: {overall_score}/100
Minimum required score: {min_score}/100
Threshold result: {threshold_label}
Dominant emotion during interview: {dominant_emotion}

Based ONLY on this summary, give the recruiter a concise recommendation.

Respond in exactly this format (no markdown, no bullet points):
Recommendation: Hire OR Reject
Reason: [2-3 sentences explaining why, referencing the score vs threshold and emotion if relevant]

Keep it professional and actionable. Do not mention speech clarity."""

    try:
        model = get_hire_advisor_model()
        if not model:
            return "Recommendation: Unable to connect to Gemini.\nReason: GEMINI_API_KEY is not configured. Please set it in your environment or Streamlit secrets."

        response = model.generate_content(prompt)
        return (response.text or "").strip() or "Recommendation: Review manually.\nReason: Gemini returned an empty response."
    except Exception as e:
        return f"Recommendation: Review manually.\nReason: Could not reach Gemini ({e})."
