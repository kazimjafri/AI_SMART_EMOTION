# ===========================
# interview/emotion_tracker.py
# Real-time Face · Emotion · Confidence tracking
# ===========================

import threading
import time
from datetime import datetime
from collections import Counter

import cv2
import numpy as np
import av
import streamlit as st
from streamlit_webrtc import VideoProcessorBase

from interview.object_detector import detect_flagged_objects

# ── Limit CPU thread usage ──
# DeepFace/TensorFlow and OpenCV's DNN backend will otherwise grab
# every available CPU core during each inference call, starving the
# audio-capture thread of CPU time and causing choppy/dropped audio.
# Capping threads here leaves headroom for audio + Streamlit + UI.
cv2.setNumThreads(2)
try:
    import tensorflow as tf
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.threading.set_inter_op_parallelism_threads(2)
except Exception:
    pass

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

def _analyze_frame(frame: np.ndarray, skip_detection: bool = False) -> dict | None:
    """Analyze frame for emotions if face is detected[cite: 5].

    skip_detection=True: pass this when `frame` is already a cropped face
    (e.g. from our own Haar Cascade result) — avoids DeepFace running its
    own (heavier) internal face detector a second time on the same frame.
    """
    try:
        DeepFace = preload_deepface()
        backend = "skip" if skip_detection else "opencv"
        results = DeepFace.analyze(frame, actions=["emotion"], enforce_detection=False, detector_backend=backend, silent=True)
        
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
        self.sample_every_n_frames = 75
        self.latest_result = None
        self.timeline = []

        # Object detection state
        # NOTE: time-based (not frame-count-based) so detection runs on a
        # predictable ~1.5s cadence no matter how the actual delivered
        # camera fps fluctuates (which varies a lot under CPU load from
        # DeepFace/face-detection running on this same pipeline). With
        # frame-count sampling, a drop in effective fps silently stretches
        # the real-world gap between checks (e.g. 30 frames at a throttled
        # ~1.5fps == 20 seconds) — this was the cause of the long delay
        # before an object alert first appeared.
        self.object_check_interval_sec = 1.5
        self._last_object_check = 0.0
        self.object_alert = []          # list of flagged class names currently visible
        self.object_alert_log = []      # every distinct alert seen, for the final report

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)
        self.frame_count += 1

        # ── Object detection (phone / laptop / book etc.) ──
        now = time.time()
        if now - self._last_object_check >= self.object_check_interval_sec:
            self._last_object_check = now
            flagged = detect_flagged_objects(img)
            with self.lock:
                self.object_alert = flagged
                for name in flagged:
                    if name not in self.object_alert_log:
                        self.object_alert_log.append(name)

        # NOTE: no longer drawing the alert banner onto the video frame itself —
        # the camera widget is small and long messages got cut off. The alert
        # is now rendered as a normal Streamlit element below the camera
        # (see _render_object_alert_banner in interview_engine.py), which has
        # full width and never truncates.

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
                # Crop to the (largest) detected face + small margin, and tell
                # DeepFace to skip its own internal face detector (detector_backend
                # "skip") since we already located the face with Haar Cascade above.
                # This avoids running face detection twice per sample.
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                m = int(0.15 * max(w, h))  # margin so the crop isn't too tight
                y1, y2 = max(0, y - m), min(img.shape[0], y + h + m)
                x1, x2 = max(0, x - m), min(img.shape[1], x + w + m)
                face_crop = img[y1:y2, x1:x2]

                result = _analyze_frame(face_crop, skip_detection=True) if face_crop.size else None
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
            self._last_object_check = 0.0
            self.object_alert = []
            self.object_alert_log = []

def compute_emotion_summary(timeline):
    """Aggregate collected emotion data for the report[cite: 5]."""
    if not timeline:
        return {
            "avg_confidence": 50, "avg_anxiety": 20, "avg_composed": 30,
            "dominant_emotion": "Neutral", "overall_score": 50,
            "assessment": "No camera/emotion data was captured for this interview.",
            "total_samples": 0, "timeline": [],
        }

    confidences = [r["confidence"] for r in timeline]
    anxieties   = [r["anxiety"]    for r in timeline]
    composures  = [r.get("composed", max(0, 100 - r["confidence"] - r["anxiety"])) for r in timeline]
    emotions    = [r["dominant_emotion"] for r in timeline]

    avg_conf = int(sum(confidences) / len(confidences))
    avg_anx  = int(sum(anxieties) / len(anxieties))
    avg_comp = int(sum(composures) / len(composures))
    emotion_counts = Counter(emotions)

    # Behavioral sub-score (0-100): blends confidence and composure.
    # High anxiety already pulls both of these down (see _analyze_frame's
    # formula), so this naturally reflects a calm + confident presence.
    behavioral_score = max(0, min(100, round((avg_conf + avg_comp) / 2)))

    if behavioral_score >= 75:
        assessment = "Confident and composed throughout the interview."
    elif behavioral_score >= 55:
        assessment = "Generally composed, with some moments of visible nervousness."
    elif behavioral_score >= 35:
        assessment = "Noticeable signs of anxiety were observed during the interview."
    else:
        assessment = "High anxiety levels observed — significant nervousness throughout."

    return {
        "avg_confidence":   avg_conf,
        "avg_anxiety":      avg_anx,
        "avg_composed":     avg_comp,
        "dominant_emotion": emotion_counts.most_common(1)[0][0],
        "overall_score":    behavioral_score,
        "assessment":       assessment,
        "total_samples":    len(timeline),
        "timeline":         timeline,
    }