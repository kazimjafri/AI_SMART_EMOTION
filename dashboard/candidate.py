# ===========================
# CANDIDATE DASHBOARD
# dashboard/candidate.py
# ===========================

import streamlit as st
import base64
import time
from datetime import datetime
from firebase_admin import db as realtime_db


# ===========================
# CANDIDATE PROFILE HELPERS
# ===========================

def load_candidate_profile(uid: str) -> dict:
    try:
        snapshot = realtime_db.reference(f"users/{uid}/candidate_profile").get()
        return snapshot if snapshot else {}
    except Exception:
        return {}


def save_candidate_profile(uid: str, profile_data: dict) -> bool:
    try:
        profile_data["profile_complete"] = True
        profile_data["updated_at"] = datetime.utcnow().isoformat()
        realtime_db.reference(f"users/{uid}/candidate_profile").set(profile_data)
        return True
    except Exception as e:
        st.error(f"❌ Failed to save profile: {str(e)}")
        return False


# ===========================
# CANDIDATE JOB / APPLICATION HELPERS
# ===========================

def load_all_job_postings() -> list:
    """Fetch all active job postings across all recruiters. Falls back to rich mock data."""
    try:
        from google.cloud import firestore as gcloud_firestore
        try:
            fs = gcloud_firestore.Client(project="aiemotioninterviewer")
        except Exception:
            fs = None

        if fs:
            docs = fs.collection("job_postings").where("status", "==", "active").stream()
            results = []
            for doc in docs:
                d = doc.to_dict()
                d["job_id"] = doc.id
                results.append(d)
            if results:
                return results

        snapshot = realtime_db.reference("recruiters").get()
        if snapshot:
            results = []
            for rec_uid, rec_data in snapshot.items():
                postings = rec_data.get("job_postings", {})
                for key, job in postings.items():
                    if job.get("status", "active") == "active":
                        job["job_id"]        = key
                        job["recruiter_uid"] = rec_uid
                        results.append(job)
            if results:
                return results
        raise ValueError("no data")
    except Exception:
        return [
            {
                "job_id":           "job_mock_001",
                "job_title":        "Senior ML Engineer",
                "company_name":     "FinEdge AI",
                "industry":         "FinTech",
                "work_mode":        "Hybrid",
                "location":         "Karachi",
                "experience_level": "Senior",
                "recruiter_uid":    "rec_uid_001",
                "recruiter_name":   "Zara Ahmed",
                "core_skills":      ["Python", "TensorFlow", "SQL", "MLOps", "Docker"],
                "nice_to_have":     ["Kubernetes", "Spark"],
                "min_speech_clarity": 75,
                "min_score":        70,
                "target_trait":     "Analytical",
                "interview_type":   "Technical",
                "job_description":  "Build and deploy ML models at scale for our fraud detection platform.",
                "posted_at":        "2026-05-28T10:00:00",
                "status":           "active",
            },
            {
                "job_id":           "job_mock_002",
                "job_title":        "Full Stack Developer",
                "company_name":     "CloudNest",
                "industry":         "Technology",
                "work_mode":        "Remote",
                "location":         "Remote-Global",
                "experience_level": "Mid-Level",
                "recruiter_uid":    "rec_uid_002",
                "recruiter_name":   "Omar Farooq",
                "core_skills":      ["React", "Node.js", "TypeScript", "PostgreSQL"],
                "nice_to_have":     ["Docker", "GraphQL", "AWS"],
                "min_speech_clarity": 65,
                "min_score":        60,
                "target_trait":     "Collaborative",
                "interview_type":   "Mixed",
                "job_description":  "Join our distributed team building next-gen cloud infrastructure tooling.",
                "posted_at":        "2026-05-30T08:30:00",
                "status":           "active",
            },
            {
                "job_id":           "job_mock_003",
                "job_title":        "Data Analyst",
                "company_name":     "HealthSpark",
                "industry":         "HealthTech",
                "work_mode":        "On-site",
                "location":         "Lahore",
                "experience_level": "Fresher",
                "recruiter_uid":    "rec_uid_003",
                "recruiter_name":   "Sana Malik",
                "core_skills":      ["SQL", "Python", "Tableau", "Excel"],
                "nice_to_have":     ["Power BI", "R"],
                "min_speech_clarity": 60,
                "min_score":        55,
                "target_trait":     "Results-Oriented",
                "interview_type":   "HR",
                "job_description":  "Analyse patient outcome data to drive clinical decision-making.",
                "posted_at":        "2026-06-01T11:00:00",
                "status":           "active",
            },
            {
                "job_id":           "job_mock_004",
                "job_title":        "DevOps Engineer",
                "company_name":     "ScaleOps",
                "industry":         "Technology",
                "work_mode":        "Hybrid",
                "location":         "Islamabad",
                "experience_level": "Mid-Level",
                "recruiter_uid":    "rec_uid_004",
                "recruiter_name":   "Ali Hassan",
                "core_skills":      ["Docker", "Kubernetes", "AWS", "Terraform", "Linux"],
                "nice_to_have":     ["Kafka", "Airflow", "Python"],
                "min_speech_clarity": 70,
                "min_score":        65,
                "target_trait":     "Analytical",
                "interview_type":   "Technical",
                "job_description":  "Maintain and scale our Kubernetes clusters serving 10M+ daily requests.",
                "posted_at":        "2026-06-02T09:00:00",
                "status":           "active",
            },
            {
                "job_id":           "job_mock_005",
                "job_title":        "NLP Research Engineer",
                "company_name":     "LinguaLab",
                "industry":         "Technology",
                "work_mode":        "Remote",
                "location":         "Remote-Global",
                "experience_level": "Senior",
                "recruiter_uid":    "rec_uid_005",
                "recruiter_name":   "Fatima Qureshi",
                "core_skills":      ["Python", "NLP", "HuggingFace", "PyTorch", "SQL"],
                "nice_to_have":     ["LangChain", "MLOps", "REST APIs"],
                "min_speech_clarity": 80,
                "min_score":        75,
                "target_trait":     "Creative",
                "interview_type":   "Technical",
                "job_description":  "Research and build multilingual NLP systems with a focus on Urdu and Arabic.",
                "posted_at":        "2026-06-03T14:00:00",
                "status":           "active",
            },
        ]


