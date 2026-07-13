# Morpheus Security Hardening Notes

## What Changed

### `morpheus-backend/supabase/migrations/20260713_security_rls.sql`
Adds a Supabase RLS migration for `dreams`, `dream_keywords`, `keywords`, and `knowledge_base`. User-owned rows are isolated by `auth.uid()`, shared keywords are only readable when linked to the user's own dreams, and `match_documents` runs as `security invoker` so RLS remains active.

### `morpheus-backend/app/database.py`
Removes the broad `supabase` admin alias and renames the service-role client to `supabase_admin_only`. Normal user data access now goes through `get_user_supabase(access_token)`, which sets the request JWT on the PostgREST client.

### `morpheus-backend/app/auth.py`
The auth dependency now returns an `AuthenticatedUser` object with the user's ID, email, access token, and user-scoped Supabase client. This makes authenticated routes use the same JWT that Supabase RLS evaluates.

### `morpheus-backend/app/routers/dreams.py`
Dream list, read, delete, insert, update, history, and RAG lookups now use the user-scoped client instead of the admin client. The only elevated path is `_admin_only_get_or_create_keyword_id`, which is limited to resolving the shared keyword dictionary and never exposes arbitrary keyword lists.

### `morpheus-backend/app/routers/graph.py`
Graph loading now passes the user-scoped client to graph construction. Client-facing graph failures return a generic message instead of provider or database internals.

### `morpheus-backend/app/services/graph_logic.py`
Graph queries now receive a scoped Supabase client from the route. The graph still has the same response shape and visualization inputs, but database reads are constrained by RLS.

### `morpheus-backend/app/services/ai_service.py`
RAG and user-history queries now accept the request-scoped Supabase client. PII redaction now includes a cloud-safe name pass before Gemini calls, so cloud mode is not limited to email, phone, date, and ID regex replacement.

### `morpheus-backend/app/security.py`
Adds a lightweight in-process rate limiter for dream processing endpoints and request-size middleware for text/audio payloads. This reduces accidental abuse, cost burn, and oversized request risk without changing the API response schema.

### `morpheus-backend/app/main.py`
Registers request-size middleware and generic exception handlers. Full errors are logged server-side, while clients receive safe generic messages.

### `morpheus-backend/app/config.py`
Adds configurable limits for dream text size, audio upload size, and dream-processing rate limits.

### `morpheus-backend/requirements.txt`
Adds `names-dataset` so cloud deployments can perform a lightweight name-redaction pass without loading spaCy.

### `morpheus-frontend/src/hooks/useAuth.js`
Removes manual writes to `localStorage.morpheus_session_token`. The app now relies on Supabase SDK session management and still exposes the active session through React state.

### `morpheus-frontend/src/lib/api.js`
Stops deleting the removed manual token mirror. API requests still get the current access token directly from `supabase.auth.getSession()`.

### `morpheus-frontend/src/pages/AuthPage.jsx`
Removes the manual token write after sign-in/sign-up. Navigation behavior and user-facing auth flow are unchanged.

### `.gitignore` and `.env.example`
Adds `.env.example` templates and ignores real `.env` files in both frontend and backend. The previously committed frontend `.env` was removed from the tracked project files.

## Verification Checklist

1. Run the backend compile check:
   ```bash
   PYTHONPYCACHEPREFIX=/private/tmp/morpheus-pycache morpheus-backend/.venv/bin/python3 -m compileall morpheus-backend/app
   ```

2. Run the frontend checks:
   ```bash
   cd morpheus-frontend
   npm run lint
   npm run build
   ```

3. In Supabase SQL Editor, run:
   ```sql
   select schemaname, tablename, rowsecurity
   from pg_tables
   where schemaname = 'public'
     and tablename in ('dreams', 'dream_keywords', 'keywords', 'knowledge_base');
   ```
   Confirm every `rowsecurity` value is `true`.

4. Use User A's valid JWT to call `GET /v1/dreams/{user_b_dream_id}`. Confirm the response is `404 Dream not found.` or another non-data response.

5. Use only the anon key, with no user JWT, to call the Supabase REST API for `dreams`, `dream_keywords`, `keywords`, and `knowledge_base`. Confirm no rows are returned.

6. Use User A's valid JWT to query Supabase REST for `dreams`. Confirm only User A's rows appear.

7. Use User A's valid JWT to query `keywords`. Confirm only symbols linked to User A's dreams appear.

8. Send a text payload larger than `MAX_DREAM_TEXT_CHARS` to `POST /v1/dreams/process-text`. Confirm the request is rejected and no dream row is created.
   Do not inline a 500k-character string directly inside the shell command, because that can kill the local terminal before the request reaches the server. Use a temporary file:
   ```bash
   python3 -c 'import json; print(json.dumps({"dream_text": "a" * 500000}))' > /tmp/morpheus-big-payload.json

   curl -i -X POST "https://YOUR_BACKEND_URL/v1/dreams/process-text" \
     -H "Authorization: Bearer USER_A_ACCESS_TOKEN" \
     -H "Content-Type: application/json" \
     --data-binary @/tmp/morpheus-big-payload.json
   ```
   Expect `413 Request Entity Too Large` when the body exceeds `MAX_TEXT_REQUEST_BYTES`, or `422 Invalid request payload` when the body is under the byte limit but exceeds `MAX_DREAM_TEXT_CHARS`.

