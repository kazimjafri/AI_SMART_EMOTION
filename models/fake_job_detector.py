# ===========================================================
# models/fake_job_detector.py
# Loads the trained Logistic Regression model (saved via joblib)
# and predicts whether a job posting is Real or Fake.
#
# Place fake_job_model.pkl, fake_job_vectorizer.pkl, and
# fake_job_scaler.pkl inside AI_SMART_EMOTION/models/ before using this.
# ===========================================================

import os
import re
import joblib
import numpy as np
import streamlit as st
from scipy.sparse import hstack, csr_matrix

MODEL_DIR = os.path.dirname(__file__)

MODEL_PATH      = os.path.join(MODEL_DIR, "fake_job_model.pkl")
VECTORIZER_PATH = os.path.join(MODEL_DIR, "fake_job_vectorizer.pkl")
SCALER_PATH     = os.path.join(MODEL_DIR, "fake_job_scaler.pkl")


@st.cache_resource
def load_fake_job_artifacts():
    """Load model + vectorizer + scaler once, cache across reruns."""
    try:
        model      = joblib.load(MODEL_PATH)
        vectorizer = joblib.load(VECTORIZER_PATH)
        scaler     = joblib.load(SCALER_PATH)
        return model, vectorizer, scaler
    except FileNotFoundError:
        return None, None, None


def _clean_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _url_heuristics(url: str) -> list:
    """
    Cheap, rule-based signals from the URL itself.
    These are NOT part of the trained model (which was trained on
    job-description text only) — they're shown as extra supporting
    context alongside the model's prediction.
    """
    flags = []
    url_lower = (url or "").lower().strip()
    if not url_lower:
        return flags

    if not url_lower.startswith("https://"):
        flags.append("Link is not HTTPS-secured")

    suspicious_domains = ["bit.ly", "tinyurl", "wa.me", ".ru", ".tk", ".xyz"]
    if any(d in url_lower for d in suspicious_domains):
        flags.append("Uses a shortened or unusual domain")

    known_boards = ["linkedin.com", "indeed.com", "rozee.pk", "glassdoor.com", "monster.com", "bayt.com"]
    if not any(d in url_lower for d in known_boards):
        flags.append("Not a widely recognized job board domain")

    return flags


def predict_fake_job(url: str, description_text: str) -> dict:
    """
    Predict whether a job posting is Fake or Real.

    Returns:
        {
            "label": "Fake" | "Real",
            "confidence": float (0-100),
            "url_flags": list[str],
            "model_loaded": bool
        }
    """
    model, vectorizer, scaler = load_fake_job_artifacts()

    if model is None:
        return {
            "label": "Unknown",
            "confidence": 0.0,
            "url_flags": _url_heuristics(url),
            "model_loaded": False,
        }

    clean_text = _clean_text(description_text)

    # Same 3 engineered numeric features used during training:
    # has_salary, desc_len, title_len
    has_salary = int(bool(re.search(r"(salary|pkr|rs\.?\s?\d|\$\s?\d)", description_text.lower())))
    desc_len   = len(description_text)
    first_line = description_text.split("\n")[0] if description_text else ""
    title_len  = len(first_line)

    numeric_features = np.array([[has_salary, desc_len, title_len]])

    text_vec   = vectorizer.transform([clean_text])
    num_scaled = scaler.transform(numeric_features)

    X = hstack([text_vec, csr_matrix(num_scaled)])

    proba = model.predict_proba(X)[0]
    pred  = model.predict(X)[0]

    fake_confidence = proba[1] * 100
    real_confidence = proba[0] * 100

    label = "Fake" if pred == 1 else "Real"
    confidence = fake_confidence if pred == 1 else real_confidence

    return {
        "label": label,
        "confidence": round(confidence, 1),
        "url_flags": _url_heuristics(url),
        "model_loaded": True,
    }
