# SourceMind setup

SourceMind uses Groq for structured model calls, local MiniLM embeddings, and Supabase for accounts and durable evidence storage.

## Database

Use the existing SourceMind Supabase project or create your own. It must be active: a paused project cannot serve login or database requests. Free-project limits can prevent restoration until another project is paused or a paid plan is enabled.

Run the SQL files in `supabase/migrations/` in filename order in the Supabase SQL editor, or apply them through the Supabase CLI. They are repeatable and add to the old schema. `setup_database.sql` is the combined bootstrap copy. Review duplicate `(user_id, fingerprint)` records before upgrading an existing deployment; resolve them deliberately rather than deleting data during migration.

Every table enables RLS with `auth.uid()` ownership, explicit authenticated grants and write ownership checks. Composite foreign keys bind passages and chat messages to documents/conversations owned by the same user. The `ingest_document` RPC is a SECURITY INVOKER transaction; it stamps ownership from the JWT and never trusts a caller-supplied owner ID.

## App configuration

In Streamlit Cloud's App settings → General, select **Python 3.13**. This is the tested production runtime. The pinned embedding/numerical packages do not support Python 3.14; choosing 3.14 can prevent the app from building. Changing the runtime rebuilds the hosting environment.

Create an ignored `.env` locally or configure **Streamlit Cloud → App settings → Secrets**:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "YOUR_PUBLISHABLE_KEY"
GROQ_API_KEY = "YOUR_GROQ_KEY"
GROQ_MODEL = "llama-3.3-70b-versatile"
REDIRECT_URL = "https://adaptive-rag1.streamlit.app/"
ENABLE_GOOGLE_AUTH = "false"
```

Existing `SUPABASE_ANON_KEY` configurations remain supported. Use a publishable or legacy anon key, **never a service-role/secret key**. The default model is configurable if Groq changes availability. Keep secrets out of Git and logs.

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The public deterministic Evidence Lab works even before secrets are configured. Live document analysis requires Groq; authenticated document storage requires Supabase.

## Email signup and recovery

Keep email confirmation enabled. Set Supabase Auth → URL Configuration → Site URL to the deployed app and allow that exact URL in Redirect URLs (also `http://localhost:8501` for local development).

The app verifies a token hash server-side, which survives Streamlit opening a new browser connection. Configure the **Confirm signup** email link:

```html
<a href="{{ .SiteURL }}?token_hash={{ .TokenHash }}&type=email">Confirm your account</a>
```

Configure the **Reset password** email link:

```html
<a href="{{ .SiteURL }}?token_hash={{ .TokenHash }}&type=recovery">Choose a new password</a>
```

Choose a Site URL without a trailing slash for consistent links. Retain the rest of your email copy. Supabase's default email provider has delivery/rate restrictions; configure your own SMTP for a public app expecting multiple signups. See the official [email templates](https://supabase.com/docs/guides/auth/auth-email-templates) and [SMTP setup](https://supabase.com/docs/guides/auth/auth-smtp).

## Optional Google login

1. Enable Google in Supabase Auth → Providers and supply your Google OAuth client ID/secret.
2. In Google Cloud, allow Supabase's callback `https://YOUR_PROJECT.supabase.co/auth/v1/callback`.
3. In Supabase Redirect URLs, allow `https://adaptive-rag1.streamlit.app/**` so the opaque `oauth_state` query parameter is retained. Allow the matching localhost URL for local development. Do not allow arbitrary external domains.
4. Set `ENABLE_GOOGLE_AUTH = "true"` after verifying the provider.

The one-use PKCE verifier lives in a server-local SQLite store for 10 minutes, identified by a cryptographically random redirect nonce. A matching SameSite browser cookie binds the return to the browser that initiated it. A small bundled Streamlit component reads only this nonce, because Community Cloud filters custom cookies before the backend WebSocket request. It contains no access/refresh tokens. It survives Streamlit reconnecting after OAuth. A server restart invalidates pending attempts; start again. Multiple replicas need a shared state store.

Community Cloud remounts the app when callback query parameters change, including through its browser history wrapper. A successful callback therefore keeps its already-consumed one-use code until sign-out; reruns never exchange it again. No access or refresh token is included in the URL. Share the app's root URL rather than a callback URL. Reloading requires sign-in again.

## Existing documents

The upgrade preserves the original  metadata/history rows. The old app stored searchable PDF text in local Chroma, which may have disappeared when Streamlit redeployed. SourceMind displays these as legacy records with zero durable passages. Re-upload the original PDF to rebuild evidence, then remove the old metadata record if desired. Missing text cannot be reconstructed from an old summary.

## Verify your deployment

Sign in, upload two text PDFs, ask about a fact, inspect both the quote and the one-based page number. Run PDF disagreements and compare both source quotes. Sign out and use a second account to verify isolation. Reconnect and sign in again: documents and chat history should still be present.

Local password sessions do not use persistent browser cookies; a full browser reload requires signing in again. In-process reruns refresh expiring JWTs and save rotated refresh tokens.

The default Groq model is `llama-3.3-70b-versatile`. If Groq reports that model unavailable or denies that specific model, the adapter tries `openai/gpt-oss-20b` once through the same Groq account. Override `GROQ_MODEL` and `GROQ_FALLBACK_MODEL` to choose models; set an empty fallback to disable recovery. Authentication failures and rate limits never trigger a model switch. Logs retain only error classes and HTTP status codes, never provider bodies, keys or document content.