9. Send an audio file larger than `MAX_AUDIO_UPLOAD_BYTES` to `POST /v1/dreams/process`. Confirm the request is rejected and no transcription/API cost is incurred.

10. Call `/v1/dreams/process-text` more than `PROCESS_RATE_LIMIT_REQUESTS` times inside `PROCESS_RATE_LIMIT_WINDOW_SECONDS`. Confirm the extra request returns `429`.
    For a cheap middleware-only test that does not call Gemini or create dreams, send an invalid but small body repeatedly and confirm the response eventually switches from `422` to `429`:
    ```bash
    for i in $(seq 1 20); do
      curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://YOUR_BACKEND_URL/v1/dreams/process-text" \
        -H "Authorization: Bearer USER_A_ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"dream_text": ""}'
    done
    ```
    For the full processing-path test, use a real `dream_text` value, but lower `PROCESS_RATE_LIMIT_REQUESTS` temporarily in a dev environment first so you do not spend unnecessary Gemini calls:
    ```bash
    for i in $(seq 1 5); do
      curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://YOUR_BACKEND_URL/v1/dreams/process-text" \
        -H "Authorization: Bearer USER_A_ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"dream_text": "I was walking through a quiet house and found a locked golden door."}'
    done
    ```

11. Temporarily trigger a backend failure, for example by using an invalid Gemini key in a non-production environment. Confirm the frontend receives a generic error and the detailed error appears only in Railway logs.

12. Search the built frontend bundle for backend-only secrets:
   ```bash
   rg "SUPABASE_SERVICE_ROLE_KEY|GEMINI_API_KEY|RESEND|morpheus_session_token" morpheus-frontend/dist
   ```
   Confirm no matches.

## Deployment Guide

1. Commit and push these code changes to GitHub.

2. In Supabase, open your project, then open **SQL Editor**.

3. Paste and run `morpheus-backend/supabase/migrations/20260713_security_rls.sql`.

4. In Supabase, open **Table Editor**, then check `dreams`, `dream_keywords`, `keywords`, and `knowledge_base`. Confirm RLS shows as enabled for each table.

5. In Supabase, open **Authentication > URL Configuration**. Set your production site URL to the Railway frontend URL, for example `https://morpheus-app.up.railway.app`.

6. In Supabase, add the allowed redirect URLs you use, including:
   - `https://morpheus-app.up.railway.app/auth`
   - `http://localhost:5173/auth` for local development, if you still test locally.

7. In Railway backend service, open **Variables** and set:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `GEMINI_API_KEY`
   - `GEMINI_MODEL`
   - `GEMINI_EMBEDDING_MODEL`
   - `USE_LOCAL_MODELS=false`
   - `ALLOWED_ORIGINS=https://morpheus-app.up.railway.app`
   - the `MAX_*` and `PROCESS_RATE_LIMIT_*` values from `morpheus-backend/.env.example`.

8. In Railway frontend service, open **Variables** and set:
   - `VITE_API_BASE_URL=https://morpheus11.up.railway.app`
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_ANON_KEY`

9. Redeploy backend first, then frontend.

10. Rotate secrets if they were ever pasted, screenshotted, committed, or shared:
    - Supabase service-role or secret key
    - Gemini API key
    - Resend API key or SMTP password
    - Any Railway variables copied into chat or screenshots

11. Enable MFA on Supabase, Railway, GitHub, and the email account used for these services. Code-level RLS does not protect data from a compromised dashboard/admin account.

12. Review Supabase Security Advisor and fix any remaining warnings about RLS, exposed schemas, leaked keys, or weak auth settings.

## Privacy Disclosure Draft

Morpheus stores dream content and related analysis data, including raw dream text, generated titles, psychological analysis, extracted symbols, emotions, and embeddings, on Morpheus infrastructure. This information is associated with your account and is used to provide journal history, analysis, and graph features.

Morpheus is not a zero-knowledge system. Authorized administrators may be able to access stored dream data when necessary for maintenance, debugging, security, abuse prevention, or legal compliance.

Dream text may be processed by third-party AI services, including Gemini, to generate transcription, symbol extraction, embeddings, and analysis. Morpheus applies automated redaction before AI processing, but users should avoid submitting highly sensitive personal information that they do not want processed by third-party providers.

## Reference Links

- Supabase Row Level Security: https://supabase.com/docs/guides/database/postgres/row-level-security
- Supabase API keys and service-role guidance: https://supabase.com/docs/guides/getting-started/api-keys
- Supabase custom SMTP guidance: https://supabase.com/docs/guides/auth/auth-smtp
