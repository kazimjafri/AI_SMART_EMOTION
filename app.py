# ===========================
# IMPORTS
# ===========================
import streamlit as st
import cv2
from deepface import DeepFace
import speech_recognition as sr
import pyttsx3
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, db as realtime_db
import pyrebase
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
import os
import time
import tempfile
import base64
from datetime import datetime

from interview.interview_engine import render_interview_page
from dashboard.candidate import render_candidate_dashboard
from dashboard.recruiter import render_recruiter_dashboard

# Google Cloud Firestore
try:
    from google.cloud import firestore as gcloud_firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False

# ===========================
# FONT AWESOME
# ===========================
st.markdown(
    '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">',
    unsafe_allow_html=True
)

# ===========================
# PAGE CONFIG
# ===========================
st.set_page_config(
    page_title="AI Interview Assistant",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===========================
# FIREBASE INITIALIZATION
# ===========================
if firebase_admin._apps:
    firebase_admin.delete_app(firebase_admin.get_app())

cred = credentials.Certificate("ServiceAccountKey.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://aiemotioninterviewer-default-rtdb.firebaseio.com"
})

firebaseConfig = {
    "apiKey":            "AIzaSyAnlL4zPDarYCNOZp2j33mdkWWwaqDH93c",
    "authDomain":        "aiemotioninterviewer.firebaseapp.com",
    "databaseURL":       "https://aiemotioninterviewer-default-rtdb.firebaseio.com",
    "projectId":         "aiemotioninterviewer",
    "storageBucket":     "aiemotioninterviewer.firebasestorage.app",
    "messagingSenderId": "434777979901",
    "appId":             "1:434777979901:web:020bde1dc5e1086f317794"
}

firebase_app  = pyrebase.initialize_app(firebaseConfig)
client_auth   = firebase_app.auth()
pyrebase_db   = firebase_app.database()

# ===========================
# FIRESTORE CLIENT (optional)
# ===========================
def get_firestore_client():
    if not FIRESTORE_AVAILABLE:
        return None
    try:
        return gcloud_firestore.Client(project="aiemotioninterviewer")
    except Exception:
        return None

