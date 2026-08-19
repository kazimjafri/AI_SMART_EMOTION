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


def _send_auto_reject_email(candidate_uid, cand_app, report_payload, overall_score, min_score):
    """
    Fires automatically the moment an interview is auto-rejected (score below
    threshold) — no recruiter involved, so this uses the fixed template and
    attaches the freshly generated PDF report.
    Any failure here is swallowed so it never blocks status resolution.
    """
    try:
        from utils.email_sender import send_email, get_candidate_email
        from utils.email_templates import auto_rejected_email
        from reports.pdf_generator import generate_interview_report_pdf

        candidate_email = get_candidate_email(candidate_uid)
        if not candidate_email:
            return

        candidate_name = report_payload.get("candidate_name", "Candidate")
        job_title = cand_app.get("job_title", report_payload.get("job_title", ""))
        company = cand_app.get("company_name", report_payload.get("company_name", ""))

        questions_data = report_payload.get("questions_data", [])
        questions = [{"question": r.get("question", ""), "category": r.get("category", ""), "expected_keywords": []} for r in questions_data]
        answers   = {i: r.get("answer", "") for i, r in enumerate(questions_data)}
        scores    = {i: {"score": r.get("score", 0), "correct": r.get("correct", False), "feedback": r.get("feedback", "")} for i, r in enumerate(questions_data)}

        emotion_summary = {
            "total_samples":    1,
            "avg_confidence":   report_payload.get("avg_confidence", 0),
            "avg_anxiety":      report_payload.get("avg_anxiety", 0),
            "avg_composed":     report_payload.get("avg_composed", 0),
            "dominant_emotion": report_payload.get("dominant_emotion", "Neutral"),
            "overall_score":    report_payload.get("emotion_behavioral_score", 50),
            "assessment":       report_payload.get("emotion_assessment", ""),
        }

        pdf_bytes = generate_interview_report_pdf(
            candidate_name=candidate_name,
            job_title=job_title,
            company=company,
            questions=questions,
            answers=answers,
            scores=scores,
            completed_at=report_payload.get("completed_at", ""),
            emotion_summary=emotion_summary,
            overall_score=overall_score,
        )

        subject, body = auto_rejected_email(candidate_name, job_title, company, overall_score, min_score)
        send_email(
            to_email=candidate_email,
            subject=subject,
            body=body,
            pdf_bytes=pdf_bytes,
            pdf_filename=f"InterviewAI_{candidate_name.replace(' ', '_')}_Report.pdf",
        )
    except Exception:
        # Never let email failure break the interview status flow
        pass


def resolve_status_after_report(
    realtime_db,
    candidate_uid: str,
    app_key: str,
    recruiter_uid: str,
    report_payload: dict,
) -> str:
    """
    After a report is saved:
    - score < min_score  → auto-reject with default message + auto-send rejection email w/ PDF
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

    if overall_score < min_score:
        _send_auto_reject_email(candidate_uid, cand_app, report_payload, overall_score, min_score)

    return status