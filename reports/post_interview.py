# reports/post_interview.py — status resolution after interview report is saved
from datetime import datetime


def auto_reject_message(overall_score: int, min_score: int) -> str:
    return (
        f"Your overall AI interview score ({overall_score}%) did not meet the minimum "
        f"requirement ({min_score}%) for this role. Thank you for your interest — "
        f"we encourage you to explore other opportunities."
    )


def hire_message(job_title: str, company: str) -> str:
    company_part = f" at {company}" if company else ""
    return (
        f"Congratulations! You have been selected for the {job_title} role{company_part}. "
        f"The recruiter will be in touch with next steps."
    )


def manual_reject_message(job_title: str) -> str:
    return (
        f"Thank you for completing the interview for {job_title}. After careful review, "
        f"the recruiter has decided not to move forward with your application at this time."
    )


def resolve_status_after_report(
    realtime_db,
    candidate_uid: str,
    app_key: str,
    recruiter_uid: str,
    report_payload: dict,
) -> str:
    """
    After a report is saved:
    - score < min_score  → auto-reject with default message
    - score >= min_score → stay at Report Generated (recruiter decides manually)

    Returns the final application status.
    """
    overall_score = int(report_payload.get("overall_score", 0) or 0)
    now = datetime.utcnow().isoformat()

    cand_ref = realtime_db.reference(f"candidates/{candidate_uid}/applications/{app_key}")
    cand_app = cand_ref.get() or {}
    min_score = int(cand_app.get("min_score", 60) or 60)
    job_title = cand_app.get("job_title", report_payload.get("job_title", ""))

    report_fields = {
        "has_report": True,
        "overall_score": overall_score,
        "interview_report_url": f"firebase://interview_reports/{candidate_uid}/{app_key}",
        "dominant_emotion": report_payload.get("dominant_emotion", "Neutral"),
        "min_score": min_score,
    }

    recruiter_app_key = None
    if recruiter_uid:
        rec_apps = realtime_db.reference(f"recruiters/{recruiter_uid}/applications").get() or {}
        for k, v in rec_apps.items():
            if v.get("candidate_uid") == candidate_uid and v.get("candidate_app_key") == app_key:
                recruiter_app_key = k
                break
        if recruiter_app_key is None:
            for k, v in rec_apps.items():
                if v.get("candidate_uid") == candidate_uid:
                    recruiter_app_key = k
                    break

    if overall_score < min_score:
        status = "Rejected"
        status_message = auto_reject_message(overall_score, min_score)
        cand_update = {
            **report_fields,
            "status": status,
            "last_status_change": now,
            "status_message": status_message,
            "auto_rejected": True,
        }
        rec_update = {
            **report_fields,
            "status": status,
            "last_status_change": now,
            "auto_rejected": True,
        }
    else:
        status = "Report Generated"
        cand_update = {
            **report_fields,
            "status": status,
            "last_status_change": now,
        }
        rec_update = {
            **report_fields,
            "status": status,
            "last_status_change": now,
            "job_title": job_title or report_payload.get("job_title", ""),
        }

    cand_ref.update(cand_update)
    if recruiter_uid and recruiter_app_key:
        realtime_db.reference(
            f"recruiters/{recruiter_uid}/applications/{recruiter_app_key}"
        ).update(rec_update)

    return status
