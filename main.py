import os, time, json, traceback, base64
from datetime import datetime
from tenacity import retry, wait_fixed, stop_after_attempt

def env_required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        print(f"[FATAL] Missing env var: {name}", flush=True)
        raise SystemExit(1)
    return v

SUPABASE_URL = env_required("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = env_required("SUPABASE_SERVICE_ROLE")
POLL = float(os.getenv("JOB_POLL_SECONDS", "3"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()

print("=== Alpha Omega Worker v3 ===", flush=True)
print(f"SUPABASE_URL: {SUPABASE_URL}", flush=True)

try:
    from supabase import create_client
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
except Exception as e:
    print("[FATAL] Dependency import failed:", e, flush=True)
    raise SystemExit(1)

@retry(wait=wait_fixed(3), stop=stop_after_attempt(10))
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)

try:
    supabase = get_client()
    print("Connected to Supabase", flush=True)
except Exception as e:
    print("[FATAL] Cannot connect to Supabase:", e, flush=True)
    raise SystemExit(1)

def log(msg):
    if LOG_LEVEL in ("debug","info"):
        print(f"[{datetime.utcnow().isoformat()}] {msg}", flush=True)

def take_job():
    try:
        res = supabase.table("automation_jobs").select("*").eq("status","queued").order("created_at").limit(1).execute()
        data = res.data or []
        return data[0] if data else None
    except Exception as e:
        print("[WARN] take_job failed:", e, flush=True)
        return None

def update_job(job_id, **fields):
    try:
        fields["updated_at"] = datetime.utcnow().isoformat() + "Z"
        supabase.table("automation_jobs").update(fields).eq("id", job_id).execute()
    except Exception as e:
        print("[WARN] update_job failed:", e, flush=True)

def do_browse_search(job):
    payload = job.get("payload_json") or {}
    query = payload.get("query") or ""
    max_links = int(payload.get("max_links") or 5)
    if not query:
        return {"error":"missing query"}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto("https://www.google.com", timeout=60000)
        page.fill("input[name=q]", query)
        page.keyboard.press("Enter")
        page.wait_for_selector("a h3", timeout=60000)
        links = []
        items = page.query_selector_all("a h3")
        for h3 in items[:max_links]:
            try:
                parent = h3.evaluate_handle("e => e.closest('a')")
                href = parent.evaluate("el => el.href")
                title = h3.inner_text().strip()
                if href and title:
                    links.append({"title": title, "url": href})
            except Exception:
                continue
        browser.close()
    return {"links": links}

def do_fill_form(job):
    payload = job.get("payload_json") or {}
    url = payload.get("url")
    fields = payload.get("fields", [])
    submit_sel = payload.get("submit_selector")
    take_shot = bool(payload.get("screenshot", False))
    if not url:
        return {"error":"missing url"}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(url, timeout=120000)
        for f in fields:
            sel = f.get("selector")
            val = f.get("value","")
            if not sel:
                continue
            page.wait_for_selector(sel, timeout=60000)
            page.fill(sel, val)
        if submit_sel:
            page.click(submit_sel)
            try:
                page.wait_for_load_state("networkidle", timeout=120000)
            except PWTimeoutError:
                pass
        out = {"final_url": page.url}
        if take_shot:
            path = f"screenshot_{job['id']}.png"
            page.screenshot(path=path, full_page=True)
            with open(path, "rb") as fh:
                out["screenshot_b64"] = base64.b64encode(fh.read()).decode()
        browser.close()
    return out

HANDLERS = {
    "browse_search": do_browse_search,
    "fill_form": do_fill_form,
}

def main():
    print("Polling for jobs...", flush=True)
    while True:
        try:
            job = take_job()
            if not job:
                time.sleep(POLL); continue
            log(f"Picked job {job['id']} kind={job.get('kind')}")
            update_job(job["id"], status="running")
            kind = job.get("kind")
            handler = HANDLERS.get(kind)
            if not handler:
                update_job(job["id"], status="failed", result_json={"error": f"Unknown kind {kind}"})
                continue
            result = handler(job)
            if isinstance(result, dict) and result.get("error"):
                update_job(job["id"], status="failed", result_json=result)
            else:
                update_job(job["id"], status="done", result_json=result)
            log(f"Finished job {job['id']}")
        except Exception as e:
            traceback.print_exc()
            try:
                if 'job' in locals() and job:
                    update_job(job["id"], status="failed", result_json={"error": str(e)})
            except Exception:
                pass
            time.sleep(POLL)

if __name__ == "__main__":
    main()
