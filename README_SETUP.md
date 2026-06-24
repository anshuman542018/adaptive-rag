# SourceMind — Setup Guide

## What You Need (all free)
- Groq API key (already have this)
- Supabase account (free) → supabase.com
- GitHub account (for deployment)

---

## Step 1 — Create Supabase Project

1. Go to **supabase.com** → New Project
2. Name it `sourcemind`, choose a region close to you
3. Set a database password (save it somewhere)
4. Wait ~2 minutes for project to spin up

---

## Step 2 — Set Up the Database

1. In Supabase dashboard → **SQL Editor** → New Query
2. Copy the entire contents of `setup_database.sql`
3. Paste it and click **Run**
4. You should see "Success" — all 4 tables are created

---

## Step 3 — Enable Google OAuth

1. In Supabase → **Authentication** → **Providers**
2. Find **Google** → toggle it ON
3. You need a Google OAuth Client ID and Secret:
   - Go to **console.cloud.google.com**
   - New Project → APIs & Services → Credentials
   - Create OAuth 2.0 Client ID → Web Application
   - Authorized redirect URIs: add your Supabase callback URL
     Format: `https://YOUR_PROJECT_REF.supabase.co/auth/v1/callback`
   - Copy the Client ID and Client Secret
4. Back in Supabase → paste Client ID and Secret → Save

---

## Step 4 — Get Your Supabase Keys

In Supabase → **Settings** → **API**:
- Copy **Project URL** → this is SUPABASE_URL
- Copy **anon public** key → this is SUPABASE_ANON_KEY

---

## Step 5 — Update Your .env File

```
GROQ_API_KEY=gsk_your_key_here
SUPABASE_URL=https://your_project_ref.supabase.co
SUPABASE_ANON_KEY=eyJhbGc...your_anon_key
REDIRECT_URL=http://localhost:8501
```

---

## Step 6 — Install New Dependency

```bash
pip install supabase
```

---

## Step 7 — Run Locally

```bash
streamlit run app.py
```

Open http://localhost:8501 — you should see the login page.
Click "Sign in with Google" → authenticate → you're in!

---

## Step 8 — Deploy to Streamlit Cloud

1. Push to GitHub:
```bash
git add . && git commit -m "SourceMind with Google Auth" && git push
```

2. Go to **share.streamlit.io** → New app → your repo → app.py

3. In **Advanced → Secrets**, add:
```toml
GROQ_API_KEY = "gsk_your_key"
SUPABASE_URL = "https://your_project.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGc..."
REDIRECT_URL = "https://your-app-name.streamlit.app"
```

4. Also add the Streamlit Cloud URL to:
   - Supabase → Authentication → URL Configuration → Site URL
   - Supabase → Authentication → URL Configuration → Redirect URLs

5. Also add to Google Cloud Console → OAuth → Authorized redirect URIs:
   `https://your_project_ref.supabase.co/auth/v1/callback`

---

## What Each User Gets

After login, each user has:
- Their own private knowledge base (separate ChromaDB collection)
- Their own document list (stored in Supabase)
- Their own chat history (persists across sessions)
- Their own conflict detection results
- Data isolated from all other users (Row Level Security)

---

## Database Schema Summary

| Table          | What it stores                    |
|----------------|-----------------------------------|
| user_profiles  | name, email, avatar, last login   |
| documents      | source name, chunks, summary, fp  |
| chat_messages  | role, content, sources, confidence|
| conflicts      | topic, claims, severity, sources  |

---

## Interview Talking Points

"I added Google OAuth via Supabase so each user has a private knowledge base.
Every table has Row Level Security — users can only access their own data.
Chat history persists across sessions in PostgreSQL.
ChromaDB collections are namespaced by user ID so knowledge bases don't mix.
The whole auth flow is stateless — OAuth code exchange on redirect, session in st.session_state."
