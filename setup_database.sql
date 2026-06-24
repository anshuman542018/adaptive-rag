-- SourceMind — Supabase Database Setup
-- Run this in Supabase → SQL Editor → New Query

-- ─────────────────────────────────────────────
-- TABLE 1: User Profiles
-- Extends Supabase's built-in auth.users
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_profiles (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email       TEXT,
    name        TEXT,
    avatar_url  TEXT,
    last_login  TIMESTAMPTZ DEFAULT NOW(),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- TABLE 2: Conversations  ← NEW (was missing)
-- Each user's named chat sessions
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id         UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id    UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL DEFAULT 'New Chat',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- TABLE 3: Documents
-- Each user's ingested documents
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    chunks      INTEGER DEFAULT 0,
    summary     TEXT,
    fingerprint TEXT,
    source_type TEXT DEFAULT 'unknown',    -- 'pdf' or 'url'
    added_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- TABLE 4: Chat Messages
-- Full chat history per user, linked to a conversation
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_messages (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,              -- 'user' or 'assistant'
    content         TEXT NOT NULL,
    sources         JSONB DEFAULT '[]',         -- list of source objects
    confidence      FLOAT DEFAULT 0.0,
    conflicts       JSONB DEFAULT '[]',         -- list of conflict objects
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- TABLE 5: Conflicts
-- Cross-document contradictions per user
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conflicts (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    source_a    TEXT,
    source_b    TEXT,
    topic       TEXT,
    claim_a     TEXT,
    claim_b     TEXT,
    severity    TEXT DEFAULT 'medium',     -- 'high', 'medium', 'low'
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- ROW LEVEL SECURITY
-- Every user sees ONLY their own data
-- ─────────────────────────────────────────────
ALTER TABLE user_profiles  ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents      ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages  ENABLE ROW LEVEL SECURITY;
ALTER TABLE conflicts      ENABLE ROW LEVEL SECURITY;

-- user_profiles policies
CREATE POLICY "Users manage own profile"
    ON user_profiles FOR ALL
    USING (auth.uid() = id);

-- conversations policies
CREATE POLICY "Users manage own conversations"
    ON conversations FOR ALL
    USING (auth.uid() = user_id);

-- documents policies
CREATE POLICY "Users manage own documents"
    ON documents FOR ALL
    USING (auth.uid() = user_id);

-- chat_messages policies
CREATE POLICY "Users manage own messages"
    ON chat_messages FOR ALL
    USING (auth.uid() = user_id);

-- conflicts policies
CREATE POLICY "Users manage own conflicts"
    ON conflicts FOR ALL
    USING (auth.uid() = user_id);

-- ─────────────────────────────────────────────
-- INDEXES (speeds up queries)
-- ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_conversations_user   ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_upd    ON conversations(updated_at);
CREATE INDEX IF NOT EXISTS idx_documents_user       ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_user        ON chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_conv        ON chat_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conflicts_user       ON conflicts(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created     ON chat_messages(created_at);

-- Done! Your database is ready.
