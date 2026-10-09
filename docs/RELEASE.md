# Release runbook

## Before release

Run Python tests and `node tests/check_database.mjs`. Confirm the actual Supabase project is healthy, and check for duplicate document fingerprints and mismatched message/conversation ownership before applying the additive migration.

The migration adds durable passages, evidence reports, ownership FKs and explicit authenticated policies. It does not drop existing documents, users or conversations. An old source whose Chroma text is gone remains visible as a metadata-only record requiring re-upload.

## Deploy

Apply `supabase/migrations/*_evidence_storage.sql` once through Supabase migration tooling or the dashboard SQL editor. Use a publishable/legacy anon key, never service-role. Configure the exact deployed URL and email templates described in README_SETUP.md. Google remains opt-in until its provider and redirect allowlist are ready.

Deploy the tested commit to the Streamlit app's configured branch. For a local run, use `python -m streamlit run app.py`. No documents or secrets belong in the Git repository.

Verify: sign-up/confirmation, sign-in, upload a small text PDF, ask a question, inspect page citations, upload a contradictory PDF, run the scan, sign out, sign in as another account and confirm the library is private. Refresh and confirm saved documents and conversations remain.

## Rollback

Revert the application commit if startup, sign-in or persistent writes fail. Keep the additive schema changes; the old app ignores added columns/tables and its authenticated queries remain compatible. Do not delete the new passage table to roll back code. Existing PDF evidence remains in the database.

Watch Streamlit startup logs and Supabase Auth/Data API errors after rollout. Authentication failures, cross-user exposure, or lost writes are immediate rollback triggers. Provider rate limits should display a retriable failure/abstention rather than an invented answer.
