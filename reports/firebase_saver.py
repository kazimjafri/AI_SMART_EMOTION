# ===========================
# reports/firebase_saver.py
# Save interview report to Firebase Realtime DB
# ===========================

import streamlit as st


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

        from reports.post_interview import resolve_status_after_report

        # ── Save report to interview_reports node ──
        realtime_db.reference(f"interview_reports/{uid}/{app_key}").set(report_payload)

        # ── Auto-reject if below min_score, else Report Generated for recruiter review ──
        if app_key:
            resolve_status_after_report(
                realtime_db, uid, app_key, recruiter_uid, report_payload
            )

        return True

    except Exception as e:
        st.warning(f"⚠️ Could not save report to Firebase: {e}")
        return False