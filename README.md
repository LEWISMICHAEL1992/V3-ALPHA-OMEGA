# Alpha Omega Worker v2

This worker polls Supabase for queued automation jobs and processes them
(e.g., web browsing, form filling) via Playwright.

## Deployment
1. Upload these files to a GitHub repository (root folder).
2. Deploy the repo to Railway (New Project -> Deploy from GitHub).
3. Add Environment Variables:
   - SUPABASE_URL
   - SUPABASE_SERVICE_ROLE
   - OPENAI_API_KEY
   - JOB_POLL_SECONDS=2
   - LOG_LEVEL=info
4. View logs to confirm: "✅ Connected to Supabase"