# ===========================
# SESSION STATE
# ===========================
defaults = {
    "logged_in":                False,
    "user_name":                "",
    "user_email":               "",
    "user_role":                "",
    "user_uid":                 "",
    "id_token":                 "",
    "current_page":             "home",
    "dark_mode":                True,
    "profile_setup":            False,
    "active_dash_tab":          "Overview",
    "goto_profile_tab":         False,
    # Recruiter-specific
    "recruiter_profile_setup":  False,
    "recruiter_active_tab":     "Profile",
    "selected_candidate_uid":   None,
    # Candidate-specific
    "last_seen_timestamp":      "",
    "job_interview_context":    None,
    # Recruiter nav
    "_rec_goto_post":           False,
    "_rec_goto_applications":   False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ===========================
# HELPERS
# ===========================
def navigate_to(page: str):
    st.session_state.current_page = page
    st.rerun()

def toggle_theme():
    st.session_state.dark_mode = not st.session_state.dark_mode
    st.rerun()

# ===========================
# FIREBASE AUTH FUNCTIONS
# ===========================
def firebase_login(email: str, password: str) -> bool:
    try:
        user     = client_auth.sign_in_with_email_and_password(email, password)
        uid      = user["localId"]
        id_token = user["idToken"]
    except Exception as e:
        err = str(e)
        if "INVALID_PASSWORD" in err or "EMAIL_NOT_FOUND" in err or "INVALID_LOGIN_CREDENTIALS" in err:
            st.error("❌ Invalid email or password.")
        elif "TOO_MANY_ATTEMPTS_TRY_LATER" in err:
            st.error("⚠️ Too many attempts. Try again later.")
        elif "USER_DISABLED" in err:
            st.error("🚫 This account has been disabled.")
        else:
            st.error(f"❌ Login failed: {err}")
        return False
  
    try:
        snapshot = realtime_db.reference(f"users/{uid}").get()
        if snapshot:
            name  = snapshot.get("name",  email.split("@")[0].title())
            role  = snapshot.get("role",  "Candidate")
            candidate_profile = snapshot.get("candidate_profile", {})
            profile_setup = bool(candidate_profile and candidate_profile.get("profile_complete", False))
        else:
            name  = email.split("@")[0].title()
            role  = "Candidate"
            profile_setup = False
    except Exception:
        name  = email.split("@")[0].title()
        role  = "Candidate"
        profile_setup = False

    st.session_state.logged_in     = True
    st.session_state.user_name     = name
    st.session_state.user_email    = email
    st.session_state.user_role     = role
    st.session_state.user_uid      = uid
    st.session_state.id_token      = id_token
    st.session_state.profile_setup = profile_setup

    try:
        last_seen_snap = realtime_db.reference(f"users/{uid}/last_seen").get()
        st.session_state.last_seen_timestamp = last_seen_snap if last_seen_snap else ""
    except Exception:
        st.session_state.last_seen_timestamp = ""

    if role == "Recruiter":
        try:
            rec_snap = realtime_db.reference(f"recruiters/{uid}").get()
            st.session_state.recruiter_profile_setup = bool(
                rec_snap and rec_snap.get("profile_complete", False)
            )
        except Exception:
            st.session_state.recruiter_profile_setup = False

    return True


def firebase_register(name: str, email: str, password: str, role: str) -> bool:
    try:
        user     = client_auth.create_user_with_email_and_password(email, password)
        uid      = user["localId"]
        id_token = user["idToken"]
    except Exception as e:
        err = str(e)
        if "CONFIGURATION_NOT_FOUND" in err:
            st.error("⚠️ Email/Password sign-in not enabled in Firebase Console.")
        elif "EMAIL_EXISTS" in err:
            st.error("❌ Email already registered. Please log in.")
        elif "WEAK_PASSWORD" in err:
            st.error("⚠️ Password must be at least 6 characters.")
        elif "INVALID_EMAIL" in err:
            st.error("❌ Please enter a valid email address.")
        else:
            st.error(f"❌ Registration failed: {err}")
        return False

    try:
        profile_data = {
            "uid":        uid,
            "name":       name,
            "email":      email,
            "role":       role,
            "created_at": datetime.utcnow().isoformat(),
            "interviews": 0,
        }
        realtime_db.reference(
            f"users/{uid}",
            url="https://aiemotioninterviewer-default-rtdb.firebaseio.com"
        ).set(profile_data)
        return True
    except Exception as e:
        st.error(f"❌ Account created but profile save failed: {str(e)}")
        return True


def firebase_logout():
    uid = st.session_state.get("user_uid", "")
    if uid:
        try:
            realtime_db.reference(f"users/{uid}/last_seen").set(
                datetime.utcnow().isoformat()
            )
        except Exception:
            pass

    for key in ["logged_in", "user_name", "user_email",
                "user_role", "user_uid", "id_token",
                "profile_setup", "recruiter_profile_setup"]:
        st.session_state[key] = "" if key not in ("logged_in", "profile_setup", "recruiter_profile_setup") else False
    st.session_state.active_dash_tab       = "Overview"
    st.session_state.recruiter_active_tab  = "Profile"
    st.session_state.last_seen_timestamp   = ""
    st.session_state.job_interview_context = None
    st.session_state._rec_goto_post        = False
    st.session_state._rec_goto_applications= False
    navigate_to("home")


# ===========================
# CSS — MINIMAL LIGHT THEME
# ===========================
def inject_css(dark: bool):
    if dark:
        bg_body         = "#0c1410"
        bg_sidebar      = "#0e1812"
        bg_card         = "#131f18"
        bg_card_2       = "#162118"
        border_col      = "#1f3328"
        border_subtle   = "#1a2c22"
        text_h          = "#e6f2ec"
        text_body       = "#8cb8a0"
        text_muted      = "#3d6b52"
        text_mono       = "#34d399"
        accent          = "#34d399"
        accent_soft     = "#10b981"
        accent_bg       = "rgba(52,211,153,0.08)"
        accent_bg2      = "rgba(52,211,153,0.14)"
        btn_bg          = "#10b981"
        btn_txt         = "#ffffff"
        btn_hover       = "#0d9e6e"
        sidebar_active  = "rgba(52,211,153,0.12)"
        tag_bg          = "rgba(52,211,153,0.10)"
        tag_border      = "rgba(52,211,153,0.22)"
        tag_txt         = "#34d399"
        input_bg        = "#101d15"
        input_border    = "#1f3328"
        divider         = "#1a2c22"
        shadow_card     = "0 1px 3px rgba(0,0,0,0.4), 0 4px 16px rgba(0,0,0,0.25)"
        shadow_hover    = "0 4px 12px rgba(0,0,0,0.5), 0 12px 32px rgba(0,0,0,0.3)"
        mono_label_bg   = "rgba(52,211,153,0.07)"
    else:
        bg_body         = "#f5faf7"
        bg_sidebar      = "#ffffff"
        bg_card         = "#ffffff"
        bg_card_2       = "#f9fcfa"
        border_col      = "#e2ede8"
        border_subtle   = "#edf5f0"
        text_h          = "#0d2218"
        text_body       = "#4a7060"
        text_muted      = "#8fb5a2"
        text_mono       = "#0a7a4e"
        accent          = "#059669"
        accent_soft     = "#10b981"
        accent_bg       = "rgba(5,150,105,0.06)"
        accent_bg2      = "rgba(5,150,105,0.10)"
        btn_bg          = "#059669"
        btn_txt         = "#ffffff"
        btn_hover       = "#047857"
        sidebar_active  = "rgba(5,150,105,0.08)"
        tag_bg          = "rgba(5,150,105,0.07)"
        tag_border      = "rgba(5,150,105,0.18)"
        tag_txt         = "#047857"
        input_bg        = "#ffffff"
        input_border    = "#d4e8de"
        divider         = "#edf5f0"
        shadow_card     = "0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04)"
        shadow_hover    = "0 4px 12px rgba(0,0,0,0.08), 0 12px 32px rgba(0,0,0,0.06)"
        mono_label_bg   = "rgba(5,150,105,0.05)"

    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&display=swap');

:root {{
  --bg-body:        {bg_body};
  --bg-sidebar:     {bg_sidebar};
  --bg-card:        {bg_card};
  --bg-card-2:      {bg_card_2};
  --border:         {border_col};
  --border-subtle:  {border_subtle};
  --text-h:         {text_h};
  --text-body:      {text_body};
  --text-muted:     {text_muted};
  --text-mono:      {text_mono};
  --accent:         {accent};
  --accent-soft:    {accent_soft};
  --accent-bg:      {accent_bg};
  --accent-bg2:     {accent_bg2};
  --btn-bg:         {btn_bg};
  --btn-txt:        {btn_txt};
  --btn-hover:      {btn_hover};
  --sidebar-active: {sidebar_active};
  --tag-bg:         {tag_bg};
  --tag-border:     {tag_border};
  --tag-txt:        {tag_txt};
  --input-bg:       {input_bg};
  --input-border:   {input_border};
  --divider:        {divider};
  --shadow-card:    {shadow_card};
  --shadow-hover:   {shadow_hover};
  --mono-label-bg:  {mono_label_bg};
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

html, body, [data-testid="stAppViewContainer"], .stApp {{
  font-family: 'Sora', sans-serif !important;
  background: var(--bg-body) !important;
  color: var(--text-body) !important;
  font-size: 15px;
  -webkit-font-smoothing: antialiased;
}}

#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
header {{ visibility: hidden; }}

[data-testid="stSidebar"] {{
  display: flex !important; visibility: visible !important; opacity: 1 !important;
  transform: none !important; width: 272px !important; min-width: 272px !important;
  max-width: 272px !important; background: var(--bg-sidebar) !important;
  border-right: 1px solid var(--border) !important;
  box-shadow: 2px 0 20px rgba(0,0,0,0.04) !important; transition: none !important;
}}
[data-testid="stSidebarContent"], [data-testid="stSidebarUserContent"] {{ background: var(--bg-sidebar) !important; }}
[data-testid="stSidebar"] > div:first-child {{ padding: 2rem 1.25rem 1.5rem; background: var(--bg-sidebar) !important; }}
[data-testid="stSidebarUserContent"] {{ padding: 0 0.75rem !important; }}
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
[data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] {{
  display: flex !important; visibility: visible !important; opacity: 1 !important;
  pointer-events: all !important; z-index: 999999 !important; position: fixed !important;
  top: 0.75rem !important; left: 0.75rem !important; color: var(--accent) !important;
  background: var(--bg-card) !important; border: 1px solid var(--border) !important;
  border-radius: 8px !important; padding: 4px 8px !important; box-shadow: var(--shadow-card) !important;
}}
[data-testid="collapsedControl"] svg, [data-testid="stSidebarCollapsedControl"] svg {{
  color: var(--accent) !important; fill: var(--accent) !important; width: 18px !important; height: 18px !important;
}}
[data-testid="stSidebar"] .stButton > button {{
  background: transparent !important; color: var(--text-body) !important; border: none !important;
  border-radius: 10px !important; padding: 10px 14px !important; font-family: 'Sora', sans-serif !important;
  font-size: 0.875rem !important; font-weight: 500 !important; text-align: left !important;
  width: 100% !important; margin: 2px 0 !important; transition: background 0.15s, color 0.15s !important;
  box-shadow: none !important; letter-spacing: -0.1px !important;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
  background: var(--sidebar-active) !important; color: var(--accent) !important;
  transform: none !important; box-shadow: none !important;
}}
[data-testid="stMainBlockContainer"] .stButton > button {{
  background: var(--btn-bg) !important; color: var(--btn-txt) !important; border: none !important;
  border-radius: 10px !important; padding: 12px 28px !important; font-family: 'Sora', sans-serif !important;
  font-size: 0.9rem !important; font-weight: 600 !important; letter-spacing: -0.1px !important;
  box-shadow: 0 2px 8px rgba(5,150,105,0.25) !important; transition: background 0.15s, transform 0.15s, box-shadow 0.15s !important;
}}
[data-testid="stMainBlockContainer"] .stButton > button:hover {{
  background: var(--btn-hover) !important; transform: translateY(-2px) !important;
  box-shadow: 0 6px 20px rgba(5,150,105,0.30) !important;
}}

.ml-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 1.75rem; box-shadow: var(--shadow-card); transition: box-shadow 0.22s, transform 0.22s; position: relative; }}
.ml-card:hover {{ box-shadow: var(--shadow-hover); transform: translateY(-3px); }}
.mono-label {{ font-family: 'DM Mono', monospace !important; font-size: 0.7rem !important; font-weight: 500 !important; color: var(--text-mono) !important; text-transform: uppercase !important; letter-spacing: 1.8px !important; background: var(--mono-label-bg) !important; border: 1px solid var(--tag-border) !important; border-radius: 6px !important; padding: 3px 10px !important; display: inline-block !important; margin-bottom: 0.6rem !important; }}
.section-heading {{ font-family: 'Sora', sans-serif; font-size: 1.05rem; font-weight: 700; color: var(--text-h); margin: 1.8rem 0 0.9rem; letter-spacing: -0.3px; display: flex; align-items: center; gap: 0.5rem; }}
.section-heading::after {{ content: ""; flex: 1; height: 1px; background: var(--divider); margin-left: 0.5rem; }}
.page-hero {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 20px; padding: 3rem 2.5rem; margin-bottom: 2rem; box-shadow: var(--shadow-card); position: relative; overflow: hidden; }}
.page-hero::before {{ content: ""; position: absolute; top: -80px; right: -80px; width: 260px; height: 260px; border-radius: 50%; background: radial-gradient(circle, var(--accent-bg) 0%, transparent 68%); pointer-events: none; }}
.page-hero .eyebrow {{ font-family: 'DM Mono', monospace; font-size: 0.68rem; font-weight: 500; color: var(--text-mono); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 0.8rem; display: block; }}
.page-hero h1 {{ font-family: 'Sora', sans-serif; font-size: 2.4rem; font-weight: 800; color: var(--text-h); letter-spacing: -1px; line-height: 1.15; margin-bottom: 0.6rem; }}
.page-hero .sub {{ font-family: 'Sora', sans-serif; font-size: 0.98rem; font-weight: 400; color: var(--text-body); line-height: 1.65; }}
.feat-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 1.75rem 1.5rem; box-shadow: var(--shadow-card); transition: box-shadow 0.22s, transform 0.22s; height: 100% !important; min-height: 220px !important; position: relative; overflow: hidden; display: flex !important; flex-direction: column !important; }}
.feat-card:hover {{ box-shadow: var(--shadow-hover); transform: translateY(-4px); }}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{ display: flex !important; flex-direction: column !important; }}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div {{ flex: 1 !important; display: flex !important; flex-direction: column !important; }}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div > div {{ flex: 1 !important; display: flex !important; flex-direction: column !important; }}
.feat-card .feat-mono {{ font-family: 'DM Mono', monospace; font-size: 0.65rem; color: var(--text-mono); text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 0.9rem; display: block; }}
.feat-card .feat-icon {{ font-size: 1.6rem; margin-bottom: 0.75rem; display: block; color: var(--accent); }}
.feat-card .feat-title {{ font-family: 'Sora', sans-serif; font-size: 1rem; font-weight: 700; color: var(--text-h); letter-spacing: -0.2px; margin-bottom: 0.5rem; }}
.feat-card .feat-desc {{ font-family: 'Sora', sans-serif; font-size: 0.84rem; color: var(--text-body); line-height: 1.65; }}
.stat-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; padding: 1.5rem 1rem; text-align: center; box-shadow: var(--shadow-card); transition: box-shadow 0.2s, transform 0.2s; }}
.stat-card:hover {{ box-shadow: var(--shadow-hover); transform: translateY(-3px); }}
.stat-card .stat-num {{ font-family: 'Sora', sans-serif; font-size: 2rem; font-weight: 800; color: var(--text-h); letter-spacing: -1px; line-height: 1.1; }}
.stat-card .stat-num span {{ color: var(--accent); }}
.stat-card .stat-label {{ font-family: 'DM Mono', monospace; font-size: 0.67rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1.4px; margin-top: 6px; }}
.setup-banner {{ background: var(--accent-bg); border: 1px solid var(--tag-border); border-radius: 16px; padding: 2rem 1.75rem; margin-bottom: 1.5rem; display: flex; align-items: flex-start; gap: 1.25rem; }}
.setup-banner .banner-icon {{ font-size: 2rem; flex-shrink: 0; margin-top: 2px; }}
.setup-banner h3 {{ font-family: 'Sora', sans-serif; font-size: 1rem; font-weight: 700; color: var(--text-h); margin-bottom: 0.3rem; letter-spacing: -0.2px; }}
.setup-banner p {{ font-family: 'Sora', sans-serif; font-size: 0.85rem; color: var(--text-body); line-height: 1.6; }}
.profile-sec {{ display: flex; align-items: center; gap: 0.75rem; padding: 1rem 0 0.6rem; border-bottom: 1px solid var(--divider); margin: 1.4rem 0 1rem; }}
.profile-sec .ps-num {{ font-family: 'DM Mono', monospace; font-size: 0.68rem; font-weight: 500; color: var(--btn-txt); background: var(--accent); border-radius: 6px; padding: 2px 8px; letter-spacing: 0.5px; flex-shrink: 0; }}
.profile-sec .ps-title {{ font-family: 'Sora', sans-serif; font-size: 0.95rem; font-weight: 700; color: var(--text-h); letter-spacing: -0.2px; }}
.profile-sec .ps-desc {{ font-family: 'DM Mono', monospace; font-size: 0.67rem; color: var(--text-muted); margin-left: auto; letter-spacing: 0.5px; }}
.complete-badge {{ display: inline-flex; align-items: center; gap: 0.35rem; background: rgba(5,150,105,0.08); border: 1px solid rgba(5,150,105,0.20); border-radius: 50px; padding: 3px 12px; font-family: 'DM Mono', monospace; font-size: 0.72rem; font-weight: 500; color: var(--accent); letter-spacing: 0.3px; margin-left: 0.5rem; }}
.skill-tag {{ display: inline-block; background: var(--tag-bg); border: 1px solid var(--tag-border); border-radius: 6px; padding: 4px 11px; font-family: 'DM Mono', monospace; font-size: 0.72rem; color: var(--tag-txt); margin: 2px 3px; font-weight: 400; letter-spacing: 0.2px; transition: background 0.15s; }}
.skill-tag:hover {{ background: var(--accent-bg2); }}
.skill-tag-matched {{ display: inline-block; background: rgba(5,150,105,0.12); border: 1px solid rgba(5,150,105,0.35); border-radius: 6px; padding: 4px 11px; font-family: 'DM Mono', monospace; font-size: 0.72rem; color: var(--accent); margin: 2px 3px; font-weight: 600; letter-spacing: 0.2px; }}
.skill-tag-missing {{ display: inline-block; background: rgba(148,163,184,0.07); border: 1px solid rgba(148,163,184,0.18); border-radius: 6px; padding: 4px 11px; font-family: 'DM Mono', monospace; font-size: 0.72rem; color: var(--text-muted); margin: 2px 3px; font-weight: 400; letter-spacing: 0.2px; }}
.user-chip {{ background: var(--bg-card-2, var(--bg-card)); border: 1px solid var(--border); border-radius: 12px; padding: 0.9rem 1rem; margin-bottom: 1rem; }}
.user-chip .uc-name {{ font-family: 'Sora', sans-serif; font-size: 0.9rem; font-weight: 700; color: var(--text-h); letter-spacing: -0.2px; }}
.user-chip .uc-email {{ font-family: 'DM Mono', monospace; font-size: 0.68rem; color: var(--text-muted); margin-top: 3px; word-break: break-all; letter-spacing: 0.2px; }}
.user-chip .uc-role {{ display: inline-block; background: var(--tag-bg); border: 1px solid var(--tag-border); border-radius: 4px; padding: 1px 8px; font-family: 'DM Mono', monospace; font-size: 0.65rem; color: var(--tag-txt); margin-top: 6px; letter-spacing: 0.5px; text-transform: uppercase; }}
.sidebar-wordmark {{ font-family: 'Sora', sans-serif; font-size: 1.15rem; font-weight: 800; color: var(--text-h); letter-spacing: -0.5px; padding-bottom: 1.4rem; display: flex; align-items: center; gap: 0.5rem; }}
.sidebar-wordmark .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--accent); display: inline-block; }}
.sidebar-divider {{ height: 1px; background: var(--divider); margin: 0.9rem 0; }}
.sidebar-section {{ font-family: 'DM Mono', monospace; font-size: 0.62rem; font-weight: 500; color: var(--text-muted); text-transform: uppercase; letter-spacing: 2px; padding: 0.5rem 0.2rem 0.4rem; }}
.sidebar-footer {{ font-family: 'DM Mono', monospace; font-size: 0.68rem; color: var(--text-muted); text-align: center; padding-top: 0.8rem; line-height: 1.9; letter-spacing: 0.3px; }}
.stTextInput > div > div > input, .stTextArea > div > div > textarea, .stSelectbox > div > div, .stMultiSelect > div > div, .stNumberInput > div > div > input {{ background: var(--input-bg) !important; border: 1px solid var(--input-border) !important; border-radius: 10px !important; color: var(--text-h) !important; font-family: 'Sora', sans-serif !important; font-size: 0.88rem !important; box-shadow: none !important; }}
.stTextInput > div > div > input:focus, .stTextArea > div > div > textarea:focus {{ border-color: var(--accent) !important; box-shadow: 0 0 0 3px rgba(5,150,105,0.12) !important; outline: none !important; }}
label, .stSelectbox label, .stMultiSelect label, .stTextArea label, .stRadio label, .stSlider label, .stNumberInput label, .stFileUploader label {{ font-family: 'DM Mono', monospace !important; font-size: 0.7rem !important; font-weight: 500 !important; color: var(--text-muted) !important; text-transform: uppercase !important; letter-spacing: 1.2px !important; }}
.stTabs [data-baseweb="tab-list"] {{ background: transparent !important; border-bottom: 1px solid var(--border) !important; gap: 0 !important; }}
.stTabs [data-baseweb="tab"] {{ background: transparent !important; color: var(--text-muted) !important; border-radius: 0 !important; font-family: 'Sora', sans-serif !important; font-weight: 600 !important; font-size: 0.875rem !important; padding: 10px 22px !important; border-bottom: 2px solid transparent !important; transition: color 0.15s !important; letter-spacing: -0.1px !important; }}
.stTabs [data-baseweb="tab"]:hover {{ color: var(--text-h) !important; background: transparent !important; }}
.stTabs [aria-selected="true"] {{ background: transparent !important; color: var(--accent) !important; border-bottom: 2px solid var(--accent) !important; font-weight: 700 !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: var(--accent) !important; height: 2px !important; }}
.stTabs [data-baseweb="tab-border"] {{ background: var(--border) !important; }}
.stAlert {{ background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: 10px !important; color: var(--text-h) !important; font-family: 'Sora', sans-serif !important; box-shadow: var(--shadow-card) !important; }}
.stFileUploader > div {{ background: var(--input-bg) !important; border: 1px dashed var(--input-border) !important; border-radius: 10px !important; }}
.form-divider {{ height: 1px; background: var(--divider); margin: 1.5rem 0; }}
.stRadio > div {{ gap: 0.5rem !important; }}
.stRadio > div > label {{ background: var(--input-bg) !important; border: 1px solid var(--input-border) !important; border-radius: 8px !important; padding: 6px 14px !important; font-size: 0.84rem !important; transition: border-color 0.15s !important; cursor: pointer; }}
.stRadio > div > label:hover {{ border-color: var(--accent) !important; }}
.stCaption, small {{ font-family: 'DM Mono', monospace !important; font-size: 0.68rem !important; color: var(--text-muted) !important; letter-spacing: 0.3px !important; }}
.cta-strip {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 2.5rem 2rem; text-align: center; box-shadow: var(--shadow-card); margin: 1.5rem 0; position: relative; overflow: hidden; }}
.cta-strip::after {{ content: ""; position: absolute; inset: 0; border-radius: 16px; background: var(--accent-bg); pointer-events: none; }}
.cta-strip h2 {{ font-family: 'Sora', sans-serif; font-size: 1.65rem; font-weight: 800; color: var(--text-h); letter-spacing: -0.6px; margin-bottom: 0.4rem; position: relative; z-index: 1; }}
.cta-strip p {{ font-family: 'Sora', sans-serif; font-size: 0.9rem; color: var(--text-body); position: relative; z-index: 1; }}
.qa-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 1.2rem 1.25rem; box-shadow: var(--shadow-card); display: flex; align-items: center; gap: 0.9rem; cursor: pointer; transition: box-shadow 0.18s, transform 0.18s; }}
.qa-card:hover {{ box-shadow: var(--shadow-hover); transform: translateY(-2px); }}
.qa-card .qa-icon {{ font-size: 1.3rem; flex-shrink: 0; }}
.qa-card .qa-title {{ font-family: 'Sora', sans-serif; font-size: 0.88rem; font-weight: 600; color: var(--text-h); letter-spacing: -0.1px; }}
.qa-card .qa-sub {{ font-family: 'DM Mono', monospace; font-size: 0.66rem; color: var(--text-muted); margin-top: 1px; letter-spacing: 0.3px; }}
.empty-state {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; padding: 3rem 2rem; text-align: center; box-shadow: var(--shadow-card); }}
.empty-state .es-icon {{ font-size: 2rem; color: var(--text-muted); margin-bottom: 0.75rem; display: block; }}
.empty-state p {{ font-family: 'DM Mono', monospace; font-size: 0.75rem; color: var(--text-muted); letter-spacing: 0.5px; }}
.app-row {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 1rem 1.4rem; margin-bottom: 0.6rem; box-shadow: var(--shadow-card); display: flex; align-items: center; gap: 1rem; transition: box-shadow 0.18s, transform 0.18s; }}
.app-row:hover {{ box-shadow: var(--shadow-hover); transform: translateY(-2px); }}
.app-row .ar-avatar {{ width: 40px; height: 40px; border-radius: 10px; background: var(--accent-bg); border: 1px solid var(--tag-border); display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0; color: var(--accent); }}
.app-row .ar-name {{ font-family: 'Sora', sans-serif; font-size: 0.9rem; font-weight: 700; color: var(--text-h); letter-spacing: -0.2px; }}
.app-row .ar-meta {{ font-family: 'DM Mono', monospace; font-size: 0.67rem; color: var(--text-muted); margin-top: 2px; letter-spacing: 0.3px; }}
.app-row .ar-status {{ margin-left: auto; flex-shrink: 0; }}
.status-badge {{ display: inline-flex; align-items: center; gap: 0.3rem; border-radius: 50px; padding: 3px 12px; font-family: 'DM Mono', monospace; font-size: 0.67rem; font-weight: 500; letter-spacing: 0.3px; white-space: nowrap; }}
.status-applied      {{ background: rgba(59,130,246,0.08);  border: 1px solid rgba(59,130,246,0.22);  color: #3b82f6; }}
.status-completed    {{ background: rgba(5,150,105,0.08);   border: 1px solid rgba(5,150,105,0.22);   color: #059669; }}
.status-pending      {{ background: rgba(245,158,11,0.08);  border: 1px solid rgba(245,158,11,0.22);  color: #d97706; }}
.status-shortlisted  {{ background: rgba(139,92,246,0.08);  border: 1px solid rgba(139,92,246,0.22);  color: #7c3aed; }}
.status-hired        {{ background: rgba(5,150,105,0.12);   border: 1px solid rgba(5,150,105,0.35);   color: #047857; }}
.status-rejected     {{ background: rgba(239,68,68,0.08);   border: 1px solid rgba(239,68,68,0.22);   color: #dc2626; }}
.status-scheduled    {{ background: rgba(6,182,212,0.08);   border: 1px solid rgba(6,182,212,0.22);   color: #0891b2; }}
.status-report       {{ background: rgba(249,115,22,0.08);  border: 1px solid rgba(249,115,22,0.22);  color: #ea580c; }}
.status-cancelled    {{ background: rgba(148,163,184,0.08); border: 1px solid rgba(148,163,184,0.22); color: #94a3b8; }}
.report-metric {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; padding: 1.4rem 1rem; text-align: center; box-shadow: var(--shadow-card); }}
.report-metric .rm-value {{ font-family: 'Sora', sans-serif; font-size: 1.8rem; font-weight: 800; color: var(--accent); letter-spacing: -1px; line-height: 1.15; }}
.report-metric .rm-label {{ font-family: 'DM Mono', monospace; font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1.4px; margin-top: 6px; }}
.job-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; padding: 1.25rem 1.4rem; box-shadow: var(--shadow-card); margin-bottom: 0.8rem; transition: box-shadow 0.18s, transform 0.18s; }}
.job-card:hover {{ box-shadow: var(--shadow-hover); transform: translateY(-2px); }}
.job-card .jc-title {{ font-family: 'Sora', sans-serif; font-size: 0.96rem; font-weight: 700; color: var(--text-h); letter-spacing: -0.2px; margin-bottom: 0.3rem; }}
.job-card .jc-meta {{ font-family: 'DM Mono', monospace; font-size: 0.67rem; color: var(--text-muted); letter-spacing: 0.3px; margin-bottom: 0.7rem; }}
.jl-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 1.5rem 1.6rem; box-shadow: var(--shadow-card); margin-bottom: 1rem; transition: box-shadow 0.22s, transform 0.22s; position: relative; }}
.jl-card:hover {{ box-shadow: var(--shadow-hover); transform: translateY(-3px); }}
.jl-card .jl-header {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: 0.6rem; flex-wrap: wrap; }}
.jl-card .jl-title {{ font-family: 'Sora', sans-serif; font-size: 1rem; font-weight: 700; color: var(--text-h); letter-spacing: -0.3px; }}
.jl-card .jl-company {{ font-family: 'DM Mono', monospace; font-size: 0.72rem; color: var(--text-mono); margin-top: 2px; letter-spacing: 0.5px; }}
.jl-card .jl-meta {{ font-family: 'DM Mono', monospace; font-size: 0.67rem; color: var(--text-muted); margin: 0.5rem 0 0.75rem; letter-spacing: 0.3px; display: flex; gap: 0.8rem; flex-wrap: wrap; }}
.jl-card .jl-meta span {{ display: inline-flex; align-items: center; gap: 0.25rem; }}
.match-badge {{ display: inline-flex; align-items: center; gap: 0.3rem; border-radius: 50px; padding: 4px 14px; font-family: 'DM Mono', monospace; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.3px; white-space: nowrap; flex-shrink: 0; }}
.match-high {{ background: rgba(5,150,105,0.10);   border: 1px solid rgba(5,150,105,0.30);   color: #059669; }}
.match-mid  {{ background: rgba(245,158,11,0.08);  border: 1px solid rgba(245,158,11,0.25);  color: #d97706; }}
.match-low  {{ background: rgba(148,163,184,0.08); border: 1px solid rgba(148,163,184,0.20); color: var(--text-muted); }}
.readiness-check {{ background: var(--bg-card-2); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 0.85rem 1rem; margin-bottom: 0.75rem; }}
.readiness-check .rc-title {{ font-family: 'DM Mono', monospace; font-size: 0.67rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1.4px; margin-bottom: 0.5rem; }}
.readiness-check .rc-item {{ display: flex; align-items: center; gap: 0.5rem; font-family: 'Sora', sans-serif; font-size: 0.8rem; color: var(--text-body); padding: 2px 0; }}
.rc-ok   {{ color: var(--accent); }}
.rc-fail {{ color: var(--text-muted); }}
.ah-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 1.5rem 1.6rem; box-shadow: var(--shadow-card); margin-bottom: 1rem; transition: box-shadow 0.22s, transform 0.22s; }}
.ah-card:hover {{ box-shadow: var(--shadow-hover); transform: translateY(-2px); }}
.ah-card .ah-title {{ font-family: 'Sora', sans-serif; font-size: 0.96rem; font-weight: 700; color: var(--text-h); letter-spacing: -0.2px; }}
.ah-card .ah-company {{ font-family: 'DM Mono', monospace; font-size: 0.7rem; color: var(--text-mono); margin-top: 1px; letter-spacing: 0.4px; }}
.ah-card .ah-date {{ font-family: 'DM Mono', monospace; font-size: 0.66rem; color: var(--text-muted); letter-spacing: 0.3px; }}
.status-pipeline {{ display: flex; align-items: center; gap: 0; margin: 1rem 0 0.5rem; flex-wrap: nowrap; overflow-x: auto; padding-bottom: 2px; }}
.pipeline-step {{ display: flex; align-items: center; flex-shrink: 0; }}
.pipeline-node {{ display: flex; flex-direction: column; align-items: center; gap: 4px; }}
.pipeline-dot {{ width: 28px; height: 28px; border-radius: 50%; border: 2px solid var(--border); background: var(--bg-card-2); display: flex; align-items: center; justify-content: center; font-size: 0.65rem; color: var(--text-muted); font-family: 'DM Mono', monospace; font-weight: 600; transition: all 0.2s; flex-shrink: 0; }}
.pipeline-dot-active   {{ border-color: var(--accent);      background: var(--accent);     color: #fff;       box-shadow: 0 0 0 3px var(--accent-bg); }}
.pipeline-dot-done     {{ border-color: var(--accent-soft); background: var(--accent-bg);  color: var(--accent); }}
.pipeline-dot-rejected {{ border-color: #ef4444;            background: rgba(239,68,68,0.08); color: #dc2626;  }}
.pipeline-label {{ font-family: 'DM Mono', monospace; font-size: 0.58rem; color: var(--text-muted); text-align: center; letter-spacing: 0.3px; max-width: 60px; line-height: 1.3; white-space: nowrap; }}
.pipeline-label-active {{ color: var(--accent); font-weight: 600; }}
.pipeline-connector      {{ width: 24px; height: 2px; background: var(--border);      margin: 0 2px; margin-bottom: 22px; flex-shrink: 0; }}
.pipeline-connector-done {{ width: 24px; height: 2px; background: var(--accent-soft); margin: 0 2px; margin-bottom: 22px; flex-shrink: 0; }}
.notif-banner {{ border-radius: 14px; padding: 1.1rem 1.4rem; margin-bottom: 0.75rem; display: flex; align-items: center; gap: 1rem; border: 1px solid; }}
.notif-shortlisted {{ background: rgba(139,92,246,0.06); border-color: rgba(139,92,246,0.22); }}
.notif-hired       {{ background: rgba(5,150,105,0.07);  border-color: rgba(5,150,105,0.25);  }}
.notif-rejected    {{ background: rgba(239,68,68,0.06);  border-color: rgba(239,68,68,0.18);  }}
.notif-banner .nb-icon  {{ font-size: 1.4rem; flex-shrink: 0; }}
.notif-banner .nb-title {{ font-family: 'Sora', sans-serif; font-size: 0.88rem; font-weight: 700; color: var(--text-h); letter-spacing: -0.1px; }}
.notif-banner .nb-sub   {{ font-family: 'DM Mono', monospace; font-size: 0.68rem; color: var(--text-muted); margin-top: 2px; letter-spacing: 0.3px; }}
.cand-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 1.4rem 1.6rem; box-shadow: var(--shadow-card); margin-bottom: 0.9rem; transition: box-shadow 0.22s, transform 0.22s; }}
.cand-card:hover {{ box-shadow: var(--shadow-hover); transform: translateY(-2px); }}
.cand-card .cc-header {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 0.6rem; }}
.cand-card .cc-avatar {{ width: 44px; height: 44px; border-radius: 10px; background: var(--accent-bg); border: 1px solid var(--tag-border); display: flex; align-items: center; justify-content: center; font-size: 1.1rem; flex-shrink: 0; color: var(--accent); font-weight: 700; font-family: 'Sora', sans-serif; }}
.cand-card .cc-name {{ font-family: 'Sora', sans-serif; font-size: 0.95rem; font-weight: 700; color: var(--text-h); letter-spacing: -0.2px; }}
.cand-card .cc-role {{ font-family: 'DM Mono', monospace; font-size: 0.68rem; color: var(--text-mono); margin-top: 1px; letter-spacing: 0.4px; }}
.cand-card .cc-meta {{ font-family: 'DM Mono', monospace; font-size: 0.67rem; color: var(--text-muted); letter-spacing: 0.3px; display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.5rem; }}
.action-strip {{ display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; margin-top: 0.8rem; padding-top: 0.8rem; border-top: 1px solid var(--divider); }}
.confirm-card {{ background: var(--bg-card-2); border: 1px solid var(--border); border-radius: 12px; padding: 1.1rem 1.4rem; margin: 0.5rem 0 0.75rem; }}
.confirm-card .cc-q {{ font-family: 'Sora', sans-serif; font-size: 0.88rem; font-weight: 600; color: var(--text-h); margin-bottom: 0.75rem; }}
.deadline-pill {{ display: inline-flex; align-items: center; gap: 0.4rem; border-radius: 8px; padding: 5px 12px; font-family: 'DM Mono', monospace; font-size: 0.7rem; font-weight: 500; letter-spacing: 0.3px; border: 1px solid; }}
.deadline-ok      {{ background: rgba(5,150,105,0.07);  border-color: rgba(5,150,105,0.25);  color: #059669; }}
.deadline-warn    {{ background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.28); color: #d97706; }}
.deadline-expired {{ background: rgba(239,68,68,0.07); border-color: rgba(239,68,68,0.22);  color: #dc2626; }}

/* Interview Engine Styles */
.iv-progress-wrap {{ background: var(--border); border-radius: 50px; height: 6px; margin: 0.75rem 0 1.5rem; overflow: hidden; }}
.iv-progress-fill {{ background: linear-gradient(90deg, var(--accent-soft), var(--accent)); height: 100%; border-radius: 50px; transition: width 0.4s ease; }}
.iv-question-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 18px; padding: 2rem 2.2rem; box-shadow: var(--shadow-card); margin-bottom: 1.25rem; position: relative; }}
.iv-q-num {{ font-family: 'DM Mono', monospace; font-size: 0.65rem; color: var(--text-mono); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 0.7rem; display: block; }}
.iv-q-cat {{ display: inline-block; background: var(--tag-bg); border: 1px solid var(--tag-border); border-radius: 50px; padding: 2px 10px; font-family: 'DM Mono', monospace; font-size: 0.65rem; color: var(--tag-txt); margin-bottom: 0.8rem; letter-spacing: 0.5px; }}
.iv-q-text {{ font-family: 'Sora', sans-serif; font-size: 1.05rem; font-weight: 600; color: var(--text-h); letter-spacing: -0.3px; line-height: 1.55; }}
.iv-score-card {{ border-radius: 14px; padding: 1.2rem 1.4rem; margin: 1rem 0; border: 1px solid; display: flex; align-items: center; gap: 1rem; }}
.iv-score-pass {{ background: rgba(5,150,105,0.06); border-color: rgba(5,150,105,0.25); }}
.iv-score-fail {{ background: rgba(239,68,68,0.05); border-color: rgba(239,68,68,0.20); }}
.iv-score-num {{ font-family: 'Sora', sans-serif; font-size: 1.8rem; font-weight: 800; letter-spacing: -1px; line-height: 1; flex-shrink: 0; }}
.iv-score-pass .iv-score-num {{ color: #059669; }}
.iv-score-fail .iv-score-num {{ color: #dc2626; }}
.iv-score-label {{ font-family: 'DM Mono', monospace; font-size: 0.68rem; color: var(--text-muted); letter-spacing: 0.3px; }}
.iv-score-feedback {{ font-family: 'Sora', sans-serif; font-size: 0.84rem; color: var(--text-body); line-height: 1.6; flex: 1; }}
.iv-final-hero {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 20px; padding: 2.5rem 2.2rem; text-align: center; box-shadow: var(--shadow-card); position: relative; overflow: hidden; margin-bottom: 1.5rem; }}
.iv-final-score {{ font-family: 'Sora', sans-serif; font-size: 4rem; font-weight: 800; letter-spacing: -3px; line-height: 1; margin-bottom: 0.4rem; }}
.iv-final-label {{ font-family: 'DM Mono', monospace; font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 1rem; }}
.iv-final-verdict {{ display: inline-block; border-radius: 50px; padding: 5px 22px; font-family: 'DM Mono', monospace; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.5px; border: 1px solid; }}
.iv-verdict-pass {{ background: rgba(5,150,105,0.10); border-color: rgba(5,150,105,0.35); color: #059669; }}
.iv-verdict-fail {{ background: rgba(239,68,68,0.08); border-color: rgba(239,68,68,0.28); color: #dc2626; }}
</style>

<script>
(function() {{
  function fixSidebar() {{
    var sidebar = document.querySelector('[data-testid="stSidebar"]');
    if (sidebar) {{
      sidebar.style.setProperty('transform',   'none',    'important');
      sidebar.style.setProperty('width',       '272px',   'important');
      sidebar.style.setProperty('min-width',   '272px',   'important');
      sidebar.style.setProperty('display',     'flex',    'important');
      sidebar.style.setProperty('visibility',  'visible', 'important');
      sidebar.style.setProperty('opacity',     '1',       'important');
      sidebar.style.setProperty('transition',  'none',    'important');
    }}
    var btnSelectors = ['[data-testid="collapsedControl"]', '[data-testid="stSidebarCollapsedControl"]'];
    btnSelectors.forEach(function(sel) {{
      document.querySelectorAll(sel).forEach(function(el) {{
        el.style.setProperty('display','flex','important');
        el.style.setProperty('visibility','visible','important');
        el.style.setProperty('opacity','1','important');
        el.style.setProperty('pointer-events','all','important');
        el.style.setProperty('z-index','999999','important');
        el.style.setProperty('position','fixed','important');
        el.style.setProperty('top','0.75rem','important');
        el.style.setProperty('left','0.75rem','important');
      }});
    }});
    var inner = document.querySelector('[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"]');
    if (inner) {{ inner.style.setProperty('display', 'none', 'important'); }}
  }}
  fixSidebar();
  new MutationObserver(fixSidebar).observe(document.documentElement, {{
    childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class']
  }});
}})();
</script>
""", unsafe_allow_html=True)


# ===========================
# SIDEBAR
# ===========================
def sidebar():
    inject_css(st.session_state.dark_mode)
    with st.sidebar:
        st.markdown(
            '<div class="sidebar-wordmark"><span class="dot"></span>InterviewAI</div>',
            unsafe_allow_html=True
        )

        mode_label = "☀️  Light Mode" if st.session_state.dark_mode else "🌙  Dark Mode"
        if st.button(mode_label, use_container_width=True, key="theme_btn"):
            toggle_theme()

        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

        if st.session_state.logged_in:
            photo_html = ""
            if st.session_state.profile_setup and st.session_state.user_role == "Candidate":
                try:
                    from dashboard.candidate import load_candidate_profile
                    _p   = load_candidate_profile(st.session_state.user_uid)
                    _b64 = _p.get("profile_photo_b64", "")
                    if _b64:
                        _uri = _b64 if _b64.startswith("data:") else f"data:image/jpeg;base64,{_b64}"
                        photo_html = (
                            f'<img src="{_uri}" style="width:40px;height:40px;border-radius:8px;'
                            f'object-fit:cover;border:1px solid var(--border);margin-bottom:0.6rem;display:block;">'
                        )
                except Exception:
                    pass

            st.markdown(
                f'<div class="user-chip">'
                f'{photo_html}'
                f'<div class="uc-name">{st.session_state.user_name}</div>'
                f'<div class="uc-email">{st.session_state.user_email}</div>'
                f'<div class="uc-role">{st.session_state.user_role}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        st.markdown('<div class="sidebar-section">Navigation</div>', unsafe_allow_html=True)

        if st.button("🏠  Home", use_container_width=True):
            navigate_to("home")

        if not st.session_state.logged_in:
            if st.button("🔑  Login / Register", use_container_width=True):
                navigate_to("auth")
        else:
            if st.button("📊  Dashboard", use_container_width=True):
                navigate_to("dashboard")

            if st.session_state.user_role == "Candidate":
                if st.button("🎤  Start Interview", use_container_width=True):
                    navigate_to("interview")

            st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
            st.markdown('<div class="sidebar-section">Account</div>', unsafe_allow_html=True)

            if st.button("🚪  Logout", use_container_width=True):
                firebase_logout()

        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="sidebar-footer">© 2026 InterviewAI<br>All rights reserved</div>',
            unsafe_allow_html=True
        )


# ===========================
# HOME PAGE
# ===========================
def home_page():
    st.markdown("""
    <div class="page-hero">
      <span class="eyebrow">// AI-Powered Interview Platform</span>
      <h1>Ace every interview,<br>every time.</h1>
      <p class="sub">Emotion-aware analysis · Voice-driven sessions · Gemini-powered evaluation.<br>Built for candidates who take their career seriously.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-heading">What it does</div>', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4, gap="medium")
    feats = [
        ("fa-microphone", "01", "Voice Recognition", "High-accuracy speech-to-text captures every word, pause, and nuance."),
        ("fa-face-smile", "02", "Emotion Analysis",  "Real-time facial detection reads confidence, stress, and engagement."),
        ("fa-robot",      "03", "AI Evaluation",     "Gemini generates adaptive questions and scores with context-awareness."),
        ("fa-file-pdf",   "04", "Auto Reporting",    "Detailed PDF summaries with behavioral insights after every session."),
    ]
    for col, (icon, num, title, desc) in zip([col1, col2, col3, col4], feats):
        with col:
            st.markdown(f"""
            <div class="feat-card">
              <span class="feat-mono">// {num}</span>
              <span class="feat-icon"><i class="fa-solid {icon}"></i></span>
              <div class="feat-title">{title}</div>
              <div class="feat-desc">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-heading">By the numbers</div>', unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4, gap="small")
    for col, (n, sfx, lbl) in zip([s1, s2, s3, s4], [
        ("&lt;2", "min", "Avg report time"),
        ("95",   "%",   "Detection accuracy"),
        ("50",   "+",   "Job roles covered"),
        ("24",   "/7",  "Always available"),
    ]):
        with col:
            st.markdown(f'<div class="stat-card"><div class="stat-num">{n}<span>{sfx}</span></div><div class="stat-label">{lbl}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""<div class="cta-strip"><h2>Ready to begin?</h2><p>Smarter hiring starts with a single session — no setup, no guesswork.</p></div>""", unsafe_allow_html=True)
    col_l, col_c, col_r = st.columns([1, 1.4, 1])
    with col_c:
        if st.button("🚀  Start Your Interview Journey", use_container_width=True):
            navigate_to("auth")


# ===========================
# AUTH PAGE
# ===========================
def auth_page():
    if st.session_state.logged_in:
        navigate_to("dashboard")
        return

    st.markdown("""
    <div class="page-hero">
      <span class="eyebrow">// Account Access</span>
      <h1>Welcome back.</h1>
      <p class="sub">Sign in to your account or create a new one to get started.</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["  Login  ", "  Register  "])

        with tab_login:
            st.markdown("<br>", unsafe_allow_html=True)
            login_email    = st.text_input("Email address", placeholder="you@example.com", key="login_email")
            login_password = st.text_input("Password", type="password", placeholder="••••••••", key="login_password")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Sign In →", use_container_width=True, key="login_btn"):
                if not login_email.strip():
                    st.error("❌ Please enter your email.")
                elif not login_password:
                    st.error("❌ Please enter your password.")
                else:
                    with st.spinner("Authenticating..."):
                        success = firebase_login(login_email.strip(), login_password)
                    if success:
                        st.success(f"✅ Welcome back, {st.session_state.user_name}!")
                        time.sleep(0.8)
                        navigate_to("dashboard")

        with tab_register:
            st.markdown("<br>", unsafe_allow_html=True)
            reg_name    = st.text_input("Full name", placeholder="Jane Smith", key="reg_name")
            reg_email   = st.text_input("Email address", placeholder="you@example.com", key="reg_email")
            reg_pass    = st.text_input("Password", type="password", placeholder="Min. 6 characters", key="reg_pass")
            reg_confirm = st.text_input("Confirm password", type="password", placeholder="Repeat password", key="reg_confirm")
            reg_role    = st.selectbox("Role", ["Candidate", "Recruiter", "Admin"], key="reg_role")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Create Account →", use_container_width=True, key="register_btn"):
                if not reg_name.strip():
                    st.error("❌ Please enter your full name.")
                elif not reg_email.strip():
                    st.error("❌ Please enter your email.")
                elif len(reg_pass) < 6:
                    st.error("❌ Password must be at least 6 characters.")
                elif reg_pass != reg_confirm:
                    st.error("❌ Passwords do not match.")
                else:
                    with st.spinner("Creating your account..."):
                        success = firebase_register(reg_name.strip(), reg_email.strip(), reg_pass, reg_role)
                    if success:
                        st.success("🎉 Account created! Please log in.")
                        st.info("👆 Switch to the Login tab to sign in.")


# ===========================
# PDF REPORT GENERATOR
# (shared by candidate & recruiter — imported by dashboard modules)
# ===========================
def generate_pdf_report(
    candidate_name: str,
    job_title: str,
    company: str,
    questions: list,
    answers: dict,
    scores: dict,
    completed_at: str,
) -> bytes:
    import io
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.85*inch, rightMargin=0.85*inch,
                            topMargin=0.9*inch, bottomMargin=0.9*inch)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("Title2", parent=styles["Heading1"], fontSize=20,
                                 textColor=colors.HexColor("#059669"), spaceAfter=4, fontName="Helvetica-Bold")
    sub_style   = ParagraphStyle("Sub",    parent=styles["Normal"],   fontSize=10,
                                 textColor=colors.HexColor("#4a7060"), spaceAfter=14, fontName="Helvetica")
    section_style = ParagraphStyle("Section", parent=styles["Heading2"], fontSize=12,
                                   textColor=colors.HexColor("#0d2218"), spaceBefore=16, spaceAfter=6, fontName="Helvetica-Bold")
    q_style  = ParagraphStyle("Q",  parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#0d2218"),
                               fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=3)
    a_style  = ParagraphStyle("A",  parent=styles["Normal"], fontSize=9.5, textColor=colors.HexColor("#374151"),
                               fontName="Helvetica", spaceAfter=3, leftIndent=12)
    fb_style = ParagraphStyle("FB", parent=styles["Normal"], fontSize=9,  textColor=colors.HexColor("#6b7280"),
                               fontName="Helvetica-Oblique", spaceAfter=6, leftIndent=12)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#9ca3af"),
                                 fontName="Helvetica", spaceAfter=2)

    story = []
    story.append(Paragraph("InterviewAI — Evaluation Report", title_style))
    story.append(Paragraph(f"{candidate_name}  ·  {job_title} at {company}  ·  {completed_at[:10]}", sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2ede8")))
    story.append(Spacer(1, 10))

    total_q   = len(questions)
    answered  = sum(1 for i in range(total_q) if answers.get(i, "").strip())
    correct   = sum(1 for i in range(total_q) if scores.get(i, {}).get("correct", False))
    avg_score = round(sum(scores.get(i, {}).get("score", 0) for i in range(total_q)) / total_q) if total_q else 0
    pass_fail = "PASS ✓" if avg_score >= 60 else "FAIL ✗"
    pf_color  = colors.HexColor("#059669") if avg_score >= 60 else colors.HexColor("#dc2626")

    summary_data = [
        ["Metric", "Value"],
        ["Overall Score",    f"{avg_score}/100"],
        ["Result",           pass_fail],
        ["Questions",        str(total_q)],
        ["Answered",         str(answered)],
        ["Correct (≥60%)",   str(correct)],
        ["Incorrect (<60%)", str(answered - correct)],
        ["Skipped",          str(total_q - answered)],
    ]
    t = Table(summary_data, colWidths=[2.6*inch, 2.4*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#059669")),
        ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0), 9),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.HexColor("#f9fcfa"), colors.white]),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,1), (-1,-1), 9),
        ("TEXTCOLOR",     (0,1), (0,-1), colors.HexColor("#374151")),
        ("TEXTCOLOR",     (1,2), (1,2),  pf_color),
        ("FONTNAME",      (1,2), (1,2),  "Helvetica-Bold"),
        ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#e2ede8")),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("ALIGN",         (1,0), (1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(Spacer(1, 18))
    story.append(Paragraph("Question-by-Question Breakdown", section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2ede8")))

    for i, q_obj in enumerate(questions):
        q_text   = q_obj.get("question", "—")
        category = q_obj.get("category", "—")
        answer   = answers.get(i, "").strip() or "(No answer provided)"
        sc       = scores.get(i, {})
        score    = sc.get("score", 0)
        feedback = sc.get("feedback", "—")
        is_correct = sc.get("correct", False)
        score_color_hex = "#059669" if is_correct else "#dc2626"
        result_label    = "✓ Correct" if is_correct else "✗ Needs Work"

        story.append(Paragraph(f"Q{i+1}. [{category}]  {q_text}", q_style))
        story.append(Paragraph(f"Answer: {answer}", a_style))
        story.append(Paragraph(
            f"<font color='{score_color_hex}'><b>Score: {score}/100 — {result_label}</b></font>",
            ParagraphStyle("ScoreLine", parent=a_style, fontSize=9, spaceAfter=2)
        ))
        story.append(Paragraph(f"Feedback: {feedback}", fb_style))
        story.append(HRFlowable(width="100%", thickness=0.3, color=colors.HexColor("#edf5f0")))

    story.append(Spacer(1, 20))
    story.append(Paragraph(f"Generated by InterviewAI · {completed_at}", small_style))
    doc.build(story)
    return buf.getvalue()


# ===========================
# SAVE INTERVIEW REPORT TO FIREBASE
# ===========================
def save_interview_report_to_firebase(
    uid: str,
    app_key: str,
    recruiter_uid: str,
    report_payload: dict,
    pdf_bytes: bytes,
) -> str:
    pdf_b64 = base64.b64encode(pdf_bytes).decode()
    try:
        realtime_db.reference(f"interview_reports/{uid}/{app_key}").set(report_payload)
        now = datetime.utcnow().isoformat()
        realtime_db.reference(f"candidates/{uid}/applications/{app_key}").update({
            "status":             "Report Generated",
            "last_status_change": now,
            "has_report":         True,
            "overall_score":      report_payload.get("overall_score", 0),
        })
        if recruiter_uid:
            rec_apps = realtime_db.reference(f"recruiters/{recruiter_uid}/applications").get()
            if rec_apps:
                for k, v in rec_apps.items():
                    if v.get("candidate_uid") == uid:
                        realtime_db.reference(f"recruiters/{recruiter_uid}/applications/{k}").update({
                            "status":     "Report Generated",
                            "has_report": True,
                            "last_status_change": now,
                            "overall_score": report_payload.get("overall_score", 0),
                        })
                        break
    except Exception as e:
        st.warning(f"⚠️ Could not save to Firebase: {e}")
    return pdf_b64


# ===========================
# INTERVIEW PAGE
# ===========================
def interview_page():
    if not st.session_state.get("logged_in", False):
        st.warning("⚠️ Please log in to start an interview.")
        return
    if st.session_state.get("user_role", "") != "Candidate":
        st.warning("⚠️ Only candidates can access the interview page.")
        return
    render_interview_page()


# ===========================
# ROUTING
# ===========================
def main():
    sidebar()
    page = st.session_state.current_page

    if page == "home":
        home_page()

    elif page == "auth":
        auth_page()

    elif page == "dashboard":
        if not st.session_state.logged_in:
            st.warning("⚠️ Please log in first.")
            navigate_to("auth")
            return
        role = st.session_state.user_role
        if role == "Recruiter":
            render_recruiter_dashboard()
        else:
            render_candidate_dashboard()

    elif page == "interview":
        if st.session_state.logged_in:
            interview_page()
        else:
            st.warning("⚠️ Please log in first.")
            navigate_to("auth")


if __name__ == "__main__":
    main()