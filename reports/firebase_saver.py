# ===========================
# reports/firebase_saver.py
# Save interview report to Firebase Realtime DB
# ===========================

import streamlit as st
from datetime import datetime


def save_interview_report(
    uid: str,
    app_key: str,
    recruiter_uid: str,
    report_payload: dict,
) -> bool:
    """
    Save full interview report to Firebase RTDB.
    Updates candidate application status to 'Report Generated'.
    Updates recruiter's application node with score + report flag.
    Returns True on success.
    """
    try:
        from firebase_admin import db as realtime_db

        now = datetime.utcnow().isoformat()

        # ── Save report to interview_reports node ──
        realtime_db.reference(f"interview_reports/{uid}/{app_key}").set(report_payload)

        # ── Update candidate application status ──
        if app_key:
            realtime_db.reference(f"candidates/{uid}/applications/{app_key}").update({
                "status":             "Report Generated",
                "last_status_change": now,
                "has_report":         True,
                "overall_score":      report_payload.get("overall_score", 0),
                "interview_report_url": f"firebase://interview_reports/{uid}/{app_key}",
            })

        # ── Update recruiter application node ──
        if recruiter_uid:
            rec_apps = realtime_db.reference(f"recruiters/{recruiter_uid}/applications").get()
            if rec_apps:
                for k, v in rec_apps.items():
                    if v.get("candidate_uid") == uid:
                        realtime_db.reference(
                            f"recruiters/{recruiter_uid}/applications/{k}"
                        ).update({
                            "status":         "Report Generated",
                            "has_report":     True,
                            "last_status_change": now,
                            "overall_score":  report_payload.get("overall_score", 0),
                            "avg_confidence": report_payload.get("avg_confidence", 0),
                            "avg_anxiety":    report_payload.get("avg_anxiety",    0),
                            "dominant_emotion": report_payload.get("dominant_emotion", "Neutral"),
                        })
                        break

        return True

    except Exception as e:
        st.warning(f"⚠️ Could not save report to Firebase: {e}")
        return False