def compute_match_score(candidate_skills_str: str, job_skills: list) -> dict:
    if not candidate_skills_str or not job_skills:
        return {"matched": 0, "total": len(job_skills) if job_skills else 0, "pct": 0}
    candidate_set  = {s.strip().lower() for s in candidate_skills_str.split(",") if s.strip()}
    job_set        = [s.strip().lower() for s in job_skills]
    matched_skills = [s for s in job_set if s in candidate_set]
    total  = len(job_set)
    pct    = round((len(matched_skills) / total) * 100) if total > 0 else 0
    return {
        "matched":        len(matched_skills),
        "total":          total,
        "pct":            pct,
        "matched_skills": matched_skills,
    }


def check_readiness(profile: dict) -> dict:
    checks = {
        "profile_complete": bool(profile and profile.get("profile_complete")),
        "job_role":         bool(profile and profile.get("job_role", "").strip()),
        "primary_skills":   bool(profile and profile.get("primary_skills", "").strip()),
        "bio":              bool(profile and len(profile.get("bio", "").strip()) >= 20),
    }
    checks["all_ready"] = all(checks.values())
    return checks


def get_active_application_count(apps: list) -> int:
    terminal = {"Rejected", "Cancelled", "Withdrawn"}
    return sum(1 for a in apps if a.get("status", "") not in terminal)


def load_candidate_applications(uid: str) -> list:
    try:
        snapshot = realtime_db.reference(f"candidates/{uid}/applications").get()
        if snapshot:
            return sorted(
                [{"key": k, **v} for k, v in snapshot.items()],
                key=lambda x: x.get("applied_at", ""),
                reverse=True
            )
        raise ValueError("no data")
    except Exception:
        return []


def check_interview_deadlines(uid: str, applications: list) -> list:
    newly_cancelled = []
    now = datetime.utcnow().isoformat()
    for app in (applications or []):
        if app.get("status") != "Interview Scheduled":
            continue
        deadline = app.get("interview_deadline", "")
        if not deadline:
            continue
        if now > deadline:
            app_key       = app.get("key", "")
            recruiter_uid = app.get("recruiter_uid", "")
            try:
                cancel_update = {"status": "Cancelled", "last_status_change": now}
                realtime_db.reference(f"candidates/{uid}/applications/{app_key}").update(cancel_update)
                if recruiter_uid:
                    rec_apps = realtime_db.reference(f"recruiters/{recruiter_uid}/applications").get()
                    if rec_apps:
                        for k, v in rec_apps.items():
                            if v.get("candidate_uid") == uid:
                                realtime_db.reference(
                                    f"recruiters/{recruiter_uid}/applications/{k}"
                                ).update({"status": "Cancelled", "last_status_change": now})
                                break
                app["status"]              = "Cancelled"
                app["last_status_change"]  = now
                newly_cancelled.append(app)
            except Exception:
                pass
    return newly_cancelled


def check_status_notifications(applications: list, last_seen: str) -> list:
    notable_statuses = {"Shortlisted", "Hired", "Rejected", "Interview Scheduled", "Cancelled"}
    if not last_seen:
        return []
    return [
        app for app in (applications or [])
        if app.get("status", "") in notable_statuses
        and app.get("last_status_change", "") > last_seen
    ]


def submit_application(uid: str, job_data: dict) -> bool:
    try:
        now = datetime.utcnow().isoformat()
        app_payload_candidate = {
            "job_id":               job_data.get("job_id", ""),
            "job_title":            job_data.get("job_title", ""),
            "company_name":         job_data.get("company_name", ""),
            "recruiter_uid":        job_data.get("recruiter_uid", ""),
            "applied_at":           now,
            "status":               "Applied",
            "last_status_change":   now,
            "interview_report_url": "",
            "job_description":      job_data.get("job_description", ""),
            "core_skills":          job_data.get("core_skills", []),
            "min_speech_clarity":   job_data.get("min_speech_clarity", 60),
            "min_score":            job_data.get("min_score", 60),
        }
        app_payload_recruiter = {
            "candidate_uid":      uid,
            "candidate_name":     st.session_state.user_name,
            "job_title":          job_data.get("job_title", ""),
            "applied_at":         now,
            "status":             "Applied",
            "last_status_change": now,
            "has_report":         False,
        }
        realtime_db.reference(f"candidates/{uid}/applications").push(app_payload_candidate)
        rec_uid = job_data.get("recruiter_uid", "")
        if rec_uid:
            realtime_db.reference(f"recruiters/{rec_uid}/applications").push(app_payload_recruiter)
        return True
    except Exception as e:
        st.error(f"❌ Failed to submit application: {str(e)}")
        return False


def withdraw_application(uid: str, app_key: str, recruiter_uid: str) -> bool:
    try:
        realtime_db.reference(f"candidates/{uid}/applications/{app_key}").delete()
        if recruiter_uid:
            rec_apps = realtime_db.reference(f"recruiters/{recruiter_uid}/applications").get()
            if rec_apps:
                for k, v in rec_apps.items():
                    if v.get("candidate_uid") == uid:
                        realtime_db.reference(f"recruiters/{recruiter_uid}/applications/{k}").delete()
                        break
        return True
    except Exception as e:
        st.error(f"❌ Failed to withdraw application: {str(e)}")
        return False


def load_candidate_report(uid: str, app_key: str) -> dict:
    try:
        snapshot = realtime_db.reference(f"interview_reports/{uid}/{app_key}").get()
        if snapshot:
            return snapshot
        raise ValueError("no data")
    except Exception:
        return _mock_interview_report(uid)


def _mock_interview_report(candidate_uid: str) -> dict:
    import random
    random.seed(hash(candidate_uid) % 100)
    timeline = []
    confidence, stress = 55, 30
    for i in range(20):
        confidence = max(10, min(95, confidence + random.randint(-8, 12)))
        stress     = max(5,  min(80, stress     + random.randint(-6, 9)))
        timeline.append({
            "frame": i + 1, "confidence": confidence,
            "stress": stress, "neutral": max(0, 100 - confidence - stress),
        })
    emotions = ["Confident", "Neutral", "Focused", "Nervous", "Enthusiastic"]
    return {
        "candidate_uid":      candidate_uid,
        "avg_speech_clarity": random.randint(68, 95),
        "speech_tempo_wpm":   random.randint(110, 165),
        "dominant_emotion":   emotions[hash(candidate_uid) % len(emotions)],
        "overall_score":      random.randint(62, 94),
        "emotion_timeline":   timeline,
        "pdf_report_url":     f"https://storage.googleapis.com/aiemotioninterviewer.firebasestorage.app/reports/{candidate_uid}_report.pdf",
        "completed_at":       "2026-05-30T16:45:00",
    }


