# ===========================================================
# ONE-TIME BACKFILL SCRIPT
# Fixes existing job_postings / applications that were saved
# with a blank company_name / industry because the recruiter
# posted a job before completing their profile.
#
# Run this ONCE, locally, from your project root:
#   python backfill_missing_job_data.py
#
# It needs ServiceAccountKey.json in the same folder (or update
# the path below) and your Realtime Database URL.
# ===========================================================

import firebase_admin
from firebase_admin import credentials, db

# ---- 1. CONFIG: update these two lines ----
SERVICE_ACCOUNT_PATH = "ServiceAccountKey.json"
DATABASE_URL = "https://aiemotioninterviewer-default-rtdb.firebaseio.com" 

cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})


def backfill():
    recruiters_ref = db.reference("recruiters")
    recruiters = recruiters_ref.get() or {}

    fixed_postings = 0
    fixed_candidate_apps = 0
    fixed_recruiter_apps = 0

    for rec_uid, rec_data in recruiters.items():
        company_name = (rec_data.get("company_name") or "").strip()
        industry = (rec_data.get("industry") or "").strip()

        if not company_name:
            print(f"⚠️  Recruiter {rec_uid} still has no company_name in their profile — skipping their postings.")
            continue

        # --- Fix job_postings under this recruiter ---
        postings = rec_data.get("job_postings", {}) or {}
        for job_key, job in postings.items():
            updates = {}
            if not (job.get("company_name") or "").strip():
                updates["company_name"] = company_name
            if not (job.get("industry") or "").strip():
                updates["industry"] = industry
            if updates:
                db.reference(f"recruiters/{rec_uid}/job_postings/{job_key}").update(updates)
                fixed_postings += 1
                print(f"✅ Fixed job posting {job_key} -> company_name='{company_name}'")

        # --- Fix this recruiter's own copy of applications (job_title only lives here, no company_name field currently) ---
        rec_apps = rec_data.get("applications", {}) or {}
        for app_key, app in rec_apps.items():
            # recruiter-side application records don't store company_name today,
            # nothing to backfill here unless you add that field later.
            pass

    # --- Fix candidate-side application records (this is what the candidate dashboard reads) ---
    candidates_ref = db.reference("candidates")
    candidates = candidates_ref.get() or {}

    for cand_uid, cand_data in candidates.items():
        apps = cand_data.get("applications", {}) or {}
        for app_key, app in apps.items():
            if (app.get("company_name") or "").strip() and (app.get("job_title") or "").strip():
                continue  # already fine

            rec_uid = app.get("recruiter_uid", "")
            job_id = app.get("job_id", "")
            if not rec_uid or not job_id:
                print(f"⚠️  Candidate {cand_uid} app {app_key} has no recruiter_uid/job_id — cannot auto-fix, consider deleting it.")
                continue

            job = db.reference(f"recruiters/{rec_uid}/job_postings/{job_id}").get()
            if not job:
                print(f"⚠️  Candidate {cand_uid} app {app_key} points to a job posting that no longer exists — safe to delete.")
                continue

            updates = {}
            if not (app.get("company_name") or "").strip() and job.get("company_name"):
                updates["company_name"] = job.get("company_name")
            if not (app.get("job_title") or "").strip() and job.get("job_title"):
                updates["job_title"] = job.get("job_title")

            if updates:
                db.reference(f"candidates/{cand_uid}/applications/{app_key}").update(updates)
                fixed_candidate_apps += 1
                print(f"✅ Fixed candidate {cand_uid} application {app_key} -> {updates}")

    print("\n--- Summary ---")
    print(f"Job postings fixed:        {fixed_postings}")
    print(f"Candidate applications fixed: {fixed_candidate_apps}")


def link_and_sync_existing_applications():
    """
    Fixes applications that were already broken by the old key-mismatch bug:
    - Recruiter's copy of an application has the true status (Applied/Interview
      Scheduled/Rejected/etc) and was never corrupted.
    - Candidate's real copy (the one with job_title/company_name) may still say
      "Applied" because the old Accept/Reject code updated the wrong Firebase key.
    - That wrong update instead created a "ghost" record under the candidate with
      the SAME key as the recruiter's own application key, containing only
      {status, last_status_change} and no job data -> this is exactly the
      "Incomplete application record" you saw on the dashboard.

    This function:
      1. Matches each recruiter application to its real candidate application
         using candidate_uid + applied_at (both were written from the same
         timestamp at submission time, so this match is exact).
      2. Saves that link as "candidate_app_key" on the recruiter record (so the
         app never has to guess again).
      3. Copies the correct/current status from the recruiter record onto the
         real candidate record.
      4. Deletes the ghost record (same key as the recruiter's own push key)
         if it exists and has no job_title/job_id.
    """
    linked = 0
    status_synced = 0
    ghosts_removed = 0

    recruiters = db.reference("recruiters").get() or {}

    for rec_uid, rec_data in recruiters.items():
        rec_apps = rec_data.get("applications", {}) or {}

        for rec_key, rec_app in rec_apps.items():
            if rec_app.get("candidate_app_key"):
                continue  # already linked (new-code applications)

            cand_uid = rec_app.get("candidate_uid", "")
            applied_at = rec_app.get("applied_at", "")
            if not cand_uid or not applied_at:
                print(f"⚠️  Recruiter {rec_uid} app {rec_key} missing candidate_uid/applied_at — skipping.")
                continue

            cand_apps = db.reference(f"candidates/{cand_uid}/applications").get() or {}

            real_key = None
            for ck, ca in cand_apps.items():
                if ca.get("applied_at") == applied_at and (ca.get("job_title") or "").strip():
                    real_key = ck
                    break

            if not real_key:
                print(f"⚠️  Could not find matching candidate record for recruiter app {rec_key} "
                      f"(candidate {cand_uid}, applied_at {applied_at}). Leaving as-is.")
                continue

            # 1. Save the link so this never has to be guessed again
            db.reference(f"recruiters/{rec_uid}/applications/{rec_key}").update({"candidate_app_key": real_key})
            linked += 1

            # 2. Sync status from recruiter's (uncorrupted) record onto the real candidate record
            real_record = cand_apps.get(real_key, {})
            if (real_record.get("status") != rec_app.get("status") or
                    real_record.get("last_status_change") != rec_app.get("last_status_change")):
                update_fields = {
                    "status": rec_app.get("status", real_record.get("status", "Applied")),
                    "last_status_change": rec_app.get("last_status_change", ""),
                }
                if rec_app.get("interview_deadline"):
                    update_fields["interview_deadline"] = rec_app["interview_deadline"]
                db.reference(f"candidates/{cand_uid}/applications/{real_key}").update(update_fields)
                status_synced += 1
                print(f"✅ Synced status '{update_fields['status']}' onto candidate {cand_uid} app {real_key}")

            # 3. Clean up the ghost record (candidate app whose key == recruiter's own push key)
            ghost = cand_apps.get(rec_key)
            if ghost and rec_key != real_key and not (ghost.get("job_title") or "").strip():
                db.reference(f"candidates/{cand_uid}/applications/{rec_key}").delete()
                ghosts_removed += 1
                print(f"🗑️  Removed ghost record candidates/{cand_uid}/applications/{rec_key}")

    print("\n--- Link & Sync Summary ---")
    print(f"Recruiter records linked to candidate records: {linked}")
    print(f"Candidate statuses corrected:                  {status_synced}")
    print(f"Ghost records removed:                         {ghosts_removed}")


if __name__ == "__main__":
    backfill()
    print()
    link_and_sync_existing_applications()
