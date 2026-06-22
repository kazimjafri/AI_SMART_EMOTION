# ===========================
# interview/emotion_tracker.py
# Real-time Face · Emotion · Confidence tracking
# Camera capture happens IN THE CANDIDATE'S BROWSER via WebRTC
# (streamlit-webrtc) — frames are streamed to the server for
# DeepFace analysis, then streamed back for display.
# ===========================

import threading
from datetime import datetime
from collections import Counter

import cv2
import numpy as np
import av
from streamlit_webrtc import VideoProcessorBase


# ───────────────────────────────────────────
# DEEPFACE EMOTION → NORMALIZED SCORES
# ───────────────────────────────────────────

# DeepFace emotions mapped to interview-relevant scores
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


def _analyze_frame(frame: np.ndarray) -> dict | None:
    """
    Run DeepFace on a single BGR frame.
    Returns normalized interview emotion dict or None on failure.
    """
    try:
        from deepface import DeepFace

        results = DeepFace.analyze(
            frame,
            actions=["emotion"],
            enforce_detection=False,
            silent=True,
        )

        if not results:
            return None

        face_data    = results[0] if isinstance(results, list) else results
        raw_emotions = face_data.get("emotion", {})
        dominant     = face_data.get("dominant_emotion", "neutral").lower()

        # Build confidence/anxiety/neutral from dominant emotion
        base = _EMOTION_MAP.get(dominant, {"confidence": 50, "anxiety": 20, "neutral": 30})

        # Refine using raw scores (fear + sad = more anxiety, happy = more confidence)
        fear_pct    = raw_emotions.get("fear",    0)
        happy_pct   = raw_emotions.get("happy",   0)
        neutral_pct = raw_emotions.get("neutral", 0)
        sad_pct     = raw_emotions.get("sad",     0)
        angry_pct   = raw_emotions.get("angry",   0)

        confidence = int(min(98, max(5,
            base["confidence"]
            + happy_pct   * 0.3
            - fear_pct    * 0.4
            - sad_pct     * 0.2
        )))
        anxiety = int(min(95, max(2,
            base["anxiety"]
            + fear_pct    * 0.5
            + sad_pct     * 0.2
            + angry_pct   * 0.2
            - happy_pct   * 0.2
        )))
        composed = max(0, 100 - confidence - anxiety)

        return {
            "timestamp":        datetime.utcnow().isoformat(),
            "dominant_emotion": _INTERVIEW_EMOTION_LABELS.get(dominant, "Neutral"),
            "raw_dominant":     dominant,
            "confidence":       confidence,
            "anxiety":          anxiety,
            "composed":         composed,
            "raw_emotions":     {k: round(v, 1) for k, v in raw_emotions.items()},
        }

    except Exception:
        return None


# ───────────────────────────────────────────
# BROWSER-SIDE VIDEO PROCESSOR
# This class receives the candidate's actual webcam frames
# (sent from their browser over WebRTC), runs DeepFace on a
# sample of them, and streams the (lightly annotated) frame back.
# recv() runs on a background thread managed by streamlit-webrtc,
# so all shared state is protected by a lock.
# ───────────────────────────────────────────

class EmotionVideoProcessor(VideoProcessorBase):
    def __init__(self):
        self.lock = threading.Lock()
        self.frame_count = 0
        self.sample_every_n_frames = 60   # ~ every 2-4s depending on browser fps
        self.latest_result: dict | None = None
        self.timeline: list[dict] = []

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)  # mirror horizontally so it feels like a normal selfie view

        self.frame_count += 1
        if self.frame_count % self.sample_every_n_frames == 0:
            result = _analyze_frame(img)
            if result:
                with self.lock:
                    self.latest_result = result
                    self.timeline.append(result)

        # Light overlay: REC dot + last detected state (purely cosmetic)
        with self.lock:
            label = self.latest_result["dominant_emotion"] if self.latest_result else "Detecting..."

        try:
            cv2.circle(img, (24, 24), 7, (40, 40, 235), -1)
            cv2.putText(img, "REC", (38, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(img, label, (38, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (153, 211, 52), 1, cv2.LINE_AA)
        except Exception:
            pass

        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def get_timeline(self) -> list[dict]:
        with self.lock:
            return list(self.timeline)

    def get_latest(self) -> dict | None:
        with self.lock:
            return self.latest_result

    def reset(self):
        """Call this when a new interview attempt starts, to clear stale data."""
        with self.lock:
            self.timeline = []
            self.latest_result = None
            self.frame_count = 0


# ───────────────────────────────────────────
# TIMELINE SUMMARY  (called at interview end — unchanged)
# ───────────────────────────────────────────

def compute_emotion_summary(timeline: list[dict]) -> dict:
    """
    Aggregate the collected emotion timeline into a final summary.
    Returns dict with averages, peak values, dominant emotion, and
    per-question emotion data ready for PDF report.
    """
    if not timeline:
        return {
            "avg_confidence":       50,
            "avg_anxiety":          20,
            "avg_composed":         30,
            "peak_confidence":      50,
            "peak_anxiety":         20,
            "dominant_emotion":     "Neutral",
            "emotion_distribution": {},
            "overall_score":        50,
            "timeline":             [],
            "assessment":           "No emotion data collected.",
        }

    confidences = [r["confidence"] for r in timeline]
    anxieties   = [r["anxiety"]    for r in timeline]
    composeds   = [r["composed"]   for r in timeline]
    emotions    = [r["dominant_emotion"] for r in timeline]

    avg_conf  = int(sum(confidences) / len(confidences))
    avg_anx   = int(sum(anxieties)   / len(anxieties))
    avg_comp  = int(sum(composeds)   / len(composeds))
    peak_conf = max(confidences)
    peak_anx  = max(anxieties)

    # Dominant emotion = most frequent
    emotion_counts       = Counter(emotions)
    dominant_emotion     = emotion_counts.most_common(1)[0][0]
    emotion_distribution = {k: round(v / len(emotions) * 100) for k, v in emotion_counts.items()}

    # Overall interview emotion score (0-100)
    # Higher confidence + lower anxiety = better score
    overall_score = int(min(98, max(5,
        avg_conf * 0.6
        - avg_anx  * 0.3
        + avg_comp * 0.1
        + 20   # base offset
    )))

    # Assessment text
    if overall_score >= 75:
        assessment = "Excellent composure — candidate appeared confident and in control throughout."
    elif overall_score >= 55:
        assessment = "Good overall presence with some moments of visible stress."
    elif overall_score >= 35:
        assessment = "Moderate composure — noticeable anxiety detected at key points."
    else:
        assessment = "High anxiety levels detected — candidate may benefit from mock interview practice."

    return {
        "avg_confidence":       avg_conf,
        "avg_anxiety":          avg_anx,
        "avg_composed":         avg_comp,
        "peak_confidence":      peak_conf,
        "peak_anxiety":         peak_anx,
        "dominant_emotion":     dominant_emotion,
        "emotion_distribution": emotion_distribution,
        "overall_score":        overall_score,
        "timeline":             timeline,
        "assessment":           assessment,
        "total_samples":        len(timeline),
    }