# ===========================
# HELPER HTML BUILDERS
# ===========================

def _match_badge_html(pct: int, matched: int, total: int) -> str:
    if pct >= 70:
        css, icon = "match-high", "●"
    elif pct >= 40:
        css, icon = "match-mid",  "◑"
    else:
        css, icon = "match-low",  "○"
    return f'<span class="match-badge {css}">{icon} {matched}/{total} matched · {pct}%</span>'


def _readiness_checklist_html(checks: dict) -> str:
    items = [
        ("profile_complete", "Profile complete"),
        ("job_role",         "Target role set"),
        ("primary_skills",   "Primary skills listed"),
        ("bio",              "Bio written (20+ chars)"),
    ]
    rows = ""
    for key, label in items:
        ok   = checks.get(key, False)
        icon = "✓" if ok else "✗"
        cls  = "rc-ok" if ok else "rc-fail"
        rows += (
            f'<div class="rc-item">'
            f'<span class="{cls}" style="font-weight:700;">{icon}</span>'
            f'<span>{label}</span>'
            f'</div>'
        )
    return (
        '<div class="readiness-check">'
        '<div class="rc-title">// Interview Readiness</div>'
        f'{rows}'
        '</div>'
    )


def _app_status_badge_html(status: str) -> str:
    cls_map = {
        "Applied":             "status-applied",
        "Pending Review":      "status-pending",
        "Interview Scheduled": "status-scheduled",
        "Report Generated":    "status-report",
        "Shortlisted":         "status-shortlisted",
        "Hired":               "status-hired",
        "Rejected":            "status-rejected",
        "Cancelled":           "status-cancelled",
    }
    dot_map = {
        "Applied":             "●",
        "Pending Review":      "◐",
        "Interview Scheduled": "📅",
        "Report Generated":    "📄",
        "Shortlisted":         "⭐",
        "Hired":               "✓",
        "Rejected":            "✗",
        "Cancelled":           "⊘",
    }
    return f'<span class="status-badge {cls_map.get(status,"status-applied")}">{dot_map.get(status,"●")} {status}</span>'


_PIPELINE_STAGES = ["Applied", "Pending Review", "Interview Scheduled", "Report Generated", "Shortlisted", "Hired"]
_TERMINAL_NEGATIVE = "Rejected"


def _pipeline_html(current_status: str) -> str:
    is_rejected = current_status == _TERMINAL_NEGATIVE
    try:
        active_idx = _PIPELINE_STAGES.index(current_status)
    except ValueError:
        active_idx = -1

    nodes_html = ""
    for i, stage in enumerate(_PIPELINE_STAGES):
        if i < active_idx:
            dot_cls, label_cls = "pipeline-dot-done", ""
        elif i == active_idx:
            dot_cls, label_cls = "pipeline-dot-active", "pipeline-label-active"
        else:
            dot_cls, label_cls = "", ""

        short_labels = {
            "Applied": "Applied", "Pending Review": "Review",
            "Interview Scheduled": "Interview", "Report Generated": "Report",
            "Shortlisted": "Listed", "Hired": "Hired",
        }
        label = short_labels.get(stage, stage)
        nodes_html += (
            f'<div class="pipeline-step"><div class="pipeline-node">'
            f'<div class="pipeline-dot {dot_cls}">{i+1}</div>'
            f'<div class="pipeline-label {label_cls}">{label}</div>'
            f'</div></div>'
        )
        if i < len(_PIPELINE_STAGES) - 1:
            conn_cls = "pipeline-connector-done" if i < active_idx else ""
            nodes_html += f'<div class="pipeline-connector {conn_cls}"></div>'

    if is_rejected:
        nodes_html += (
            '<div class="pipeline-connector"></div>'
            '<div class="pipeline-step"><div class="pipeline-node">'
            '<div class="pipeline-dot pipeline-dot-rejected">✗</div>'
            '<div class="pipeline-label" style="color:#dc2626;">Rejected</div>'
            '</div></div>'
        )
    return f'<div class="status-pipeline">{nodes_html}</div>'


# ===========================
# CANDIDATE PROFILE TAB
# ===========================

