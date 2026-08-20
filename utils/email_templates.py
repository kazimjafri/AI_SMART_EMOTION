# ===========================
# utils/email_templates.py
# Professional email templates (Option A style) for both
# application-stage and post-interview-stage notifications.
# Each function returns (subject, body) — recruiter can edit
# the body before sending from the dashboard.
# ===========================


def application_accepted_email(candidate_name, job_title, company, recruiter_name):
    subject = f"You've Been Shortlisted for {job_title} at {company} | © AI SMART EMOTION INTERVIEWER"
    body = f"""Dear {candidate_name},

Your application for the {job_title} position at {company} has been shortlisted. 

We would like to invite you to complete a short, AI-driven video interview. You can access the interview directly from your dashboard.

IMPORTANT RULES & REGULATIONS:
- 1. You have 48 hours to complete this interview from the time you receive this email.
- 2. A working Webcam and Microphone are mandatory. Ensure you are in a well-lit and quiet room.
- 3. Do NOT switch tabs during interview.
- 4. Violations: Switching tabs will result in a warning. A second violation will automatically terminate your interview and flag your application.

Please log in to your dashboard to start the process whenever you are ready.

Best regards,
{recruiter_name}
{company}
| © AI SMART EMOTION INTERVIEWER
"""
    return subject, body


def application_rejected_email(candidate_name: str, job_title: str, company: str, recruiter_name: str) -> tuple[str, str]:
    subject = f"Update on Your Application — {job_title} at {company} | © AI SMART EMOTION INTERVIEWER "
    body = f"""Dear {candidate_name},

Thank you for your interest in the {job_title} position at {company} and for taking the time to apply.

After careful review, we have decided to move forward with other candidates whose profiles more closely match our current requirements at this stage. This was not an easy decision, and we appreciate the effort you put into your application.

We encourage you to apply for future openings that match your profile, and we wish you the very best in your career journey.

Warm regards,
{recruiter_name}
{company}
| © AI SMART EMOTION INTERVIEWER
"""
    return subject, body


def interview_hired_email(candidate_name: str, job_title: str, company: str, recruiter_name: str) -> tuple[str, str]:
    subject = f"Congratulations! You've Been Selected — {job_title} at {company} | © AI SMART EMOTION INTERVIEWER"
    body = f"""Dear {candidate_name},

We are pleased to inform you that after careful review of your AI-conducted interview, you have been selected for the position of {job_title} at {company}.

Your performance during the interview process stood out, and we believe you would be a great addition to our team. Please find your interview evaluation report attached for your reference.

I will personally reach out to you shortly with the next steps, including onboarding details and documentation requirements.

Congratulations once again, and welcome aboard!

Best regards,
{recruiter_name}
{company}
| © AI SMART EMOTION INTERVIEWER"""
    return subject, body


def interview_rejected_email(candidate_name: str, job_title: str, company: str, recruiter_name: str) -> tuple[str, str]:
    subject = f"Update on Your Application — {job_title} at {company} | © AI SMART EMOTION INTERVIEWER"
    body = f"""Dear {candidate_name},

Thank you for taking the time to complete the AI interview for the {job_title} position at {company}. We appreciate the effort and thought you put into your responses.

After careful consideration, we have decided to move forward with another candidate whose profile more closely matches our current requirements. This was not an easy decision, as we were impressed by several aspects of your interview.

Please find your interview evaluation report attached — we hope it gives you useful insight into your performance. We encourage you to apply for future openings that match your profile, and we wish you the very best in your career journey.

Warm regards,
{recruiter_name}
{company}
| © AI SMART EMOTION INTERVIEWER"""
    return subject, body


def auto_rejected_email(candidate_name: str, job_title: str, company: str, overall_score: int, min_score: int) -> tuple[str, str]:
    """Fixed template — used only for the automatic below-threshold rejection, no recruiter editing."""
    subject = f"Update on Your Application — {job_title} at {company} | © AI SMART EMOTION INTERVIEWER"
    body = f"""Dear {candidate_name},

Thank you for completing the AI interview for the {job_title} position at {company}.

After reviewing your interview evaluation, your overall score ({overall_score}%) did not meet the minimum requirement ({min_score}%) set for this role. As a result, we will not be moving forward with your application at this time.

Please find your full interview evaluation report attached for your reference — it includes a detailed breakdown of your responses and feedback that may be useful for future interviews.

We encourage you to apply for future openings that match your profile, and we wish you the very best in your career journey.

Regards,
The Recruitment Team
{company}
| © AI SMART EMOTION INTERVIEWER"""
    return subject, body