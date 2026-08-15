# Price Intelligence V2

Live Saudi price tracker for Amazon.sa, Noon, Jarir, eXtra, Namshi and generic JSON-LD product pages.

## Architecture
- GitHub Pages: static dashboard
- Supabase/Postgres: persistent trackers + observations
- GitHub Actions: crawler runs 3× daily
- Python adapters: retailer selectors + JSON-LD/framework-state fallback
- Optional Serper API: shopping discovery
- Optional SMTP: deal alerts

## One-time setup
1. Create a Supabase project.
2. Run `supabase/schema.sql`.
3. Put the project URL + anon key in `config.js`.
4. Add repository secrets `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.
5. Optionally add `SERPER_API_KEY` and SMTP secrets.
6. Run **Live price checks** manually once.

## Security
The browser only receives the Supabase anon key. The service-role key exists only as a GitHub Actions secret. The included RLS is intentionally permissive for a personal MVP; add authentication and owner-scoped policies before multi-user/public rollout.

Retailer markup and anti-bot controls change. Amazon/Noon may intermittently reject GitHub-hosted runner IPs; a proxy or official product-data API may eventually be required.
