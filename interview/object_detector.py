# ===========================================================
# interview/object_detector.py
# Detects prohibited objects (phone, book, remote, etc.) in the
# camera feed during an interview, using OpenCV's DNN module with
# a pretrained MobileNet-SSD-v3 model trained on COCO (91 classes).
#
# Model files expected in: interview/models/
#   - frozen_inference_graph.pb
#   - ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt
#   - coco.names
# ===========================================================

import os
import cv2
import streamlit as st

# NOTE: models/ lives at the project root (AI_SMART_EMOTION/models/),
# NOT inside interview/, so we go up one level from this file's directory.
_MODEL_DIR   = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "models"))

def _resolve_pb_path() -> str:
    """Prefer the correctly spelled weights file; fall back to legacy typo name."""
    for name in ("frozen_inference_graph.pb", "frozen_inderence_graph.pb"):
        path = os.path.join(_MODEL_DIR, name)
        if os.path.isfile(path):
            return path
    return os.path.join(_MODEL_DIR, "frozen_inference_graph.pb")


_PB_PATH     = _resolve_pb_path()
_PBTXT_PATH  = os.path.join(_MODEL_DIR, "ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt")
_NAMES_PATH  = os.path.join(_MODEL_DIR, "coco.names")

# Classes that should NOT be visible during an interview.
# Edit this set to add/remove flagged items.
FLAGGED_CLASSES = {
    "cell phone",
    "laptop",
    "book",
    "remote",
    "tv",
    "keyboard",
    "mouse",
}

CONFIDENCE_THRESHOLD = 0.55


@st.cache_resource
def load_object_detector():
    """Load the COCO SSD model + class names once, cache across reruns."""
    # Fail loudly if the model files aren't where we expect — this used to
    # be swallowed silently, which meant detection quietly did nothing.
    for path in (_PB_PATH, _PBTXT_PATH, _NAMES_PATH):
        if not os.path.isfile(path):
            print(f"[object_detector] Missing model file: {path}")
            st.error(f"⚠️ Object detection model file not found: `{path}`")
            return None, None

    try:
        net = cv2.dnn_DetectionModel(_PB_PATH, _PBTXT_PATH)
        net.setInputSize(320, 320)
        net.setInputScale(1.0 / 127.5)
        net.setInputMean((127.5, 127.5, 127.5))
        net.setInputSwapRB(True)

        with open(_NAMES_PATH, "r") as f:
            class_names = [line.strip() for line in f.readlines()]

        return net, class_names
    except Exception as e:
        print(f"[object_detector] Failed to load model: {e}")
        st.error(f"⚠️ Failed to load object detection model: {e}")
        return None, None


def detect_flagged_objects(frame) -> list:
    """
    Run object detection on a single BGR frame.
    Returns a list of flagged class names found (e.g. ["cell phone"]).
    Returns [] if the model isn't loaded or nothing flagged is found.
    """
    net, class_names = load_object_detector()
    if net is None:
        return []

    try:
        class_ids, confidences, boxes = net.detect(frame, confThreshold=CONFIDENCE_THRESHOLD)
    except Exception:
        return []

    found = []
    if len(class_ids) > 0:
        for class_id in class_ids.flatten():
            # coco.names is 0-indexed in the file, but class_id from
            # this model is 1-indexed (background implicitly excluded)
            idx = int(class_id) - 1
            if 0 <= idx < len(class_names):
                name = class_names[idx]
                if name in FLAGGED_CLASSES:
                    found.append(name)

    return list(set(found))