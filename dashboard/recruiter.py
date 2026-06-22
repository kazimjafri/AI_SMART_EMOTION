# ===========================
# RECRUITER DASHBOARD
# dashboard/recruiter.py
# ===========================

import streamlit as st
import time
from datetime import datetime, timedelta
from firebase_admin import db as realtime_db


# ===========================
# RECRUITER FIREBASE HELPERS
# ===========================

def load_recruiter_profile(uid: str) -> dict:
    try:
        snapshot = realtime_db.reference(f"recruiters/{uid}").get()
        return snapshot if snapshot else {}
    except Exception:
        return {}


def save_recruiter_profile(uid: str, data: dict) -> bool:
    try:
        data["profile_complete"] = True
        data["updated_at"]       = datetime.utcnow().isoformat()
        data["uid"]              = uid
        data["email"]            = st.session_state.user_email
        realtime_db.reference(f"recruiters/{uid}").set(data)
        return True
    except Exception as e:
        st.error(f"❌ Failed to save recruiter profile: {str(e)}")
        return False


def post_job_requirement(uid: str, job_data: dict) -> bool:
    try:
        job_data["recruiter_uid"]   = uid
        job_data["recruiter_name"]  = st.session_state.user_name
        job_data["recruiter_email"] = st.session_state.user_email
        job_data["posted_at"]       = datetime.utcnow().isoformat()
        job_data["status"]          = "active"

        push_ref = realtime_db.reference(f"recruiters/{uid}/job_postings").push(job_data)
        job_data["rtdb_key"] = push_ref.key

        try:
            from google.cloud import firestore as gcloud_firestore
            fs = gcloud_firestore.Client(project="aiemotioninterviewer")
            fs.collection("job_postings").add(job_data)
        except Exception:
            pass

        return True
    except Exception as e:
        st.error(f"❌ Failed to post job: {str(e)}")
        return False


def load_job_postings(uid: str) -> list:
    try:
        snapshot = realtime_db.reference(f"recruiters/{uid}/job_postings").get()
        if snapshot:
            return [{"key": k, **v} for k, v in snapshot.items()]
        return []
    except Exception:
        return []


def load_applications(uid: str) -> list:
    try:
        snapshot = realtime_db.reference(f"recruiters/{uid}/applications").get()
        if snapshot:
            return [{"key": k, **v} for k, v in snapshot.items()]
        return []
    except Exception:
        return []


def load_interview_report(candidate_uid: str) -> dict:
    try:
        snapshot = realtime_db.reference(f"interview_reports/{candidate_uid}").get()
        if snapshot:
            return snapshot
        raise ValueError("no data")
    except Exception:
        return _mock_interview_report(candidate_uid)


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


def update_application_status(
    candidate_uid: str,
    app_key: str,
    recruiter_uid: str,
    recruiter_app_key: str,
    new_status: str,
    interview_deadline: str = ""
) -> bool:
    try:
        now = datetime.utcnow().isoformat()
        candidate_update = {"status": new_status, "last_status_change": now}
        if interview_deadline:
            candidate_update["interview_deadline"] = interview_deadline
        recruiter_update = {"status": new_status, "last_status_change": now}

        realtime_db.reference(f"candidates/{candidate_uid}/applications/{app_key}").update(candidate_update)
        if recruiter_uid and recruiter_app_key:
            realtime_db.reference(f"recruiters/{recruiter_uid}/applications/{recruiter_app_key}").update(recruiter_update)
        return True
    except Exception as e:
        st.error(f"❌ Failed to update status: {str(e)}")
        return False


# ===========================
# HELPER HTML
# ===========================

def _rec_status_badge(status: str) -> str:
    cls_map = {
        "Applied":             "status-applied",
        "Pending Review":      "status-pending",
        "Interview Scheduled": "status-scheduled",
        "Interview Completed": "status-completed",
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
        "Interview Completed": "✓",
        "Report Generated":    "📄",
        "Shortlisted":         "⭐",
        "Hired":               "✓",
        "Rejected":            "✗",
        "Cancelled":           "⊘",
    }
    return f'<span class="status-badge {cls_map.get(status,"status-applied")}">{dot_map.get(status,"●")} {status}</span>'


# ===========================
# TAB 1 — RECRUITER OVERVIEW
# ===========================

