import streamlit as st
from datetime import datetime
from firebase_admin import db as realtime_db

# --- 1. AUTHENTICATION HELPERS ---

def firebase_login(client_auth, email, password) -> bool:
    try:
        user = client_auth.sign_in_with_email_and_password(email, password)
        uid = user["localId"]
        snapshot = realtime_db.reference(f"users/{uid}").get()
        
        st.session_state.logged_in = True
        st.session_state.user_uid = uid
        st.session_state.user_name = snapshot.get("name", email.split("@")[0].title()) if snapshot else "User"
        st.session_state.user_role = snapshot.get("role", "Candidate")
        return True
    except Exception as e:
        st.error(f"❌ Login failed: {e}")
        return False

def firebase_register(client_auth, name, email, password, role) -> bool:
    try:
        user = client_auth.create_user_with_email_and_password(email, password)
        uid = user["localId"]
        profile_data = {
            "uid": uid, "name": name, "email": email, "role": role,
            "created_at": datetime.utcnow().isoformat(), "interviews": 0
        }
        realtime_db.reference(f"users/{uid}").set(profile_data)
        return True
    except Exception as e:
        st.error(f"❌ Registration failed: {e}")
        return False

def firebase_logout():
    for key in ["logged_in", "user_name", "user_role", "user_uid", "profile_setup"]:
        st.session_state[key] = None if key == "user_uid" else ""
        if key == "logged_in": st.session_state[key] = False
    st.rerun()

# --- 2. CANDIDATE HELPERS ---

def load_candidate_profile(uid: str) -> dict:
    snapshot = realtime_db.reference(f"users/{uid}/candidate_profile").get()
    return snapshot if snapshot else {}

def save_candidate_profile(uid: str, profile_data: dict) -> bool:
    profile_data["profile_complete"] = True
    profile_data["updated_at"] = datetime.utcnow().isoformat()
    realtime_db.reference(f"users/{uid}/candidate_profile").set(profile_data)
    return True

def load_candidate_applications(uid: str) -> list:
    """Fetches applications and converts them to a clean list."""
    snapshot = realtime_db.reference(f"candidates/{uid}/applications").get()
    if not snapshot: return []
    
    apps = []
    for key, val in snapshot.items():
        val['key'] = key
        apps.append(val)
    return sorted(apps, key=lambda x: x.get("applied_at", ""), reverse=True)

# --- 3. RECRUITER HELPERS ---

def load_recruiter_profile(uid: str) -> dict:
    return realtime_db.reference(f"recruiters/{uid}").get() or {}

def load_job_postings(uid: str) -> list:
    snapshot = realtime_db.reference(f"recruiters/{uid}/job_postings").get()
    return [{"key": k, **v} for k, v in snapshot.items()] if snapshot else []

def load_applications(uid: str) -> list:
    snapshot = realtime_db.reference(f"recruiters/{uid}/applications").get()
    return [{"key": k, **v} for k, v in snapshot.items()] if snapshot else []

# Add other shared helpers (check_readiness, compute_match, etc.) here as well.