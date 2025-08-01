import os, time, json, traceback, base64
from datetime import datetime, timezone
from tenacity import retry, wait_fixed, stop_after_attempt

def need(name: str) -> str:
    v = os.getenv(name)
    if not v:
        print(f"[FATAL] Missing env var: {name}", flush=True)
        raise SystemExit(1)
    return v

SUPABASE_URL = need("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = need("SUPABASE_SERVICE_ROLE")
POLL_SECS = float(os.getenv("JOB_POLL_SECONDS", "3"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()

print("=== Alpha Omega Worker v3 ===", flush=True)
print(f"SUPABASE_URL: {SUPABASE_URL}", flush=True)

try:
    from supabase import create_client
    from playwright.sync_api import sync_playwright
except Exception as e:
    print("[FATAL] Dependency import failed:", e, flush=True)
    raise SystemExit(1)

@retry(wait=wait_fixed(3), stop=stop_after_attempt(10))
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)

try:
    sb = get_client()
    print("[OK] Connected to Supabase", flush=True)
except Exception as e:
    print("[FATAL] Cannot connect to Supabase:", e, flush=True)
    raise SystemExit(1)

def log(msg):
    if LOG_LEVEL in ("debug","info"):
        print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)

def take_job():
    # Support both schemas: (type,payload) OR (kind,payload_json)
    try:
        res = sb.table("automation_jobs") \
            .select("*") \
            .in_("status", ["pending","queued"]) \
            .lte("scheduled_at", datetime.now(timezone.utc).isoformat()) \
            .order("created_at") \
            .limit(1) \
            .execute()
        data = res.data or []
        return data[0] if data else None
    except Exception as e:
        print("[WARN] take_job failed:", e, flush=True)
        return None

def update_job(job_id, **fields):
    try:
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        sb.table("automation_jobs").update(fields).eq("id", job_id).execute()
    except Exception as e:
        print("[WARN] update_job failed:", e, flush=True)

def handle_visit_url(url: str):
    # Use Playwright (already in image) to visit and read title
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=90000)
        title = page.title()
        final_url = page.url
        browser.close()
    return {"final_url": final_url, "title": title}

def run_job(job: dict):
    # Resolve fields (both schema variants)
    job_type = job.get("type") or job.get("kind")
    payload  = job.get("payload") or job.get("payload_json") or {}

    if not job_type:
        return {"error": "missing job type"}
    if not isinstance(payload, dict):
        # Supabase returns JSON as dict; if string, try parse
        try:
            payload = json.loads(payload)
        except Exception:
            return {"error": "payload not a dict"}

    if job_type == "visit_url":
        url = payload.get("url")
        if not url:
            return {"error": "visit_url requires payload.url"}
        try:
            return handle_visit_url(url)
        except Exception as e:
            return {"error": f"visit_url failed: {e}"}

    # Extend here: browse_search, fill_form, etc.
    return {"error": f"unknown job type '{job_type}'"}

def main():
    print(f"[OK] Polling every {POLL_SECS}s …", flush=True)
    idle_counter = 0
    while True:
        try:
            job = take_job()
            if not job:
                idle_counter += 1
                if idle_counter % int(max(1, 5/POLL_SECS)) == 0:  # log periodically
                    log("idle – no jobs")
                time.sleep(POLL_SECS)
                continue

            idle_counter = 0
            jid = job["id"]
            jtype = job.get("type") or job.get("kind")
            log(f"picked job {jid} type={jtype}")
            update_job(jid, status="running")

            result = run_job(job)
            if result.get("error"):
                update_job(jid, status="failed", attempts=(job.get("attempts") or 0) + 1, result=json.dumps(result))
                log(f"job {jid} failed: {result['error']}")
            else:
                update_job(jid, status="completed", result=json.dumps(result))
                log(f"job {jid} completed")
        except Exception as e:
            traceback.print_exc()
            time.sleep(POLL_SECS)

if __name__ == "__main__":
    main()