def candidate_profile_tab():
    uid = st.session_state.user_uid

    with st.spinner("Loading profile..."):
        profile = load_candidate_profile(uid)

    is_edit = bool(profile and profile.get("profile_complete", False))

    if is_edit:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.4rem;">'
            '<span style="font-family:\'Sora\',sans-serif;font-size:1.05rem;font-weight:700;color:var(--text-h);">Your Profile</span>'
            '<span class="complete-badge">✓ complete</span>'
            '</div>'
            '<p style="font-family:\'DM Mono\',monospace;font-size:0.72rem;color:var(--text-muted);'
            'letter-spacing:0.3px;margin-bottom:1.4rem;">Edit any field and click Save Profile to update.</p>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="ml-card" style="margin-bottom:1.4rem;display:flex;align-items:center;gap:1rem;">'
            '<span style="font-size:1.8rem;">📋</span>'
            '<div>'
            '<div style="font-family:\'Sora\',sans-serif;font-size:0.95rem;font-weight:700;color:var(--text-h);">Complete your profile</div>'
            '<div style="font-family:\'DM Mono\',monospace;font-size:0.7rem;color:var(--text-muted);margin-top:3px;letter-spacing:0.3px;">'
            '// helps gemini generate personalised questions'
            '</div></div></div>',
            unsafe_allow_html=True
        )

    st.markdown('<div class="profile-sec"><span class="ps-num">01</span><span class="ps-title">Personal Info</span><span class="ps-desc">// identity</span></div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2, gap="medium")
    with col_a:
        full_name = st.text_input("Full name", value=profile.get("full_name", st.session_state.user_name), placeholder="Your full name", key="pf_full_name")
    with col_b:
        existing_photo_b64 = profile.get("profile_photo_b64", "")
        uploaded_photo = st.file_uploader("Profile photo (optional)", type=["jpg", "jpeg", "png", "webp"], key="pf_photo_upload")
        if uploaded_photo is not None:
            photo_bytes = uploaded_photo.read()
            photo_b64_new = base64.b64encode(photo_bytes).decode()
            photo_mime = uploaded_photo.type
            profile_photo_b64_final = photo_b64_new
            photo_data_uri = f"data:{photo_mime};base64,{photo_b64_new}"
            st.markdown(
                f'<div style="margin-top:0.5rem;display:flex;align-items:center;gap:0.75rem;">'
                f'<img src="{photo_data_uri}" style="width:52px;height:52px;border-radius:8px;object-fit:cover;border:1px solid var(--border);">'
                f'<span style="font-family:\'DM Mono\',monospace;font-size:0.7rem;color:var(--text-muted);">// new photo selected</span>'
                f'</div>', unsafe_allow_html=True
            )
        elif existing_photo_b64:
            profile_photo_b64_final = existing_photo_b64
            existing_uri = existing_photo_b64 if existing_photo_b64.startswith("data:") else f"data:image/jpeg;base64,{existing_photo_b64}"
            st.markdown(
                f'<div style="margin-top:0.5rem;display:flex;align-items:center;gap:0.75rem;">'
                f'<img src="{existing_uri}" style="width:52px;height:52px;border-radius:8px;object-fit:cover;border:1px solid var(--border);">'
                f'<span style="font-family:\'DM Mono\',monospace;font-size:0.7rem;color:var(--text-muted);">// current photo</span>'
                f'</div>', unsafe_allow_html=True
            )
        else:
            profile_photo_b64_final = ""

    st.markdown('<div class="profile-sec"><span class="ps-num">02</span><span class="ps-title">Professional Background</span><span class="ps-desc">// experience</span></div>', unsafe_allow_html=True)
    col_c, col_d = st.columns(2, gap="medium")
    with col_c:
        job_role = st.text_input("Target role", value=profile.get("job_role", ""), placeholder="e.g. Software Engineer, Data Analyst", key="pf_job_role")
        exp_opts = ["Fresher", "Mid-Level", "Senior"]
        exp_def  = profile.get("experience_level", "Fresher")
        experience_level = st.selectbox("Experience level", exp_opts, index=exp_opts.index(exp_def) if exp_def in exp_opts else 0, key="pf_exp_level")
    with col_d:
        years_exp = st.number_input("Years of experience", min_value=0, max_value=50, value=int(profile.get("years_experience", 0)), step=1, key="pf_years_exp")
        current_company = st.text_input("Current / last company", value=profile.get("current_company", ""), placeholder="e.g. Google, Acme Corp", key="pf_company")

    st.markdown('<div class="profile-sec"><span class="ps-num">03</span><span class="ps-title">Skills</span><span class="ps-desc">// tech & soft</span></div>', unsafe_allow_html=True)
    col_e, col_f = st.columns(2, gap="medium")
    with col_e:
        primary_skills = st.text_input("Primary skills", value=profile.get("primary_skills", ""), placeholder="Python, React, SQL, Machine Learning", key="pf_primary_skills")
        st.caption("separate with commas")
    with col_f:
        secondary_skills = st.text_input("Secondary skills (optional)", value=profile.get("secondary_skills", ""), placeholder="Docker, Figma, Excel", key="pf_secondary_skills")
        st.caption("supporting / bonus skills")

    if primary_skills.strip():
        pills = "".join(f'<span class="skill-tag">{s.strip()}</span>' for s in primary_skills.split(",") if s.strip())
        st.markdown(f'<div style="margin-top:6px;">{pills}</div>', unsafe_allow_html=True)

    st.markdown('<div class="profile-sec"><span class="ps-num">04</span><span class="ps-title">Interview Preferences</span><span class="ps-desc">// customise</span></div>', unsafe_allow_html=True)
    col_g, col_h, col_i = st.columns(3, gap="medium")
    with col_g:
        it_opts = ["Technical", "HR", "Behavioral", "Mixed"]
        it_def  = profile.get("interview_type", "Mixed")
        interview_type = st.selectbox("Interview type", it_opts, index=it_opts.index(it_def) if it_def in it_opts else 3, key="pf_interview_type")
    with col_h:
        nq_opts = [5, 10, 15]
        nq_def  = int(profile.get("num_questions", 10))
        num_questions = st.selectbox("No. of questions", nq_opts, index=nq_opts.index(nq_def) if nq_def in nq_opts else 1, key="pf_num_questions")
    with col_i:
        diff_opts = ["Easy", "Medium", "Hard"]
        diff_def  = profile.get("difficulty_level", "Medium")
        difficulty_level = st.selectbox("Difficulty", diff_opts, index=diff_opts.index(diff_def) if diff_def in diff_opts else 1, key="pf_difficulty")

    st.markdown('<div class="profile-sec"><span class="ps-num">05</span><span class="ps-title">About You</span><span class="ps-desc">// bio & links</span></div>', unsafe_allow_html=True)
    col_j, col_k = st.columns([3, 2], gap="medium")
    with col_j:
        bio = st.text_area("Brief bio", value=profile.get("bio", ""), placeholder="2–3 lines about yourself, your goals, what makes you unique...", height=110, key="pf_bio")
        st.caption(f"{'✓' if len(bio.strip()) >= 20 else '~'}  {len(bio)} chars  //  aim for 50+")
    with col_k:
        linkedin_url = st.text_input("LinkedIn URL (optional)", value=profile.get("linkedin_url", ""), placeholder="https://linkedin.com/in/you", key="pf_linkedin")

    st.markdown('<div class="form-divider"></div>', unsafe_allow_html=True)
    save_col, _ = st.columns([1, 3])
    with save_col:
        label = "Save Changes →" if is_edit else "Save Profile →"
        save_clicked = st.button(label, use_container_width=True, key="save_profile_btn")

    if save_clicked:
        errors = []
        if not full_name.strip():      errors.append("Full name is required.")
        if not job_role.strip():       errors.append("Target role is required.")
        if not primary_skills.strip(): errors.append("Primary skills are required.")
        for err in errors:
            st.error(f"❌ {err}")
        if not errors:
            payload = {
                "full_name":         full_name.strip(),
                "profile_photo_b64": profile_photo_b64_final,
                "job_role":          job_role.strip(),
                "experience_level":  experience_level,
                "years_experience":  int(years_exp),
                "current_company":   current_company.strip(),
                "primary_skills":    primary_skills.strip(),
                "secondary_skills":  secondary_skills.strip(),
                "interview_type":    interview_type,
                "num_questions":     int(num_questions),
                "difficulty_level":  difficulty_level,
                "bio":               bio.strip(),
                "linkedin_url":      linkedin_url.strip(),
            }
            with st.spinner("Saving..."):
                saved = save_candidate_profile(uid, payload)
            if saved:
                st.session_state.profile_setup = True
                st.session_state.user_name = full_name.strip()
                st.success(f"✅ Profile {'updated' if is_edit else 'saved'}!")
                time.sleep(0.6)
                st.rerun()


# ===========================
# JOB SEARCH TAB
# ===========================

def job_search_tab():
    uid = st.session_state.user_uid
    with st.spinner("Loading jobs..."):
        profile       = load_candidate_profile(uid)
        all_jobs      = load_all_job_postings()
        existing_apps = load_candidate_applications(uid)

    candidate_skills = profile.get("primary_skills", "") if profile else ""
    readiness        = check_readiness(profile)
    applied_job_ids  = {a.get("job_id", "") for a in existing_apps}

    st.markdown('<div class="section-heading">Filter jobs</div>', unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1], gap="small")
    with f1:
        search_kw = st.text_input("Search by title or company", placeholder="e.g. ML Engineer, FinEdge", key="js_search").strip().lower()
    with f2:
        work_mode_filter = st.selectbox("Work mode", ["All", "Remote", "Hybrid", "On-site"], key="js_work_mode")
    with f3:
        exp_filter = st.selectbox("Experience level", ["All", "Fresher", "Mid-Level", "Senior", "Lead / Principal"], key="js_exp")
    with f4:
        industry_filter = st.selectbox("Industry", ["All", "Technology", "FinTech", "HealthTech", "EdTech", "E-Commerce", "Consulting", "Manufacturing", "Telecom", "Other"], key="js_industry")

    filtered_jobs = [
        job for job in all_jobs
        if (not search_kw or search_kw in job.get("job_title", "").lower() or search_kw in job.get("company_name", "").lower())
        and (work_mode_filter == "All" or job.get("work_mode") == work_mode_filter)
        and (exp_filter == "All" or job.get("experience_level") == exp_filter)
        and (industry_filter == "All" or job.get("industry") == industry_filter)
    ]
    filtered_jobs.sort(key=lambda j: compute_match_score(candidate_skills, j.get("core_skills", []))["pct"], reverse=True)

    st.markdown(
        f'<div style="font-family:\'DM Mono\',monospace;font-size:0.7rem;color:var(--text-muted);'
        f'letter-spacing:0.5px;margin:0.4rem 0 1.2rem;">// {len(filtered_jobs)} job{"s" if len(filtered_jobs) != 1 else ""} found</div>',
        unsafe_allow_html=True
    )

    if not filtered_jobs:
        st.markdown("""<div class="empty-state"><span class="es-icon"><i class="fa-regular fa-folder-open"></i></span><p>// no jobs match your filters — try broadening the search</p></div>""", unsafe_allow_html=True)
        return

    for idx, job in enumerate(filtered_jobs):
        job_id      = job.get("job_id", f"job_{idx}")
        job_title   = job.get("job_title", "—")
        company     = job.get("company_name", "—")
        industry    = job.get("industry", "—")
        work_mode   = job.get("work_mode", "—")
        location    = job.get("location") or "TBC"
        exp_level   = job.get("experience_level", "—")
        core_skills = job.get("core_skills") or []
        posted_at   = job.get("posted_at", "")[:10] if job.get("posted_at") else "—"
        already_applied = job_id in applied_job_ids

        match       = compute_match_score(candidate_skills, core_skills)
        badge_html  = _match_badge_html(match["pct"], match["matched"], match["total"])
        matched_set = set(match.get("matched_skills", []))
        skills_html = "".join(
            f'<span class="skill-tag-matched">{s}</span>' if s.lower() in matched_set
            else f'<span class="skill-tag-missing">{s}</span>'
            for s in core_skills
        )
        work_mode_icon = {"Remote": "🌐", "Hybrid": "🏢", "On-site": "📍"}.get(work_mode, "📌")
        exp_icon = {"Fresher": "🌱", "Mid-Level": "⚡", "Senior": "🔥", "Lead / Principal": "👑"}.get(exp_level, "✦")

        st.markdown(f"""
        <div class="jl-card">
          <div class="jl-header">
            <div>
              <div class="jl-title">{job_title}</div>
              <div class="jl-company">// {company} &nbsp;·&nbsp; {industry}</div>
            </div>
            {badge_html}
          </div>
          <div class="jl-meta">
            <span>{work_mode_icon} {work_mode}</span>
            <span>📍 {location}</span>
            <span>{exp_icon} {exp_level}</span>
            <span>📅 {posted_at}</span>
          </div>
          <div style="margin-bottom:0.75rem;">{skills_html}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander(f"View details & apply — {job_title}", expanded=False):
            desc = job.get("job_description", "")
            if desc:
                st.markdown(f'<div style="font-family:\'Sora\',sans-serif;font-size:0.85rem;color:var(--text-body);line-height:1.7;margin-bottom:1rem;">{desc}</div>', unsafe_allow_html=True)

            nth = job.get("nice_to_have") or []
            if nth:
                nth_pills = "".join(f'<span class="skill-tag">{s}</span>' for s in nth)
                st.markdown(
                    f'<div style="margin-bottom:0.8rem;">'
                    f'<span style="font-family:\'DM Mono\',monospace;font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:1.3px;">// nice to have &nbsp;</span>'
                    f'{nth_pills}</div>', unsafe_allow_html=True
                )

            t1, t2, t3 = st.columns(3, gap="small")
            with t1:
                st.markdown(f'<div class="report-metric" style="padding:0.9rem 0.8rem;"><div class="rm-value" style="font-size:1.3rem;">{job.get("min_speech_clarity",0)}%</div><div class="rm-label">min speech clarity</div></div>', unsafe_allow_html=True)
            with t2:
                st.markdown(f'<div class="report-metric" style="padding:0.9rem 0.8rem;"><div class="rm-value" style="font-size:1.3rem;">{job.get("min_score",0)}%</div><div class="rm-label">min overall score</div></div>', unsafe_allow_html=True)
            with t3:
                st.markdown(f'<div class="report-metric" style="padding:0.9rem 0.8rem;"><div class="rm-value" style="font-size:1rem;">{job.get("target_trait","—")}</div><div class="rm-label">target trait</div></div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            if already_applied:
                st.markdown(
                    f'<div class="notif-banner notif-hired" style="margin-top:0.5rem;">'
                    f'<span class="nb-icon">✅</span>'
                    f'<div><div class="nb-title">Already applied to {job_title}</div>'
                    f'<div class="nb-sub">// check Application History for status updates</div></div>'
                    f'</div>', unsafe_allow_html=True
                )
            else:
                apply_col, check_col = st.columns([1, 2], gap="medium")
                with check_col:
                    st.markdown(_readiness_checklist_html(readiness), unsafe_allow_html=True)
                with apply_col:
                    if readiness["all_ready"]:
                        if st.button(f"Apply Now →", key=f"apply_{job_id}_{idx}", use_container_width=True):
                            with st.spinner("Submitting application..."):
                                ok = submit_application(uid, job)
                            if ok:
                                st.success(f"✅ Applied to {job_title} at {company}!")
                                st.rerun()
                    else:
                        st.markdown(
                            '<div class="readiness-check" style="border-color:rgba(245,158,11,0.3);">'
                            '<div class="rc-title" style="color:#d97706;">// profile incomplete</div>'
                            '<div style="font-family:\'Sora\',sans-serif;font-size:0.8rem;color:var(--text-body);line-height:1.55;">'
                            'Complete your profile before applying.</div></div>', unsafe_allow_html=True
                        )
                        st.button("Complete Profile First", key=f"goto_profile_from_jobs_{idx}", use_container_width=True,
                                  on_click=lambda: setattr(st.session_state, "goto_profile_tab", True))


# ===========================
# APPLICATION HISTORY TAB
# ===========================

def application_history_tab():
    uid = st.session_state.user_uid
    with st.spinner("Loading your applications..."):
        apps = load_candidate_applications(uid)

    last_seen        = st.session_state.get("last_seen_timestamp", "")
    notifications    = check_status_notifications(apps, last_seen)
    newly_cancelled  = check_interview_deadlines(uid, apps)

    if newly_cancelled:
        for nc in newly_cancelled:
            st.markdown(
                f'<div class="notif-banner notif-rejected">'
                f'<span class="nb-icon">⏰</span>'
                f'<div><div class="nb-title">Interview deadline passed for <strong>{nc.get("job_title","—")}</strong> at {nc.get("company_name","—")} — session cancelled</div>'
                f'<div class="nb-sub">// you did not complete the interview within 48 hours</div></div>'
                f'</div>', unsafe_allow_html=True
            )   

    if notifications:
        st.markdown('<div class="section-heading">🔔 What\'s new</div>', unsafe_allow_html=True)
        for notif in notifications:
            status    = notif.get("status", "")
            notif_cls = {"Shortlisted": "notif-shortlisted", "Hired": "notif-hired", "Rejected": "notif-rejected",
                         "Interview Scheduled": "notif-hired", "Cancelled": "notif-rejected"}.get(status, "notif-shortlisted")
            icon = {"Shortlisted": "⭐", "Hired": "🎉", "Rejected": "📭", "Interview Scheduled": "📅", "Cancelled": "⏰"}.get(status, "🔔")
            st.markdown(
                f'<div class="notif-banner {notif_cls}"><span class="nb-icon">{icon}</span>'
                f'<div><div class="nb-title">Your application for <strong>{notif.get("job_title","—")}</strong> at {notif.get("company_name","—")} is now: {status}</div>'
                f'<div class="nb-sub">// updated {notif.get("last_status_change","")[:10]}</div></div></div>',
                unsafe_allow_html=True
            )
        st.markdown("<br>", unsafe_allow_html=True)

    total_apps    = len(apps)
    interviews_sc = sum(1 for a in apps if a.get("status") == "Interview Scheduled")
    reports_ready = sum(1 for a in apps if a.get("status") in {"Report Generated", "Shortlisted", "Hired", "Rejected"} and a.get("interview_report_url"))
    shortlisted   = sum(1 for a in apps if a.get("status") == "Shortlisted")

    st.markdown('<div class="section-heading">Your summary</div>', unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4, gap="small")
    for col, (n, sfx, lbl) in zip([s1, s2, s3, s4], [
        (total_apps,    "", "total applied"),
        (interviews_sc, "", "interviews scheduled"),
        (reports_ready, "", "reports ready"),
        (shortlisted,   "", "shortlisted"),
    ]):
        with col:
            st.markdown(f'<div class="stat-card"><div class="stat-num">{n}<span>{sfx}</span></div><div class="stat-label">{lbl}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if not apps:
        st.markdown("""<div class="empty-state"><span class="es-icon"><i class="fa-regular fa-folder-open"></i></span><p>// no applications yet — browse the Job Search tab to get started</p></div>""", unsafe_allow_html=True)
        return

    st.markdown('<div class="section-heading">All applications</div>', unsafe_allow_html=True)

    for idx, app in enumerate(apps):
        status        = app.get("status", "Applied")
        job_title     = app.get("job_title", "—")
        company       = app.get("company_name", "—")
        applied_str   = app.get("applied_at", "")[:10] if app.get("applied_at") else "—"
        app_key       = app.get("key", "")
        recruiter_uid = app.get("recruiter_uid", "")
        report_url    = app.get("interview_report_url", "")

        st.markdown(f"""
        <div class="ah-card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.5rem;">
            <div>
              <div class="ah-title">{job_title}</div>
              <div class="ah-company">// {company}</div>
            </div>
            <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
              {_app_status_badge_html(status)}
              <span class="ah-date">Applied {applied_str}</span>
            </div>
          </div>
          {_pipeline_html(status)}
        </div>
        """, unsafe_allow_html=True)

        if status == "Interview Scheduled":
            deadline = app.get("interview_deadline", "")
            if deadline:
                try:
                    deadline_dt  = datetime.fromisoformat(deadline)
                    diff         = deadline_dt - datetime.utcnow()
                    total_secs   = int(diff.total_seconds())
                    if total_secs > 0:
                        hours_left   = total_secs // 3600
                        minutes_left = (total_secs % 3600) // 60
                        time_str     = f"{hours_left}h {minutes_left}m remaining" if hours_left > 0 else f"{minutes_left}m remaining"
                        urgency_color = "#d97706" if hours_left < 12 else "#059669"
                        st.markdown(
                            f'<div style="background:rgba(245,158,11,0.07);border:1px solid rgba(245,158,11,0.25);'
                            f'border-radius:10px;padding:0.75rem 1rem;margin-bottom:0.6rem;display:flex;align-items:center;gap:0.75rem;">'
                            f'<span style="font-size:1.1rem;">⏱️</span>'
                            f'<div><div style="font-family:\'Sora\',sans-serif;font-size:0.82rem;font-weight:700;color:{urgency_color};">'
                            f'Interview deadline: {time_str}</div>'
                            f'<div style="font-family:\'DM Mono\',monospace;font-size:0.65rem;color:var(--text-muted);margin-top:2px;letter-spacing:0.3px;">'
                            f'// complete your AI interview before the deadline or it will be cancelled</div></div></div>',
                            unsafe_allow_html=True
                        )
                except Exception:
                    pass

        actions = []
        if status == "Applied":             actions.append("withdraw")
        if status == "Interview Scheduled": actions.append("start_interview")
        if report_url and status in {"Report Generated", "Shortlisted", "Hired", "Rejected"}:
            actions.append("download_report")

        if actions:
            from app import generate_pdf_report  # local import to avoid circular
            btn_cols = st.columns(len(actions) + 3, gap="small")
            col_ptr = 0
            if "withdraw" in actions:
                with btn_cols[col_ptr]:
                    if st.button("Withdraw", key=f"withdraw_{app_key}_{idx}", use_container_width=True):
                        st.session_state[f"confirm_withdraw_{app_key}"] = True
                col_ptr += 1
            if "start_interview" in actions:
                with btn_cols[col_ptr]:
                    if st.button("🎤 Start Interview", key=f"start_int_{app_key}_{idx}", use_container_width=True):
                        st.session_state.job_interview_context = {
                            "job_id":             app.get("job_id", ""),
                            "job_title":          job_title,
                            "company_name":       company,
                            "job_description":    app.get("job_description", ""),
                            "core_skills":        app.get("core_skills", []),
                            "min_speech_clarity": app.get("min_speech_clarity", 60),
                            "min_score":          app.get("min_score", 60),
                            "app_key":            app_key,
                        }
                        st.success(f"✅ Interview context loaded for {job_title}. Launching...")
                        time.sleep(0.6)
                        from app import navigate_to
                        navigate_to("interview")
                col_ptr += 1
            if "download_report" in actions:
                with btn_cols[col_ptr]:
                    try:
                        rpt = realtime_db.reference(f"interview_reports/{uid}/{app_key}").get()
                        if rpt and rpt.get("questions_data"):
                            qd = rpt["questions_data"]
                            qs = [{"question": r["question"], "category": r.get("category",""), "expected_keywords": []} for r in qd]
                            an = {i: r.get("answer","") for i, r in enumerate(qd)}
                            sc = {i: {"score": r.get("score",0), "correct": r.get("correct",False), "feedback": r.get("feedback","")} for i, r in enumerate(qd)}
                            pdf_bytes_inline = generate_pdf_report(
                                candidate_name=rpt.get("candidate_name", st.session_state.user_name),
                                job_title=rpt.get("job_title",""),
                                company=rpt.get("company_name",""),
                                questions=qs, answers=an, scores=sc,
                                completed_at=rpt.get("completed_at",""),
                            )
                            st.download_button(
                                "⬇️ Download Report", data=pdf_bytes_inline,
                                file_name=f"InterviewAI_{app_key}.pdf",
                                mime="application/pdf",
                                key=f"dl_report_{app_key}_{idx}",
                                use_container_width=True,
                            )
                        elif report_url:
                            st.info(f"📎 [Click here]({report_url})")
                        else:
                            st.warning("⚠️ Report not ready yet.")
                    except Exception:
                        if report_url:
                            st.info(f"📎 [Download report]({report_url})")
                        else:
                            st.warning("⚠️ Report not available.")
                col_ptr += 1

        if st.session_state.get(f"confirm_withdraw_{app_key}", False):
            st.warning(f"⚠️ Are you sure you want to withdraw your application for **{job_title}** at **{company}**?")
            c1, c2, _ = st.columns([1, 1, 4])
            with c1:
                if st.button("Yes, withdraw", key=f"confirm_yes_{app_key}"):
                    with st.spinner("Withdrawing..."):
                        ok = withdraw_application(uid, app_key, recruiter_uid)
                    if ok:
                        st.session_state.pop(f"confirm_withdraw_{app_key}", None)
                        st.success("✅ Application withdrawn.")
                        time.sleep(0.5)
                        st.rerun()
            with c2:
                if st.button("Cancel", key=f"confirm_no_{app_key}"):
                    st.session_state.pop(f"confirm_withdraw_{app_key}", None)
                    st.rerun()

        st.markdown('<div style="height:0.25rem;"></div>', unsafe_allow_html=True)


# ===========================
# CANDIDATE DASHBOARD (main entry)
# ===========================

def render_candidate_dashboard():
    """Main candidate dashboard — called from app.py."""
    st.markdown(f"""
    <div class="page-hero">
      <span class="eyebrow">// Dashboard</span>
      <h1>Hey, {st.session_state.user_name}.</h1>
      <p class="sub">Role: {st.session_state.user_role} &nbsp;·&nbsp; Manage your interviews, jobs, applications, and profile.</p>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.get("goto_profile_tab", False):
        st.session_state.goto_profile_tab = False
        tab_profile, tab_overview, tab_jobs, tab_apphistory = st.tabs([
            "  Profile  ", "  Overview  ", "  Job Search  ", "  Application History  ",
        ])
    else:
        tab_overview, tab_jobs, tab_apphistory, tab_profile = st.tabs([
            "  Overview  ", "  Job Search  ", "  Application History  ", "  Profile  ",
        ])

    with tab_overview:
        _candidate_overview_tab()

    with tab_jobs:
        job_search_tab()

    with tab_apphistory:
        application_history_tab()

    with tab_profile:
        candidate_profile_tab()


def _candidate_overview_tab():
    from app import navigate_to
    uid = st.session_state.user_uid

    with st.spinner(""):
        candidate_apps = load_candidate_applications(uid)

    last_seen       = st.session_state.get("last_seen_timestamp", "")
    notifications   = check_status_notifications(candidate_apps, last_seen)
    newly_cancelled = check_interview_deadlines(uid, candidate_apps)

    if newly_cancelled:
        st.markdown('<div class="section-heading">⏰ Interview Deadlines Passed</div>', unsafe_allow_html=True)
        for nc in newly_cancelled:
            st.markdown(
                f'<div class="notif-banner notif-rejected"><span class="nb-icon">⏰</span>'
                f'<div><div class="nb-title">Interview session for <strong>{nc.get("job_title","—")}</strong> at {nc.get("company_name","—")} was cancelled — deadline passed</div>'
                f'<div class="nb-sub">// you did not complete the AI interview within 48 hours</div></div></div>',
                unsafe_allow_html=True
            )
        st.markdown("<br>", unsafe_allow_html=True)

    if notifications:
        st.markdown('<div class="section-heading">🔔 Updates since last login</div>', unsafe_allow_html=True)
        for notif in notifications:
            status    = notif.get("status", "")
            notif_cls = {"Shortlisted": "notif-shortlisted", "Hired": "notif-hired", "Rejected": "notif-rejected",
                         "Interview Scheduled": "notif-hired", "Cancelled": "notif-rejected"}.get(status, "notif-shortlisted")
            icon = {"Shortlisted": "⭐", "Hired": "🎉", "Rejected": "📭", "Interview Scheduled": "📅", "Cancelled": "⏰"}.get(status, "🔔")
            st.markdown(
                f'<div class="notif-banner {notif_cls}"><span class="nb-icon">{icon}</span>'
                f'<div><div class="nb-title"><strong>{notif.get("job_title","—")}</strong> at {notif.get("company_name","—")} — status changed to: {status}</div>'
                f'<div class="nb-sub">// updated {notif.get("last_status_change","")[:10]}</div></div></div>',
                unsafe_allow_html=True
            )
        st.markdown("<br>", unsafe_allow_html=True)

    total_applied  = len(candidate_apps)
    interviews_sch = sum(1 for a in candidate_apps if a.get("status") == "Interview Scheduled")
    reports_rdy    = sum(1 for a in candidate_apps if a.get("interview_report_url") and
                         a.get("status") in {"Report Generated", "Shortlisted", "Hired", "Rejected"})

    if total_applied > 0:
        active_count = get_active_application_count(candidate_apps)
        st.markdown('<div class="section-heading">Application snapshot</div>', unsafe_allow_html=True)
        as1, as2, as3, as4 = st.columns(4, gap="small")
        for col, (n, sfx, lbl) in zip([as1, as2, as3, as4], [
            (active_count,   "", "active applications"),
            (interviews_sch, "", "interviews scheduled"),
            (reports_rdy,    "", "reports ready"),
            (sum(1 for a in candidate_apps if a.get("status") == "Shortlisted"), "", "shortlisted"),
        ]):
            with col:
                st.markdown(f'<div class="stat-card"><div class="stat-num">{n}<span>{sfx}</span></div><div class="stat-label">{lbl}</div></div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    if not st.session_state.profile_setup:
        st.markdown("""
        <div class="setup-banner"><span class="banner-icon">📋</span>
        <div><h3>Set up your profile to get started</h3>
        <p>Your profile lets Gemini generate role-specific, personalised interview questions.<br>Takes about 2 minutes — makes a big difference.</p>
        </div></div>
        """, unsafe_allow_html=True)
        bc1, bc2, bc3 = st.columns([1, 1, 1])
        with bc2:
            if st.button("Set Up Profile →", use_container_width=True, key="goto_profile_btn"):
                st.session_state.goto_profile_tab = True
                st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)

    st.markdown('<div class="section-heading">Quick actions</div>', unsafe_allow_html=True)
    qa1, qa2, qa3 = st.columns(3, gap="medium")
    with qa1:
        st.markdown("""<div class="qa-card"><span class="qa-icon">🎤</span><div><div class="qa-title">New Interview</div><div class="qa-sub">// start a session</div></div></div>""", unsafe_allow_html=True)
        if st.button("Start →", key="dash_interview", use_container_width=True):
            navigate_to("interview")
    with qa2:
        st.markdown("""<div class="qa-card"><span class="qa-icon">🔍</span><div><div class="qa-title">Browse Jobs</div><div class="qa-sub">// find openings</div></div></div>""", unsafe_allow_html=True)
        st.button("Browse →", key="dash_jobs", use_container_width=True)
    with qa3:
        st.markdown("""<div class="qa-card"><span class="qa-icon">📋</span><div><div class="qa-title">My Applications</div><div class="qa-sub">// track progress</div></div></div>""", unsafe_allow_html=True)
        st.button("View →", key="dash_myapps", use_container_width=True)

    if st.session_state.profile_setup:
        st.markdown('<div class="section-heading">Profile summary</div>', unsafe_allow_html=True)
        profile = load_candidate_profile(uid)
        if profile:
            _photo_b64 = profile.get("profile_photo_b64", "")
            if _photo_b64:
                _uri = _photo_b64 if _photo_b64.startswith("data:") else f"data:image/jpeg;base64,{_photo_b64}"
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:1rem;margin-bottom:1.2rem;">'
                    f'<img src="{_uri}" style="width:60px;height:60px;border-radius:10px;object-fit:cover;border:1px solid var(--border);">'
                    f'<div><div style="font-family:\'Sora\',sans-serif;font-size:1.05rem;font-weight:700;color:var(--text-h);letter-spacing:-0.3px;">{profile.get("full_name", st.session_state.user_name)}</div>'
                    f'<div style="font-family:\'DM Mono\',monospace;font-size:0.72rem;color:var(--text-muted);margin-top:3px;letter-spacing:0.3px;">// {profile.get("job_role", "")}</div>'
                    f'</div></div>', unsafe_allow_html=True
                )
            p1, p2, p3, p4 = st.columns(4, gap="small")
            for col, (n, l) in zip([p1, p2, p3, p4], [
                (profile.get("job_role", "—"),          "target role"),
                (str(profile.get("years_experience",0)), "yrs experience"),
                (profile.get("experience_level", "—"),   "level"),
                (profile.get("interview_type", "—"),     "interview type"),
            ]):
                with col:
                    st.markdown(f'<div class="stat-card"><div class="stat-num" style="font-size:1rem;">{n}</div><div class="stat-label">{l}</div></div>', unsafe_allow_html=True)
            ps = profile.get("primary_skills", "")
            if ps:
                st.markdown("<br>", unsafe_allow_html=True)
                pills = "".join(f'<span class="skill-tag">{s.strip()}</span>' for s in ps.split(",") if s.strip())
                st.markdown(
                    f'<div class="ml-card" style="padding:1rem 1.4rem;">'
                    f'<div style="font-family:\'DM Mono\',monospace;font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:0.6rem;">// primary skills</div>'
                    f'{pills}</div>', unsafe_allow_html=True
                )

    st.markdown('<div class="section-heading">Recent interviews</div>', unsafe_allow_html=True)
    st.markdown("""<div class="empty-state"><span class="es-icon"><i class="fa-regular fa-folder-open"></i></span><p>// no sessions yet — start one above</p></div>""", unsafe_allow_html=True)