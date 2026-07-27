# ===========================
# interview/emotion_tracker.py
# Real-time Face · Emotion · Confidence tracking
# ===========================

import threading
from datetime import datetime
from collections import Counter

import cv2
import numpy as np
import av
import streamlit as st
from streamlit_webrtc import VideoProcessorBase

from interview.object_detector import detect_flagged_objects

# Haar Cascade load karna (Fast face detection ke liye)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# ───────────────────────────────────────────
# DEEPFACE EMOTION → NORMALIZED SCORES
# ───────────────────────────────────────────

_EMOTION_MAP = {
    "happy":    {"confidence": 80, "anxiety": 10, "neutral": 10},
    "neutral":  {"confidence": 60, "anxiety": 15, "neutral": 25},
    "surprise": {"confidence": 55, "anxiety": 30, "neutral": 15},
    "sad":      {"confidence": 25, "anxiety": 50, "neutral": 25},
    "angry":    {"confidence": 40, "anxiety": 55, "neutral":  5},
    "fear":     {"confidence": 10, "anxiety": 85, "neutral":  5},
    "disgust":  {"confidence": 20, "anxiety": 60, "neutral": 20},
}

_INTERVIEW_EMOTION_LABELS = {
    "happy":    "Confident",
    "neutral":  "Composed",
    "surprise": "Engaged",
    "sad":      "Stressed",
    "angry":    "Tense",
    "fear":     "Anxious",
    "disgust":  "Uncomfortable",
}

@st.cache_resource
def preload_deepface():
    """Preload DeepFace to avoid lag on first frame analysis[cite: 5]."""
    from deepface import DeepFace
    dummy_img = np.zeros((224, 224, 3), dtype=np.uint8)
    try:
        DeepFace.analyze(dummy_img, actions=["emotion"], enforce_detection=False, silent=True)
    except Exception:
        pass
    return DeepFace

def _analyze_frame(frame: np.ndarray) -> dict | None:
    """Analyze frame for emotions if face is detected[cite: 5]."""
    try:
        DeepFace = preload_deepface()
        results = DeepFace.analyze(frame, actions=["emotion"], enforce_detection=False, silent=True)
        
        if not results: return None
        face_data = results[0] if isinstance(results, list) else results
        raw_emotions = face_data.get("emotion", {})
        dominant = face_data.get("dominant_emotion", "neutral").lower()

        base = _EMOTION_MAP.get(dominant, {"confidence": 50, "anxiety": 20, "neutral": 30})
        fear_pct, happy_pct = raw_emotions.get("fear", 0), raw_emotions.get("happy", 0)
        sad_pct, angry_pct = raw_emotions.get("sad", 0), raw_emotions.get("angry", 0)

        confidence = int(min(98, max(5, base["confidence"] + happy_pct * 0.3 - fear_pct * 0.4 - sad_pct * 0.2)))
        anxiety = int(min(95, max(2, base["anxiety"] + fear_pct * 0.5 + sad_pct * 0.2 + angry_pct * 0.2 - happy_pct * 0.2)))
        composed = max(0, 100 - confidence - anxiety)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "dominant_emotion": _INTERVIEW_EMOTION_LABELS.get(dominant, "Neutral"),
            "confidence": confidence,
            "anxiety": anxiety,
            "composed": composed,
        }
    except Exception:
        return None

class EmotionVideoProcessor(VideoProcessorBase):
    def __init__(self):
        self.lock = threading.Lock()
        self.frame_count = 0
        self.sample_every_n_frames = 60
        self.latest_result = None
        self.timeline = []

        # Object detection state
        self.object_sample_every_n_frames = 20
        self.object_alert = []          # list of flagged class names currently visible
        self.object_alert_log = []      # every distinct alert seen, for the final report

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)
        self.frame_count += 1

        # ── Object detection (phone / laptop / book etc.) ──
        if self.frame_count % self.object_sample_every_n_frames == 0:
            flagged = detect_flagged_objects(img)
            with self.lock:
                self.object_alert = flagged
                for name in flagged:
                    if name not in self.object_alert_log:
                        self.object_alert_log.append(name)

        with self.lock:
            current_alert = list(self.object_alert)

        if current_alert:
            alert_text = f"OBJECT DETECTED: {', '.join(current_alert).upper()} — PLEASE REMOVE IT"
            cv2.rectangle(img, (0, 0), (img.shape[1], 36), (0, 0, 200), -1)
            cv2.putText(img, alert_text, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)

        # 1. Fast Face Detection
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        face_detected = len(faces) > 0

        if not face_detected:
            # 2. Alert if no face
            cv2.putText(img, "NO FACE DETECTED!", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
            cv2.putText(img, "Please look into the camera", (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
        else:
            # 3. Analyze Emotion only when face exists[cite: 5]
            if self.frame_count % self.sample_every_n_frames == 0:
                result = _analyze_frame(img)
                if result:
                    with self.lock:
                        self.latest_result = result
                        self.timeline.append(result)

            # 4. Display Metrics on Camera
            with self.lock:
                if self.latest_result:
                    cv2.putText(img, f"Conf: {self.latest_result['confidence']}%", (38, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    cv2.putText(img, f"Anxiety: {self.latest_result['anxiety']}%", (38, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                    cv2.putText(img, f"State: {self.latest_result['dominant_emotion']}", (38, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        # REC Indicator
        cv2.circle(img, (24, 24), 7, (40, 40, 235), -1)
        cv2.putText(img, "REC", (38, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def get_timeline(self):
        with self.lock: return list(self.timeline)

    def get_object_alert(self):
        """Returns the list of flagged objects currently visible (empty list = all clear)."""
        with self.lock:
            return list(self.object_alert)

    def get_object_alert_log(self):
        """Returns every distinct flagged object seen at any point during the interview."""
        with self.lock:
            return list(self.object_alert_log)

    def reset(self):
        with self.lock:
            self.timeline = []
            self.latest_result = None
            self.frame_count = 0
            self.object_alert = []
            self.object_alert_log = []

def compute_emotion_summary(timeline):
    """Aggregate collected emotion data for the report[cite: 5]."""
    if not timeline: 
        return {"avg_confidence": 50, "avg_anxiety": 20, "dominant_emotion": "Neutral"}
    
    confidences = [r["confidence"] for r in timeline]
    anxieties   = [r["anxiety"]    for r in timeline]
    emotions    = [r["dominant_emotion"] for r in timeline]
    
    avg_conf = int(sum(confidences) / len(confidences))
    avg_anx  = int(sum(anxieties) / len(anxieties))
    emotion_counts = Counter(emotions)
    
    return {
        "avg_confidence": avg_conf,
        "avg_anxiety": avg_anx,
        "dominant_emotion": emotion_counts.most_common(1)[0][0],
        "total_samples": len(timeline)
    }