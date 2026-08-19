# ===========================
# utils/email_sender.py
# Gmail SMTP sender — used for both application-stage and
# post-interview-stage candidate notification emails.
# ===========================

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from dotenv import load_dotenv
from firebase_admin import db as realtime_db

load_dotenv()

EMAIL_ADDRESS      = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT   = 587


def get_candidate_email(candidate_uid: str) -> str:
    """Fetch the candidate's registered email from Firebase (users/{uid}/email)."""
    try:
        email = realtime_db.reference(f"users/{candidate_uid}/email").get()
        return email or ""
    except Exception:
        return ""


def send_email(
    to_email: str,
    subject: str,
    body: str,
    pdf_bytes: bytes = None,
    pdf_filename: str = "Interview_Report.pdf",
    reply_to: str = None,
    sender_display_name: str = None,
) -> tuple[bool, str]:
    """
    Sends a plain-text email via Gmail SMTP, with an optional PDF attachment.
    Returns (success: bool, message: str).
    """
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        return False, "Email credentials not configured. Add EMAIL_ADDRESS and EMAIL_APP_PASSWORD to your .env file."

    if not to_email or "@" not in to_email:
        return False, "No valid candidate email address found."

    try:
        msg = MIMEMultipart()
        msg["From"]    = f"{sender_display_name} <{EMAIL_ADDRESS}>" if sender_display_name else EMAIL_ADDRESS
        msg["To"]      = to_email
        msg["Subject"] = subject
        if reply_to:
            msg["Reply-To"] = reply_to

        msg.attach(MIMEText(body, "plain"))

        if pdf_bytes:
            attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
            attachment.add_header(
                "Content-Disposition", "attachment", filename=pdf_filename
            )
            msg.attach(attachment)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.send_message(msg)

        return True, "Email sent successfully."

    except smtplib.SMTPAuthenticationError:
        return False, "Gmail authentication failed. Check EMAIL_ADDRESS / EMAIL_APP_PASSWORD in .env."
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"