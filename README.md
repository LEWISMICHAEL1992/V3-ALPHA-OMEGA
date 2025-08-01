# Alpha Omega – Playwright Worker v3 (Railway, Dockerfile)

This worker polls Supabase for automation jobs and executes them with Playwright (Chromium).

**Supported jobs:**
- `browse_search` – Google search → return top links (title + URL)
- `fill_form` – open URL, fill selectors, optionally submit → return final URL (+ optional screenshot)

## Deploy in 3 steps

### 1) Upload to GitHub
- Create a repo (e.g., `alpha-omega-worker`) – private is fine.
- Upload these files **at the repo root**: `Dockerfile`, `requirements.txt`, `main.py`, `railway.toml`, `Procfile`, `.env.example`, `README.md`.

### 2) Deploy on Railway
- Railway → **New Project → Deploy from GitHub repo** → select your repo.
- After service is created, set Variables:
  - `SUPABASE_URL` = `https://<your-project>.supabase.co`
  - `SUPABASE_SERVICE_ROLE` = `<service-role-key from Supabase Settings → API>`
  - `JOB_POLL_SECONDS` = `3`
  - `LOG_LEVEL` = `info`
- Click **Deploy / Redeploy**. Logs should show:
  ```
  === Alpha Omega Worker v3 ===
  Connected to Supabase
  Polling for jobs...
  ```

### 3) Test
Supabase SQL:
```sql
-- replace with a real agent id from your 'agents' table
insert into automation_jobs (agent_id, kind, payload_json)
values ('PUT-AGENT-ID', 'browse_search', '{"query":"5 star hotels in London Mayfair","max_links":5}');
```
Then query:
```sql
select status, result_json
from automation_jobs
order by created_at desc
limit 1;
```

## Notes
- Keep secrets out of GitHub. Use Railway Variables only.
- If memory errors occur, increase service size in Railway Settings.
- This worker runs in the background; it does not expose an HTTP port.