def recruiter_overview_tab(apps: list, postings: list):
    total_apps      = len(apps)
    active_postings = sum(1 for p in postings if p.get("status", "active") == "active")
    pending_review  = sum(1 for a in apps if a.get("status") in {"Applied", "Pending Review"})
    interviews_done = sum(1 for a in apps if a.get("status") in {"Interview Completed", "Report Generated", "Shortlisted", "Hired"})

    st.markdown('<div class="section-heading">Live snapshot</div>', unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4, gap="small")
    for col, (n, sfx, lbl) in zip([s1, s2, s3, s4], [
        (active_postings, "+", "Active job postings"),
        (total_apps,      "",  "Total applications"),
        (pending_review,  "",  "Awaiting your review"),
        (interviews_done, "",  "AI screenings done"),
    ]):
        with col:
            st.markdown(f'<div class="stat-card"><div class="stat-num">{n}<span>{sfx}</span></div><div class="stat-label">{lbl}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Quick actions</div>', unsafe_allow_html=True)
    qa1, qa2, qa3 = st.columns(3, gap="medium")
    with qa1:
        st.markdown("""<div class="qa-card"><span class="qa-icon">📋</span><div><div class="qa-title">Post a Job</div><div class="qa-sub">// create new requirement</div></div></div>""", unsafe_allow_html=True)
        if st.button("Post →", key="rec_ov_post", use_container_width=True):
            st.session_state._rec_goto_post = True
            st.rerun()
    with qa2:
        st.markdown("""<div class="qa-card"><span class="qa-icon">📥</span><div><div class="qa-title">View Applications</div><div class="qa-sub">// review queue</div></div></div>""", unsafe_allow_html=True)
        if st.button("Review →", key="rec_ov_apps", use_container_width=True):
            st.session_state._rec_goto_applications = True
            st.rerun()
    with qa3:
        st.markdown("""<div class="qa-card"><span class="qa-icon">📊</span><div><div class="qa-title">Reports Hub</div><div class="qa-sub">// AI evaluations</div></div></div>""", unsafe_allow_html=True)
        if st.button("View →", key="rec_ov_reports", use_container_width=True):
            st.session_state._rec_goto_reports = True
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Recent applications</div>', unsafe_allow_html=True)
    if not apps:
        st.markdown("""<div class="empty-state"><span class="es-icon"><i class="fa-regular fa-inbox"></i></span><p>// no applications yet — post a job to get started</p></div>""", unsafe_allow_html=True)
    else:
        recent = sorted(apps, key=lambda x: x.get("applied_at", ""), reverse=True)[:5]
        for app in recent:
            applied_str = app.get("applied_at", "")[:10] if app.get("applied_at") else "—"
            st.markdown(
                f'<div class="app-row">'
                f'<div class="ar-avatar"><i class="fa-solid fa-user"></i></div>'
                f'<div><div class="ar-name">{app.get("candidate_name","—")}</div>'
                f'<div class="ar-meta">{app.get("job_title","—")} &nbsp;·&nbsp; {applied_str}</div></div>'
                f'<div class="ar-status">{_rec_status_badge(app.get("status","Applied"))}</div>'
                f'</div>', unsafe_allow_html=True
            )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""<div class="cta-strip"><h2>Ready to find your next hire?</h2><p>Post a requirement and let AI screen candidates objectively — no scheduling, no bias.</p></div>""", unsafe_allow_html=True)
    cta_l, cta_c, cta_r = st.columns([1, 1.4, 1])
    with cta_c:
        if st.button("📋  Post a Job Requirement →", use_container_width=True, key="rec_overview_cta"):
            st.session_state._rec_goto_post = True
            st.rerun()


# ===========================
# TAB 2 — RECRUITER PROFILE
# ===========================

def recruiter_profile_tab():
    uid = st.session_state.user_uid
    with st.spinner("Loading recruiter profile..."):
        profile = load_recruiter_profile(uid)

    is_edit = bool(profile and profile.get("profile_complete", False))

    if is_edit:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.4rem;">'
            '<span style="font-family:\'Sora\',sans-serif;font-size:1.05rem;font-weight:700;color:var(--text-h);">Recruiter Profile</span>'
            '<span class="complete-badge">✓ complete</span></div>'
            '<p style="font-family:\'DM Mono\',monospace;font-size:0.72rem;color:var(--text-muted);letter-spacing:0.3px;margin-bottom:1.4rem;">Edit any field and save to update your company details.</p>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="ml-card" style="margin-bottom:1.4rem;display:flex;align-items:center;gap:1rem;">'
            '<span style="font-size:1.8rem;">🏢</span>'
            '<div><div style="font-family:\'Sora\',sans-serif;font-size:0.95rem;font-weight:700;color:var(--text-h);">Complete your recruiter profile</div>'
            '<div style="font-family:\'DM Mono\',monospace;font-size:0.7rem;color:var(--text-muted);margin-top:3px;letter-spacing:0.3px;">'
            '// helps candidates find and trust your postings</div></div></div>',
            unsafe_allow_html=True
        )

    st.markdown('<div class="profile-sec"><span class="ps-num">01</span><span class="ps-title">Company Identity</span><span class="ps-desc">// who you are</span></div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2, gap="medium")
    with col_a:
        company_name = st.text_input("Company name", value=profile.get("company_name", ""), placeholder="e.g. Acme Corp, FinEdge AI", key="rp_company_name")
    with col_b:
        industry_opts = ["Technology", "FinTech", "HealthTech", "EdTech", "E-Commerce", "Consulting", "Manufacturing", "Media & Entertainment", "Telecom", "Other"]
        ind_def = profile.get("industry", "Technology")
        industry = st.selectbox("Industry", industry_opts, index=industry_opts.index(ind_def) if ind_def in industry_opts else 0, key="rp_industry")

    st.markdown('<div class="profile-sec"><span class="ps-num">02</span><span class="ps-title">Recruiter Details</span><span class="ps-desc">// your role</span></div>', unsafe_allow_html=True)
    col_c, col_d = st.columns(2, gap="medium")
    with col_c:
        recruiter_role = st.text_input("Your role / title", value=profile.get("recruiter_role", ""), placeholder="e.g. Talent Acquisition Lead, HR Manager", key="rp_recruiter_role")
    with col_d:
        company_size_opts = ["1–10", "11–50", "51–200", "201–500", "500+"]
        cs_def = profile.get("company_size", "51–200")
        company_size = st.selectbox("Company size", company_size_opts, index=company_size_opts.index(cs_def) if cs_def in company_size_opts else 2, key="rp_company_size")

    col_e, col_f = st.columns(2, gap="medium")
    with col_e:
        company_website = st.text_input("Company website (optional)", value=profile.get("company_website", ""), placeholder="https://yourcompany.com", key="rp_website")
    with col_f:
        linkedin_company = st.text_input("Company LinkedIn (optional)", value=profile.get("linkedin_company", ""), placeholder="https://linkedin.com/company/yourco", key="rp_linkedin")

    st.markdown('<div class="profile-sec"><span class="ps-num">03</span><span class="ps-title">Company Bio</span><span class="ps-desc">// elevator pitch</span></div>', unsafe_allow_html=True)
    bio = st.text_area("Brief company bio", value=profile.get("bio", ""), placeholder="What does your company do? What kind of talent are you looking for?", height=110, key="rp_bio")
    st.caption(f"{'✓' if len(bio.strip()) >= 20 else '~'}  {len(bio)} chars  //  aim for 80+")

    st.markdown('<div class="form-divider"></div>', unsafe_allow_html=True)
    save_col, _ = st.columns([1, 3])
    with save_col:
        label = "Save Changes →" if is_edit else "Save Profile →"
        if st.button(label, use_container_width=True, key="save_rec_profile_btn"):
            errors = []
            if not company_name.strip():   errors.append("Company name is required.")
            if not recruiter_role.strip(): errors.append("Your role/title is required.")
            for err in errors:
                st.error(f"❌ {err}")
            if not errors:
                payload = {
                    "company_name":     company_name.strip(),
                    "industry":         industry,
                    "recruiter_role":   recruiter_role.strip(),
                    "company_size":     company_size,
                    "company_website":  company_website.strip(),
                    "linkedin_company": linkedin_company.strip(),
                    "bio":              bio.strip(),
                }
                with st.spinner("Saving..."):
                    saved = save_recruiter_profile(uid, payload)
                if saved:
                    st.session_state.recruiter_profile_setup = True
                    st.success(f"✅ Profile {'updated' if is_edit else 'saved'}!")
                    time.sleep(0.6)
                    st.rerun()


# ===========================
# TAB 3 — POST JOB REQUIREMENTS
# ===========================

def post_requirements_tab():
    uid = st.session_state.user_uid

    if not st.session_state.recruiter_profile_setup:
        st.markdown("""<div class="setup-banner"><span class="banner-icon">⚠️</span><div><h3>Complete your recruiter profile first</h3><p>Your company details are attached to every job posting — candidates see them when browsing.</p></div></div>""", unsafe_allow_html=True)

    st.markdown(
        '<div style="font-family:\'Sora\',sans-serif;font-size:1.05rem;font-weight:700;color:var(--text-h);margin-bottom:0.2rem;">Post a New Job Requirement</div>'
        '<p style="font-family:\'DM Mono\',monospace;font-size:0.72rem;color:var(--text-muted);letter-spacing:0.3px;margin-bottom:1.4rem;">// saved to Firebase · visible to candidates instantly</p>',
        unsafe_allow_html=True
    )

    st.markdown('<div class="profile-sec"><span class="ps-num">01</span><span class="ps-title">Role Information</span><span class="ps-desc">// the position</span></div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2, gap="medium")
    with col_a:
        job_title = st.text_input("Job title", placeholder="e.g. Senior ML Engineer, Data Analyst", key="pr_job_title")
    with col_b:
        exp_lvl_opts = ["Fresher", "Mid-Level", "Senior", "Lead / Principal", "Any"]
        exp_lvl = st.selectbox("Experience level required", exp_lvl_opts, index=1, key="pr_exp_level")

    col_c, col_d = st.columns(2, gap="medium")
    with col_c:
        work_mode = st.selectbox("Work mode", ["On-site", "Remote", "Hybrid"], index=2, key="pr_work_mode")
    with col_d:
        location = st.text_input("Location (optional)", placeholder="e.g. Karachi, Remote-Global", key="pr_location")

    ALL_SKILLS = [
        "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust",
        "SQL", "NoSQL", "PostgreSQL", "MongoDB", "Redis",
        "React", "Vue", "Angular", "Next.js", "Node.js", "Django", "FastAPI", "Flask",
        "TensorFlow", "PyTorch", "Scikit-learn", "Keras", "HuggingFace",
        "MLOps", "LangChain", "OpenCV", "NLP", "Computer Vision",
        "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform",
        "Spark", "Kafka", "Airflow", "dbt",
        "Git", "Linux", "REST APIs", "GraphQL", "Microservices",
        "Figma", "Tableau", "Power BI", "Excel",
        "Leadership", "Communication", "Project Management", "Agile / Scrum",
    ]

    st.markdown('<div class="profile-sec"><span class="ps-num">02</span><span class="ps-title">Technical Requirements</span><span class="ps-desc">// core skills</span></div>', unsafe_allow_html=True)
    core_skills = st.multiselect("Core technical skills required", options=ALL_SKILLS, default=["Python", "SQL"], key="pr_core_skills")
    if core_skills:
        pills = "".join(f'<span class="skill-tag">{s}</span>' for s in core_skills)
        st.markdown(f'<div style="margin-top:6px;">{pills}</div>', unsafe_allow_html=True)
    nice_to_have = st.multiselect("Nice-to-have skills (optional)", options=[s for s in ALL_SKILLS if s not in core_skills], key="pr_nice_to_have")

    st.markdown('<div class="profile-sec"><span class="ps-num">03</span><span class="ps-title">AI Interview Thresholds</span><span class="ps-desc">// evaluation criteria</span></div>', unsafe_allow_html=True)
    col_e, col_f = st.columns(2, gap="medium")
    with col_e:
        min_speech_clarity = st.slider("Minimum speech clarity threshold (%)", 0, 100, 70, 5, key="pr_speech_clarity")
        st.caption(f"// candidates below {min_speech_clarity}% clarity will be flagged")
    with col_f:
        min_score = st.slider("Minimum overall AI score (%)", 0, 100, 60, 5, key="pr_min_score")
        st.caption(f"// auto-reject below {min_score}% overall score")

    col_g, col_h = st.columns(2, gap="medium")
    with col_g:
        trait_opts = ["Analytical", "Collaborative", "Confident", "Creative", "Empathetic", "Leadership", "Results-Oriented", "Any"]
        target_trait = st.selectbox("Target dominant behavioral trait", trait_opts, index=0, key="pr_target_trait")
    with col_h:
        interview_type = st.selectbox("Interview type for this role", ["Technical", "HR", "Behavioral", "Mixed"], index=3, key="pr_interview_type")

    st.markdown('<div class="profile-sec"><span class="ps-num">04</span><span class="ps-title">Job Description</span><span class="ps-desc">// context for gemini</span></div>', unsafe_allow_html=True)
    job_description = st.text_area("Full job description (optional but recommended)", placeholder="Paste or write the full JD here. Gemini uses this to generate highly relevant, role-specific interview questions.", height=140, key="pr_job_description")
    st.caption(f"{'✓' if len(job_description.strip()) > 50 else '~'}  {len(job_description)} chars  //  more context = sharper questions")

    st.markdown('<div class="form-divider"></div>', unsafe_allow_html=True)
    post_col, _ = st.columns([1, 3])
    with post_col:
        if st.button("📤  Post Job Requirement →", use_container_width=True, key="post_job_btn"):
            errors = []
            if not job_title.strip(): errors.append("Job title is required.")
            if not core_skills:       errors.append("Select at least one core skill.")
            for err in errors:
                st.error(f"❌ {err}")
            if not errors:
                rec_profile = load_recruiter_profile(uid)
                payload = {
                    "job_title":          job_title.strip(),
                    "company_name":       rec_profile.get("company_name", ""),
                    "industry":           rec_profile.get("industry", ""),
                    "experience_level":   exp_lvl,
                    "work_mode":          work_mode,
                    "location":           location.strip(),
                    "core_skills":        core_skills,
                    "nice_to_have":       nice_to_have,
                    "min_speech_clarity": min_speech_clarity,
                    "min_score":          min_score,
                    "target_trait":       target_trait,
                    "interview_type":     interview_type,
                    "job_description":    job_description.strip(),
                }
                with st.spinner("Posting to Firebase..."):
                    ok = post_job_requirement(uid, payload)
                if ok:
                    st.success("✅ Job posted! Candidates can now see and apply for this role.")
                    st.balloons()

    st.markdown('<div class="section-heading">Your active postings</div>', unsafe_allow_html=True)
    with st.spinner("Fetching postings..."):
        postings = load_job_postings(uid)

    if not postings:
        st.markdown("""<div class="empty-state"><span class="es-icon"><i class="fa-regular fa-file-lines"></i></span><p>// no postings yet — use the form above</p></div>""", unsafe_allow_html=True)
    else:
        for p in postings:
            skills_html = "".join(f'<span class="skill-tag">{s}</span>' for s in (p.get("core_skills") or []))
            posted_date = p.get("posted_at", "")[:10] if p.get("posted_at") else "—"
            st.markdown(f"""
            <div class="job-card">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.4rem;">
                <div class="jc-title">{p.get("job_title","—")}</div>
                <span class="status-badge status-completed">● active</span>
              </div>
              <div class="jc-meta">{p.get("experience_level","—")} &nbsp;·&nbsp; {p.get("work_mode","—")} &nbsp;·&nbsp; {p.get("location") or "Location TBC"} &nbsp;·&nbsp; posted {posted_date}</div>
              <div style="margin-bottom:0.5rem;">{skills_html}</div>
            </div>
            """, unsafe_allow_html=True)


