import os, time, sys
from tenacity import retry, wait_fixed, stop_after_attempt
from supabase import create_client

def required(name):
    v = os.getenv(name)
    if not v:
        print(f"[FATAL] Missing env var: {name}", flush=True)
        sys.exit(1)
    return v

SUPABASE_URL = required("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = required("SUPABASE_SERVICE_ROLE")
POLL = int(os.getenv("JOB_POLL_SECONDS", "2"))

print("=== Alpha Omega Worker v2 ===", flush=True)
print("Connecting to Supabase...", flush=True)

@retry(wait=wait_fixed(3), stop=stop_after_attempt(5))
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)

sb = get_client()
print("✅ Connected to Supabase", flush=True)

while True:
    try:
        res = sb.table("automation_jobs").select("id, status").limit(1).execute()
        print(f"Heartbeat OK - jobs found: {len(res.data)}", flush=True)
    except Exception as e:
        print("[WARN] Heartbeat query failed:", e, flush=True)
    time.sleep(POLL)
