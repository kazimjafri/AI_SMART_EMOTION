# models/ai_evaluator.py
import json
import os
import streamlit as st
import google.generativeai as genai_sdk
from dotenv import load_dotenv

# Load environment variables from .env file for local development
load_dotenv()

@st.cache_resource
def get_gemini_model():
    """Cache the Gemini model initialization so it doesn't reload on every call."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        # Streamlit secrets fallback
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
        else:
            return None
            
    genai_sdk.configure(api_key=api_key)
    return genai_sdk.GenerativeModel("gemini-1.5-flash")


def generate_interview_questions(ctx: dict, profile: dict, num_q: int) -> list:
    """Call Gemini API to produce `num_q` interview questions as JSON."""
    job_title    = ctx.get("job_title", "the role")
    company      = ctx.get("company_name", "the company")
    jd           = ctx.get("job_description", "")
    core_skills  = ", ".join(ctx.get("core_skills", []))
    int_type     = ctx.get("interview_type", profile.get("interview_type", "Mixed"))
    difficulty   = profile.get("difficulty_level", "Medium")
    exp_level    = profile.get("experience_level", "Mid-Level")
    candidate_skills = profile.get("primary_skills", "")
    target_trait = ctx.get("target_trait", "Analytical")

    prompt = f"""You are an expert technical interviewer. Generate exactly {num_q} interview questions for:

    Role: {job_title} at {company}
    Interview type: {int_type}
    Difficulty: {difficulty}
    Candidate experience level: {exp_level}
    Core skills to assess: {core_skills}
    Candidate's stated skills: {candidate_skills}
    Target behavioral trait: {target_trait}
    Job description: {jd[:800] if jd else "Not provided"}

    Rules:
    - Mix question types based on the interview type ({int_type})
    - For Technical: focus on coding concepts, system design, and skill-specific problems
    - For HR: focus on situational, behavioral, and culture-fit questions
    - For Behavioral: use STAR-method prompts
    - For Mixed: blend all three types evenly
    - Vary difficulty — start easier, ramp up
    - Each question must be clearly answerable in 2-5 sentences

    Respond ONLY with a valid JSON array (no markdown, no backticks, no preamble):
    [
      {{"question": "...", "category": "Technical|Behavioral|HR|Situational", "expected_keywords": ["kw1","kw2"]}},
      ...
    ]"""

    try:
        model = get_gemini_model()
        if not model:
            raise ValueError("GEMINI_API_KEY not set in .env or secrets")

        response = model.generate_content(prompt)
        raw = response.text.strip()
        
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        questions = json.loads(raw)
        return questions[:num_q]

    except Exception as e:
        print(f"Error generating questions via API: {e}")
        # Yahan fallback map wali logic wese hi rahegi
        return [{"question": f"Fallback Technical Question for {job_title}?", "category": "Technical", "expected_keywords": []}] * num_q


def evaluate_answer(question: str, answer: str, category: str, expected_keywords: list) -> dict:
    """Score one answer 0-100, return feedback and correctness flag."""
    if not answer.strip():
        return {"score": 0, "feedback": "No answer provided.", "correct": False}

    prompt = f"""You are a strict but fair interview evaluator. Score this answer:
    Question: {question}
    Category: {category}
    Expected keywords (hints): {', '.join(expected_keywords) if expected_keywords else 'N/A'}
    Candidate's answer: {answer}

    Evaluate on:
    - Relevance (does it address the question?)
    - Depth (sufficient detail for {category} level?)
    - Clarity (well-structured and articulate?)
    - Accuracy (technically/factually correct?)

    Respond ONLY with valid JSON (no markdown):
    {{"score": <0-100>, "feedback": "<2 sentences of constructive feedback>", "correct": <true if score>=60>}}"""

    try:
        model = get_gemini_model()
        if not model:
            raise ValueError("No API key")
            
        response = model.generate_content(prompt)
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        return {
            "score":    max(0, min(100, int(result.get("score", 50)))),
            "feedback": result.get("feedback", "Good attempt."),
            "correct":  bool(result.get("correct", False)),
        }
    except Exception:
        word_count = len(answer.split())
        kw_hits = sum(1 for kw in expected_keywords if kw.lower() in answer.lower()) if expected_keywords else 0
        base = min(85, 40 + word_count * 1.2 + kw_hits * 8)
        score = int(min(95, base))
        correct = score >= 60
        return {
            "score":    score,
            "correct":  correct,
            "feedback": f"{'Good answer with reasonable depth.' if correct else 'Answer could use more detail and specificity.'}",
        }