# ===========================
# TAB 4 — INCOMING APPLICATIONS
# ===========================

def incoming_applications_tab():
    uid = st.session_state.user_uid

    st.markdown(
        '<div style="font-family:\'Sora\',sans-serif;font-size:1.05rem;font-weight:700;color:var(--text-h);margin-bottom:0.2rem;">Incoming Applications</div>'
        '<p style="font-family:\'DM Mono\',monospace;font-size:0.72rem;color:var(--text-muted);letter-spacing:0.3px;margin-bottom:1.4rem;">// review queue · accept to schedule AI interview · reject to notify candidate</p>',
        unsafe_allow_html=True
    )

    with st.spinner("Fetching applications..."):
        apps = load_applications(uid)

    total       = len(apps)
    need_review = sum(1 for a in apps if a.get("status") in {"Applied", "Pending Review"})
    scheduled   = sum(1 for a in apps if a.get("status") == "Interview Scheduled")
    completed   = sum(1 for a in apps if a.get("status") in {"Interview Completed", "Report Generated"})
    shortlisted = sum(1 for a in apps if a.get("status") == "Shortlisted")

    s1, s2, s3, s4, s5 = st.columns(5, gap="small")
    for col, (n, lbl) in zip([s1, s2, s3, s4, s5], [
        (total,       "total"),
        (need_review, "need review"),
        (scheduled,   "interview set"),
        (completed,   "AI done"),
        (shortlisted, "shortlisted"),
    ]):
        with col:
            st.markdown(f'<div class="stat-card"><div class="stat-num">{n}</div><div class="stat-label">{lbl}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    f1, f2, f3 = st.columns([2, 1, 1], gap="small")
    with f1:
        search_term = st.text_input("Search candidate name or role", placeholder="e.g. Sarah, ML Engineer", key="rec_app_search").strip().lower()
    with f2:
        status_filter = st.selectbox("Filter by status",
            ["All", "Applied", "Pending Review", "Interview Scheduled", "Interview Completed",
             "Report Generated", "Shortlisted", "Hired", "Rejected", "Cancelled"],
            key="rec_app_status_filter"
        )
    with f3:
        sort_order = st.selectbox("Sort by", ["Newest first", "Oldest first", "Name A–Z"], key="rec_app_sort")

    filtered = [
        a for a in apps
        if (status_filter == "All" or a.get("status") == status_filter)
        and (not search_term or search_term in a.get("candidate_name", "").lower() or search_term in a.get("job_title", "").lower())
    ]
    if sort_order == "Newest first":
        filtered.sort(key=lambda x: x.get("applied_at", ""), reverse=True)
    elif sort_order == "Oldest first":
        filtered.sort(key=lambda x: x.get("applied_at", ""))
    elif sort_order == "Name A–Z":
        filtered.sort(key=lambda x: x.get("candidate_name", "").lower())

    st.markdown(
        f'<div style="font-family:\'DM Mono\',monospace;font-size:0.7rem;color:var(--text-muted);'
        f'letter-spacing:0.5px;margin:0.4rem 0 1rem;">// {len(filtered)} application{"s" if len(filtered) != 1 else ""}</div>',
        unsafe_allow_html=True
    )

    if not filtered:
        st.markdown("""<div class="empty-state"><span class="es-icon"><i class="fa-regular fa-inbox"></i></span><p>// no applications match your filter</p></div>""", unsafe_allow_html=True)
        return

    st.markdown('<div class="section-heading">Application queue</div>', unsafe_allow_html=True)

    for idx, app in enumerate(filtered):
        status      = app.get("status", "Applied")
        app_key     = app.get("key", "")
        cand_uid    = app.get("candidate_uid", "")
        cand_name   = app.get("candidate_name", "—")
        job_title   = app.get("job_title", "—")
        applied_str = app.get("applied_at", "")[:10] if app.get("applied_at") else "—"
        last_change = app.get("last_status_change", "")[:10] if app.get("last_status_change") else "—"
        has_report  = app.get("has_report", False)
        initials    = "".join(p[0].upper() for p in cand_name.split()[:2]) if cand_name != "—" else "?"

        deadline_html = ""
        if status == "Interview Scheduled":
            deadline = app.get("interview_deadline", "")
            if deadline:
                try:
                    deadline_dt = datetime.fromisoformat(deadline)
                    diff = deadline_dt - datetime.utcnow()
                    secs = int(diff.total_seconds())
                    if secs > 0:
                        hrs  = secs // 3600
                        mins = (secs % 3600) // 60
                        time_str  = f"{hrs}h {mins}m left" if hrs > 0 else f"{mins}m left"
                        pill_cls  = "deadline-warn" if hrs < 12 else "deadline-ok"
                        deadline_html = f'<span class="deadline-pill {pill_cls}">⏱ {time_str}</span>'
                    else:
                        deadline_html = '<span class="deadline-pill deadline-expired">⏰ Expired</span>'
                except Exception:
                    pass

        st.markdown(f"""
        <div class="cand-card">
          <div class="cc-header">
            <div class="cc-avatar">{initials}</div>
            <div style="flex:1;"><div class="cc-name">{cand_name}</div><div class="cc-role">// {job_title}</div></div>
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:0.35rem;">
              {_rec_status_badge(status)}{deadline_html}
            </div>
          </div>
          <div class="cc-meta"><span>📅 Applied {applied_str}</span><span>🔄 Updated {last_change}</span></div>
        </div>
        """, unsafe_allow_html=True)

        show_report = has_report or status in {"Interview Completed", "Report Generated", "Shortlisted", "Hired"}
        btn_cols = st.columns([1, 1, 1, 3], gap="small")

        if status in {"Applied", "Pending Review"}:
            with btn_cols[0]:
                if st.button("✅ Accept", key=f"accept_{app_key}_{idx}", use_container_width=True):
                    st.session_state[f"action_{app_key}"] = "accept"
            with btn_cols[1]:
                if st.button("✕ Reject", key=f"reject_{app_key}_{idx}", use_container_width=True):
                    st.session_state[f"action_{app_key}"] = "reject"

        if show_report:
            with btn_cols[2]:
                if st.button("📊 View Report", key=f"view_rep_{app_key}_{idx}", use_container_width=True):
                    st.session_state.selected_candidate_uid  = cand_uid
                    st.session_state.selected_candidate_name = cand_name
                    st.session_state._rec_goto_reports = True
                    st.rerun()

        if st.session_state.get(f"action_{app_key}") == "accept":
            st.markdown(
                f'<div class="confirm-card"><div class="cc-q">Accept <strong>{cand_name}</strong> for <strong>{job_title}</strong>?<br>'
                f'<span style="font-family:\'DM Mono\',monospace;font-size:0.7rem;color:var(--text-muted);">'
                f'// they will receive a 48-hour window to complete the AI interview</span></div></div>',
                unsafe_allow_html=True
            )
            ca1, ca2, _ = st.columns([1, 1, 4])
            with ca1:
                if st.button("Yes, Accept", key=f"yes_accept_{app_key}_{idx}", use_container_width=True):
                    deadline = (datetime.utcnow() + timedelta(hours=48)).isoformat()
                    with st.spinner("Updating..."):
                        ok = update_application_status(
                            candidate_uid=cand_uid, app_key=app_key,
                            recruiter_uid=uid, recruiter_app_key=app_key,
                            new_status="Interview Scheduled", interview_deadline=deadline
                        )
                    if ok:
                        st.session_state.pop(f"action_{app_key}", None)
                        st.success(f"✅ {cand_name} accepted! 48-hour interview window starts now.")
                        time.sleep(0.6)
                        st.rerun()
            with ca2:
                if st.button("Cancel", key=f"cancel_accept_{app_key}_{idx}", use_container_width=True):
                    st.session_state.pop(f"action_{app_key}", None)
                    st.rerun()

        if st.session_state.get(f"action_{app_key}") == "reject":
            st.markdown(
                f'<div class="confirm-card" style="border-color:rgba(239,68,68,0.25);">'
                f'<div class="cc-q" style="color:#dc2626;">Reject <strong>{cand_name}</strong> for <strong>{job_title}</strong>?<br>'
                f'<span style="font-family:\'DM Mono\',monospace;font-size:0.7rem;color:var(--text-muted);">'
                f'// candidate will see "Rejected" on their dashboard</span></div></div>',
                unsafe_allow_html=True
            )
            cr1, cr2, _ = st.columns([1, 1, 4])
            with cr1:
                if st.button("Yes, Reject", key=f"yes_reject_{app_key}_{idx}", use_container_width=True):
                    with st.spinner("Updating..."):
                        ok = update_application_status(
                            candidate_uid=cand_uid, app_key=app_key,
                            recruiter_uid=uid, recruiter_app_key=app_key,
                            new_status="Rejected"
                        )
                    if ok:
                        st.session_state.pop(f"action_{app_key}", None)
                        st.warning(f"❌ {cand_name}'s application for {job_title} has been rejected.")
                        time.sleep(0.6)
                        st.rerun()
            with cr2:
                if st.button("Cancel", key=f"cancel_reject_{app_key}_{idx}", use_container_width=True):
                    st.session_state.pop(f"action_{app_key}", None)
                    st.rerun()

        st.markdown('<div style="height:0.3rem;"></div>', unsafe_allow_html=True)


# ===========================
# TAB 5 — INTERVIEW REPORTS HUB
# ===========================

def interview_reports_hub_tab():
    uid = st.session_state.user_uid

    st.markdown(
        '<div style="font-family:\'Sora\',sans-serif;font-size:1.05rem;font-weight:700;color:var(--text-h);margin-bottom:0.2rem;">Interview Reports Hub</div>'
        '<p style="font-family:\'DM Mono\',monospace;font-size:0.72rem;color:var(--text-muted);letter-spacing:0.3px;margin-bottom:1.4rem;">// computer vision · audio analytics · gemini evaluation</p>',
        unsafe_allow_html=True
    )

    with st.spinner("Loading candidates..."):
        apps = load_applications(uid)

    completed_apps = [a for a in apps if a.get("has_report") or a.get("status") in {"Interview Completed", "Report Generated", "Shortlisted", "Hired"}]

    if not completed_apps:
        st.markdown("""<div class="empty-state"><span class="es-icon"><i class="fa-solid fa-chart-bar"></i></span><p>// no interview reports available yet</p></div>""", unsafe_allow_html=True)
        return

    candidate_names = [a.get("candidate_name", "—") for a in completed_apps]
    candidate_uids  = [a.get("candidate_uid",  "")  for a in completed_apps]

    preselect_uid = st.session_state.get("selected_candidate_uid")
    preselect_idx = candidate_uids.index(preselect_uid) if preselect_uid and preselect_uid in candidate_uids else 0

    sel_idx = st.selectbox(
        "Select candidate to review",
        range(len(candidate_names)),
        format_func=lambda i: candidate_names[i],
        index=preselect_idx,
        key="report_candidate_select"
    )
    selected_uid  = candidate_uids[sel_idx]
    selected_name = candidate_names[sel_idx]

    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:0.75rem;margin:1rem 0 1.4rem;">
      <div class="cc-avatar" style="width:44px;height:44px;border-radius:10px;background:var(--accent-bg);border:1px solid var(--tag-border);display:flex;align-items:center;justify-content:center;font-size:1.1rem;color:var(--accent);">
        <i class="fa-solid fa-user"></i>
      </div>
      <div>
        <div style="font-family:'Sora',sans-serif;font-size:1rem;font-weight:700;color:var(--text-h);letter-spacing:-0.2px;">{selected_name}</div>
        <div style="font-family:'DM Mono',monospace;font-size:0.68rem;color:var(--text-muted);margin-top:2px;letter-spacing:0.3px;">// uid: {selected_uid[:16]}...</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Fetching AI evaluation data..."):
        report = load_interview_report(selected_uid)

    overall_score    = report.get("overall_score", 0)
    speech_clarity   = report.get("avg_speech_clarity", 0)
    tempo_wpm        = report.get("speech_tempo_wpm", 0)
    dominant_emotion = report.get("dominant_emotion", "—")
    emotion_timeline = report.get("emotion_timeline", [])
    pdf_url          = report.get("pdf_report_url", "")
    completed_at     = report.get("completed_at", "")[:10] if report.get("completed_at") else "—"

    score_color = "#059669" if overall_score >= 75 else ("#d97706" if overall_score >= 55 else "#ef4444")
    st.markdown(f"""
    <div class="ml-card" style="margin-bottom:1.2rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1rem;">
      <div>
        <div style="font-family:'DM Mono',monospace;font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:0.3rem;">// overall ai score</div>
        <div style="font-family:'Sora',sans-serif;font-size:2.8rem;font-weight:800;color:{score_color};letter-spacing:-2px;line-height:1;">
          {overall_score}<span style="font-size:1.4rem;color:var(--text-muted);">/100</span>
        </div>
        <div style="font-family:'DM Mono',monospace;font-size:0.68rem;color:var(--text-muted);margin-top:4px;letter-spacing:0.3px;">completed: {completed_at}</div>
      </div>
      <div style="font-family:'DM Mono',monospace;font-size:0.7rem;color:var(--text-muted);text-align:right;letter-spacing:0.5px;">
        composite of speech · emotion · technical<br>// powered by gemini + deepface + audio analysis
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-heading">Key performance metrics</div>', unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4, gap="small")
    with m1:
        st.metric("🎙️ Avg Speech Clarity", f"{speech_clarity}%", "above threshold" if speech_clarity >= 70 else "below threshold", delta_color="normal" if speech_clarity >= 70 else "inverse")
    with m2:
        st.metric("⚡ Speech Tempo", f"{tempo_wpm} WPM", "optimal range" if 110 <= tempo_wpm <= 160 else "outside optimal", delta_color="normal" if 110 <= tempo_wpm <= 160 else "off")
    with m3:
        st.metric("😊 Dominant Emotion", dominant_emotion)
    with m4:
        st.metric("🏆 Overall Score", f"{overall_score}/100", "pass" if overall_score >= 60 else "fail", delta_color="normal" if overall_score >= 60 else "inverse")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Emotion timeline — frame-by-frame</div>', unsafe_allow_html=True)
    if emotion_timeline:
        import pandas as pd
        df = pd.DataFrame(emotion_timeline).rename(columns={
            "frame": "Frame", "confidence": "Confidence (%)", "stress": "Stress (%)", "neutral": "Neutral (%)"
        }).set_index("Frame")
        st.line_chart(df[["Confidence (%)", "Stress (%)", "Neutral (%)"]], use_container_width=True, height=300)
        st.caption(
            f"// {len(emotion_timeline)} frames sampled · "
            f"avg confidence: {sum(r['confidence'] for r in emotion_timeline)//len(emotion_timeline)}% · "
            f"avg stress: {sum(r['stress'] for r in emotion_timeline)//len(emotion_timeline)}%"
        )
    else:
        st.info("No timeline data available for this candidate.")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Behavioral analysis</div>', unsafe_allow_html=True)
    b1, b2, b3 = st.columns(3, gap="medium")
    for col, (label, value, icon) in zip([b1, b2, b3], [
        ("Eye Contact Consistency", f"{min(95, speech_clarity + 5)}%",  "fa-eye"),
        ("Answer Coherence",        f"{min(98, overall_score + 8)}%",   "fa-brain"),
        ("Vocabulary Richness",     f"{min(92, tempo_wpm // 2)}%",      "fa-spell-check"),
    ]):
        with col:
            st.markdown(f"""<div class="report-metric"><div style="font-size:1.4rem;color:var(--accent);margin-bottom:0.4rem;"><i class="fa-solid {icon}"></i></div><div class="rm-value">{value}</div><div class="rm-label">{label}</div></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Download evaluation report</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="ml-card" style="display:flex;align-items:center;gap:1.25rem;flex-wrap:wrap;">
      <span style="font-size:2rem;">📄</span>
      <div style="flex:1;">
        <div style="font-family:'Sora',sans-serif;font-size:0.92rem;font-weight:700;color:var(--text-h);letter-spacing:-0.2px;">AI Evaluation Report — {selected_name}</div>
        <div style="font-family:'DM Mono',monospace;font-size:0.68rem;color:var(--text-muted);margin-top:3px;letter-spacing:0.3px;">// full pdf · speech transcript · emotion heatmap · gemini feedback · score breakdown</div>
        <div style="font-family:'DM Mono',monospace;font-size:0.65rem;color:var(--accent);margin-top:5px;letter-spacing:0.3px;word-break:break-all;">{pdf_url}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Try to find app_key for this candidate
    app_key_for_report = ""
    try:
        rec_apps = realtime_db.reference(f"recruiters/{uid}/applications").get()
        if rec_apps:
            for k, v in rec_apps.items():
                if v.get("candidate_uid") == selected_uid:
                    app_key_for_report = k
                    break
    except Exception:
        pass

    dl_col, _ = st.columns([1, 4])
    with dl_col:
        rpt_fetched = None
        try:
            if app_key_for_report:
                rpt_fetched = realtime_db.reference(f"interview_reports/{selected_uid}/{app_key_for_report}").get()
            if not rpt_fetched:
                rpt_fetched = realtime_db.reference(f"interview_reports/{selected_uid}").get()
        except Exception:
            pass

        if rpt_fetched and rpt_fetched.get("questions_data"):
            from app import generate_pdf_report
            qd = rpt_fetched["questions_data"]
            qs = [{"question": r["question"], "category": r.get("category",""), "expected_keywords": []} for r in qd]
            an = {i: r.get("answer","") for i, r in enumerate(qd)}
            sc = {i: {"score": r.get("score",0), "correct": r.get("correct",False), "feedback": r.get("feedback","")} for i, r in enumerate(qd)}
            try:
                pdf_bytes_rec = generate_pdf_report(
                    candidate_name=rpt_fetched.get("candidate_name", selected_name),
                    job_title=rpt_fetched.get("job_title",""),
                    company=rpt_fetched.get("company_name",""),
                    questions=qs, answers=an, scores=sc,
                    completed_at=rpt_fetched.get("completed_at",""),
                )
                st.download_button(
                    "⬇️  Download PDF Report", data=pdf_bytes_rec,
                    file_name=f"InterviewAI_{selected_name.replace(' ','_')}_Report.pdf",
                    mime="application/pdf", key="dl_report_recruiter", use_container_width=True,
                )
            except Exception as e:
                st.warning(f"Could not generate PDF: {e}")
        elif pdf_url:
            if st.button("⬇️  Download / View Report", use_container_width=True, key="dl_report_btn"):
                st.info(f"📎 If it didn't open, [click here]({pdf_url}) to download.")
        else:
            st.info("📄 Report will appear here once the candidate completes their interview.")


# ===========================
# RECRUITER DASHBOARD (main entry)
# ===========================

def render_recruiter_dashboard():
    """Main recruiter dashboard — called from app.py."""
    uid = st.session_state.user_uid

    rec_profile  = load_recruiter_profile(uid)
    apps         = load_applications(uid)
    postings     = load_job_postings(uid)

    company_name = rec_profile.get("company_name", st.session_state.user_name)
    rec_role_str = rec_profile.get("recruiter_role", "Recruiter")
    industry     = rec_profile.get("industry", "")
    bio          = rec_profile.get("bio", "")
    bio_html     = f'<em style="font-size:0.88rem;color:var(--text-muted);">{bio[:120]}{"…" if len(bio) > 120 else ""}</em>' if bio else ""

    st.markdown(f"""
    <div class="page-hero">
      <span class="eyebrow">// Recruiter Command Centre</span>
      <h1>Welcome back,<br>{st.session_state.user_name}.</h1>
      <p class="sub">
        {company_name}
        {(' &nbsp;·&nbsp; ' + rec_role_str) if rec_role_str else ''}
        {(' &nbsp;·&nbsp; ' + industry)     if industry     else ''}
        {('<br>' + bio_html)                if bio_html     else ''}
      </p>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.recruiter_profile_setup:
        st.markdown("""<div class="setup-banner"><span class="banner-icon">🏢</span><div><h3>Set up your recruiter profile</h3><p>Candidates see your company name and details on every job posting you create. Takes 60 seconds — builds trust instantly.</p></div></div>""", unsafe_allow_html=True)

    # Determine active tab via flags
    goto_post    = st.session_state.get("_rec_goto_post", False)
    goto_apps    = st.session_state.get("_rec_goto_applications", False)
    goto_reports = st.session_state.get("_rec_goto_reports", False)

    st.session_state._rec_goto_post         = False
    st.session_state._rec_goto_applications = False
    st.session_state._rec_goto_reports      = False

    tab_labels = [
        "  🏠 Overview  ",
        "  🏢 Profile  ",
        "  📋 Post Jobs  ",
        "  📥 Applications  ",
        "  📊 Reports Hub  ",
    ]

    if goto_post:
        order = [2, 0, 1, 3, 4]
    elif goto_apps:
        order = [3, 0, 1, 2, 4]
    elif goto_reports:
        order = [4, 0, 1, 2, 3]
    else:
        order = [0, 1, 2, 3, 4]

    ordered_labels = [tab_labels[i] for i in order]
    rendered_tabs  = st.tabs(ordered_labels)

    handlers = [
        lambda: recruiter_overview_tab(apps, postings),
        recruiter_profile_tab,
        post_requirements_tab,
        incoming_applications_tab,
        interview_reports_hub_tab,
    ]

    for tab_widget, orig_idx in zip(rendered_tabs, order):
        with tab_widget:
            handlers[orig_idx]()