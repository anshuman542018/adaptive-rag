"""
SourceMind — Production Adaptive RAG
Final error-proof version
Fixes: Google OAuth, JWT auth, negative confidence, RLS writes
"""

import streamlit as st
import chromadb
import os, json, hashlib, tempfile, re
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from urllib.parse import urlparse
from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import bs4, requests

load_dotenv()

# ─────────────────────────────────────────────
# PAGE CONFIG  (must be FIRST st call)
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="SourceMind",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Sora:wght@300;400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Sora', sans-serif; }
.stApp { background: #0a0a0f; color: #e8e6f0; }
div[data-testid="stSidebar"] { background: #0d0d14; border-right: 1px solid #1f1f2e; }

.login-wrap {
    max-width: 420px; margin: 60px auto;
    background: #13131a; border: 1px solid #1f1f2e;
    border-radius: 20px; padding: 44px 40px; text-align: center;
}
.login-logo  { font-size: 2.8rem; margin-bottom: 10px; }
.login-title { font-size: 1.8rem; font-weight: 700; color: #e8e6f0; margin-bottom: 6px; }
.login-sub   { color: #6b7280; font-size: 0.85rem; margin-bottom: 28px; line-height: 1.6; }
.or-divider  {
    display: flex; align-items: center; gap: 12px;
    color: #374151; font-size: 0.8rem; margin: 18px 0;
}
.or-divider::before, .or-divider::after {
    content: ''; flex: 1; height: 1px; background: #1f1f2e;
}
.user-name  { font-weight: 600; color: #e8e6f0; font-size: 0.88rem; }
.user-email { color: #6b7280; font-size: 0.72rem; }
.conv-group-label {
    font-size: 0.7rem; color: #4b5563; text-transform: uppercase;
    letter-spacing: 1px; padding: 10px 4px 4px;
}
.big-title {
    font-size: 2.2rem; font-weight: 700; letter-spacing: -1px;
    background: linear-gradient(135deg, #a78bfa, #60a5fa, #34d399);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.subtitle { color: #4b5563; font-size: 0.85rem; margin-bottom: 1.5rem; }
.chat-user {
    background: #1a1a2e; border-radius: 14px 14px 4px 14px;
    padding: 12px 16px; margin: 10px 0; color: #e8e6f0; max-width: 85%;
}
.chat-ai {
    background: #13131a; border: 1px solid #1f1f2e;
    border-radius: 14px 14px 14px 4px;
    padding: 12px 16px; margin: 10px 0; color: #e8e6f0;
}
.chat-meta { margin-top: 10px; padding-top: 8px; border-top: 1px solid #1f1f2e; }
.source-chip {
    display: inline-block; background: #1a1a2e; border: 1px solid #312e81;
    color: #a78bfa; padding: 2px 10px; border-radius: 20px;
    font-size: 0.72rem; font-family: 'DM Mono', monospace; margin: 2px;
}
.conflict-card {
    background: #1a0f00; border-left: 4px solid #f59e0b;
    border-radius: 8px; padding: 14px; margin: 8px 0;
}
.conflict-title { color: #fbbf24; font-weight: 600; font-size: 0.82rem; margin-bottom: 8px; }
.conflict-side {
    background: #0f0f1a; border-radius: 6px; padding: 8px;
    font-size: 0.78rem; color: #d1d5db; margin: 4px 0;
    font-family: 'DM Mono', monospace;
}
.conf-wrap { background: #1f1f2e; border-radius: 4px; height: 5px; margin: 4px 0 10px; }
.conf-bar  { height: 5px; border-radius: 4px; }
.metric-card {
    background: #13131a; border: 1px solid #1f1f2e;
    border-radius: 10px; padding: 14px; text-align: center;
}
.metric-num   { font-size: 1.8rem; font-weight: 700; color: #a78bfa; }
.metric-label { font-size: 0.7rem; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; }
.gap-item {
    background: #0f1a0f; border-left: 4px solid #22c55e;
    border-radius: 8px; padding: 10px 14px; margin: 6px 0;
    font-size: 0.83rem; color: #86efac;
}
.doc-pill {
    background: #13131a; border: 1px solid #1f1f2e; border-radius: 8px;
    padding: 7px 12px; margin: 3px 0; font-size: 0.8rem;
    display: flex; justify-content: space-between; align-items: center;
}
.doc-pill-name { color: #a78bfa; font-family: 'DM Mono', monospace; }
.doc-pill-meta { color: #6b7280; font-size: 0.72rem; }
.stButton > button {
    background: linear-gradient(135deg, #7c3aed, #2563eb);
    color: white; border: none; border-radius: 8px;
    font-family: 'Sora', sans-serif; font-weight: 600; width: 100%;
}
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background: #13131a; border: 1px solid #1f1f2e;
    color: #e8e6f0; border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
def _secret(key: str, default: str = "") -> str:
    try:    return st.secrets[key]
    except: return os.environ.get(key, default)

SUPABASE_URL = _secret("SUPABASE_URL")
SUPABASE_KEY = _secret("SUPABASE_ANON_KEY")
GROQ_KEY     = _secret("GROQ_API_KEY")
REDIRECT_URL = _secret("REDIRECT_URL", "http://localhost:8501")
PERSIST_DIR  = "./sourcemind_db"


# ─────────────────────────────────────────────
# CACHED RESOURCES
# ─────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    """Returns a plain Supabase client (no JWT). Use get_authed_supabase() for writes."""
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_authed_supabase():
    """
    Returns Supabase client with the current user's JWT attached.
    Required for all INSERT/UPDATE/DELETE calls — RLS checks auth.uid().
    Without the JWT, auth.uid() returns NULL and every write is blocked.
    """
    sb    = get_supabase()
    token = st.session_state.get("access_token", "")
    refresh_token = st.session_state.get("refresh_token", "")
    if sb and token:
        try:
            sb.auth.set_session(token, refresh_token)
        except Exception:
            pass   # token expired or invalid — reads still work, writes may fail
    return sb


@st.cache_resource
def get_llm():
    return ChatGroq(model="llama-3.1-8b-instant", temperature=0, api_key=GROQ_KEY)


@st.cache_resource
def get_embeddings():
    return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")


@st.cache_resource
def get_chroma_client():
    Path(PERSIST_DIR).mkdir(exist_ok=True)
    return chromadb.PersistentClient(path=PERSIST_DIR)


def get_vectorstore(user_id: str) -> Chroma:
    """Each user gets their own ChromaDB collection."""
    safe = user_id.replace("-", "")[:16]
    return Chroma(
        client=get_chroma_client(),
        collection_name=f"kb_{safe}",
        embedding_function=get_embeddings()
    )


# ─────────────────────────────────────────────
# AUTH — GOOGLE OAUTH
# ─────────────────────────────────────────────
def get_oauth_url() -> str:
    """Build the Google OAuth redirect URL via Supabase."""
    sb = get_supabase()
    if not sb:
        return ""
    if st.session_state.get("oauth_url"):
        return st.session_state["oauth_url"]
    try:
        res = sb.auth.sign_in_with_oauth({
            "provider": "google",
            "options":  {"redirect_to": REDIRECT_URL, "scopes": "openid email profile"}
        })
        st.session_state["oauth_url"] = res.url
        verifier = _get_oauth_code_verifier(sb)
        if verifier:
            st.session_state["oauth_code_verifier"] = verifier
        return res.url
    except Exception as e:
        st.error(f"OAuth setup error: {e}")
        return ""


def _get_oauth_code_verifier(sb) -> str:
    """Read Supabase's PKCE verifier before another rerun can replace it."""
    verifier = st.session_state.get("oauth_code_verifier", "")
    if verifier:
        return verifier
    try:
        auth = sb.auth
        storage = getattr(auth, "_storage", None)
        storage_key = getattr(auth, "_storage_key", "supabase.auth.token")
        if storage:
            return storage.get_item(f"{storage_key}-code-verifier") or ""
    except Exception:
        pass
    return ""


def _clear_oauth_attempt(sb=None):
    for key in ["oauth_url", "oauth_code_verifier"]:
        st.session_state.pop(key, None)
    try:
        sb = sb or get_supabase()
        auth = sb.auth
        storage = getattr(auth, "_storage", None)
        storage_key = getattr(auth, "_storage_key", "supabase.auth.token")
        if storage:
            storage.remove_item(f"{storage_key}-code-verifier")
    except Exception:
        pass


def _query_param_value(params, key: str) -> str:
    value = params.get(key, "")
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def handle_oauth_callback():
    """
    Called on every page load.
    If Supabase redirected back with ?code=..., exchange it for a session.
    Clears the query param after success so it doesn't loop.
    """
    params = st.query_params
    if "code" not in params or "user" in st.session_state:
        return

    sb = get_supabase()
    if not sb:
        return

    try:
        code_verifier = _get_oauth_code_verifier(sb)
        if not code_verifier:
            raise RuntimeError("OAuth session expired. Please click the Google button again.")

        session = sb.auth.exchange_code_for_session({
            "auth_code": _query_param_value(params, "code"),
            "code_verifier": code_verifier,
            "redirect_to": REDIRECT_URL,
        })
        u       = session.user

        if not u or not session.session:
            raise RuntimeError("Supabase did not return a user session.")

        st.session_state["user"] = {
            "id":     u.id,
            "email":  u.email,
            "name":   u.user_metadata.get("full_name", u.email.split("@")[0]),
            "avatar": u.user_metadata.get("avatar_url", ""),
        }
        # CRITICAL: store tokens so get_authed_supabase() can attach/refresh them
        st.session_state["access_token"] = session.session.access_token
        st.session_state["refresh_token"] = session.session.refresh_token

        _upsert_profile(
            get_authed_supabase(), u.id, u.email,
            u.user_metadata.get("full_name", ""),
            u.user_metadata.get("avatar_url", "")
        )
        _clear_oauth_attempt(sb)
        st.query_params.clear()
        st.rerun()

    except Exception as e:
        _clear_oauth_attempt(sb)
        st.error(f"Google login failed: {e}")
        st.query_params.clear()


# ─────────────────────────────────────────────
# AUTH — EMAIL
# ─────────────────────────────────────────────
def email_signup(email: str, password: str, name: str) -> str | None:
    """
    Register then immediately sign in.
    Returns None on success, error string on failure, "CONFIRM_EMAIL" sentinel
    when Supabase requires email verification before login.
    """
    sb = get_supabase()
    if not sb:
        return "Supabase not configured."
    try:
        sb.auth.sign_up({
            "email":    email,
            "password": password,
            "options":  {"data": {"full_name": name}}
        })
    except Exception as e:
        err = str(e)
        if "already registered" not in err and "already been registered" not in err:
            return err
        # user already exists — fall through to sign-in

    # Attempt immediate sign-in (works when email confirmation is disabled)
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
        u   = res.user
        st.session_state["user"] = {
            "id":     u.id,
            "email":  u.email,
            "name":   u.user_metadata.get("full_name", name or email.split("@")[0]),
            "avatar": u.user_metadata.get("avatar_url", ""),
        }
        # CRITICAL: store JWT so RLS writes work
        st.session_state["access_token"] = res.session.access_token
        st.session_state["refresh_token"] = res.session.refresh_token
        _upsert_profile(get_authed_supabase(), u.id, email,
                        u.user_metadata.get("full_name", name), "")
        return None

    except Exception as e:
        err = str(e)
        if "Email not confirmed" in err:
            return "CONFIRM_EMAIL"
        if "Invalid login" in err:
            return "Account created — please sign in manually."
        return err


def email_signin(email: str, password: str) -> str | None:
    """Returns None on success, error string on failure."""
    sb = get_supabase()
    if not sb:
        return "Supabase not configured."
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
        u   = res.user
        st.session_state["user"] = {
            "id":     u.id,
            "email":  u.email,
            "name":   u.user_metadata.get("full_name", u.email.split("@")[0]),
            "avatar": u.user_metadata.get("avatar_url", ""),
        }
        # CRITICAL: store JWT so RLS writes work
        st.session_state["access_token"] = res.session.access_token
        st.session_state["refresh_token"] = res.session.refresh_token
        _upsert_profile(get_authed_supabase(), u.id, u.email,
                        u.user_metadata.get("full_name", ""),
                        u.user_metadata.get("avatar_url", ""))
        return None

    except Exception as e:
        msg = str(e)
        if "Invalid login" in msg:       return "Wrong email or password."
        if "Email not confirmed" in msg: return "Please verify your email first."
        return msg


def send_password_reset(email: str) -> str:
    sb = get_supabase()
    if not sb:
        return "Supabase not configured."
    try:
        sb.auth.reset_password_email(email, options={"redirect_to": REDIRECT_URL})
        return "ok"
    except Exception as e:
        return str(e)


def _upsert_profile(sb, uid: str, email: str, name: str, avatar: str):
    if not sb:
        return
    try:
        sb.table("user_profiles").upsert({
            "id":         uid,
            "email":      email,
            "name":       name,
            "avatar_url": avatar,
            "last_login": datetime.now().isoformat()
        }).execute()
    except Exception:
        pass   # non-critical — profile upsert failing shouldn't block login


def sign_out():
    sb = get_authed_supabase()
    if sb:
        try:
            sb.auth.sign_out()
        except Exception:
            pass
    _clear_oauth_attempt(sb)
    for k in ["user", "access_token", "refresh_token", "current_conv_id", "chat_history"]:
        st.session_state.pop(k, None)
    st.rerun()


def get_current_user() -> dict | None:
    return st.session_state.get("user")


# ─────────────────────────────────────────────
# DATABASE — CONVERSATIONS
# ─────────────────────────────────────────────
def db_create_conversation(user_id: str, title: str = "New Chat") -> str | None:
    sb = get_authed_supabase()
    if not sb:
        return None
    try:
        res = sb.table("conversations").insert({
            "user_id": user_id,
            "title":   title[:80],
        }).execute()
        return res.data[0]["id"] if res.data else None
    except Exception:
        return None


def db_get_conversations(user_id: str) -> list:
    sb = get_authed_supabase()
    if not sb:
        return []
    try:
        res = (sb.table("conversations")
                 .select("id,title,created_at,updated_at")
                 .eq("user_id", user_id)
                 .order("updated_at", desc=True)
                 .limit(60)
                 .execute())
        return res.data or []
    except Exception:
        return []


def db_update_conv_title(conv_id: str, title: str):
    sb = get_authed_supabase()
    if not sb:
        return
    try:
        sb.table("conversations").update({
            "title":      title[:80],
            "updated_at": datetime.now().isoformat()
        }).eq("id", conv_id).execute()
    except Exception:
        pass


def db_touch_conversation(conv_id: str):
    sb = get_authed_supabase()
    if not sb:
        return
    try:
        sb.table("conversations").update(
            {"updated_at": datetime.now().isoformat()}
        ).eq("id", conv_id).execute()
    except Exception:
        pass


def db_delete_conversation(conv_id: str):
    sb = get_authed_supabase()
    if not sb:
        return
    try:
        sb.table("chat_messages").delete().eq("conversation_id", conv_id).execute()
        sb.table("conversations").delete().eq("id", conv_id).execute()
    except Exception:
        pass


def db_get_conv_messages(conv_id: str) -> list:
    sb = get_authed_supabase()
    if not sb:
        return []
    try:
        res = (sb.table("chat_messages")
                 .select("*")
                 .eq("conversation_id", conv_id)
                 .order("created_at")
                 .execute())

        def _safe_list(val) -> list:
            """Handle JSONB (already a list) or legacy string-encoded JSON."""
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return []
            return []

        return [
            {
                "role":       r["role"],
                "content":    r["content"],
                "sources":    _safe_list(r.get("sources")),
                "confidence": r.get("confidence", 0),
                "conflicts":  _safe_list(r.get("conflicts")),
            }
            for r in (res.data or [])
        ]
    except Exception:
        return []


def db_save_message(user_id: str, conv_id: str, msg: dict):
    sb = get_authed_supabase()
    if not sb:
        return
    try:
        sb.table("chat_messages").insert({
            "user_id":         user_id,
            "conversation_id": conv_id,
            "role":            msg["role"],
            "content":         msg["content"],
            "sources":         msg.get("sources", []),    # Supabase handles JSONB natively
            "confidence":      msg.get("confidence", 0.0),
            "conflicts":       msg.get("conflicts", []),
        }).execute()
    except Exception:
        pass


# ─────────────────────────────────────────────
# DATABASE — DOCUMENTS + CONFLICTS
# ─────────────────────────────────────────────
def db_get_documents(user_id: str) -> list:
    sb = get_authed_supabase()
    if not sb:
        return []
    try:
        res = (sb.table("documents")
                 .select("*")
                 .eq("user_id", user_id)
                 .order("added_at", desc=True)
                 .execute())
        return res.data or []
    except Exception:
        return []


def db_save_document(user_id: str, info: dict):
    sb = get_authed_supabase()
    if not sb:
        return
    try:
        sb.table("documents").insert({
            "user_id":     user_id,
            "name":        info["name"],
            "chunks":      info["chunks"],
            "summary":     info.get("summary", ""),
            "fingerprint": info["fingerprint"],
            "source_type": info.get("source_type", "unknown"),
        }).execute()
    except Exception as e:
        st.warning(f"DB save warning: {e}")


def db_get_fingerprints(user_id: str) -> list:
    return [d.get("fingerprint", "") for d in db_get_documents(user_id)]


def db_save_conflict(user_id: str, c: dict):
    sb = get_authed_supabase()
    if not sb:
        return
    try:
        sb.table("conflicts").insert({
            "user_id":  user_id,
            "source_a": c["source_a"][:200],
            "source_b": c["source_b"][:200],
            "topic":    c["topic"][:200],
            "claim_a":  c["claim_a"][:500],
            "claim_b":  c["claim_b"][:500],
            "severity": c["severity"],
        }).execute()
    except Exception:
        pass


def db_get_conflicts(user_id: str) -> list:
    sb = get_authed_supabase()
    if not sb:
        return []
    try:
        res = (sb.table("conflicts")
                 .select("*")
                 .eq("user_id", user_id)
                 .order("detected_at", desc=True)
                 .execute())
        return res.data or []
    except Exception:
        return []


def db_clear_user_data(user_id: str):
    sb = get_authed_supabase()
    if not sb:
        return
    for table in ["documents", "conflicts", "chat_messages", "conversations"]:
        try:
            sb.table(table).delete().eq("user_id", user_id).execute()
        except Exception:
            pass
    try:
        safe = user_id.replace("-", "")[:16]
        get_chroma_client().delete_collection(f"kb_{safe}")
    except Exception:
        pass


# ─────────────────────────────────────────────
# DOCUMENT LOADERS
# ─────────────────────────────────────────────
def fingerprint(text: str) -> str:
    return hashlib.md5(text[:500].encode()).hexdigest()


def load_pdf(uploaded_file) -> List[Document]:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name
    try:
        docs = PyPDFLoader(tmp_path).load()
        for d in docs:
            d.metadata["source_name"] = uploaded_file.name
            d.metadata["source_type"] = "pdf"
        return docs
    finally:
        os.unlink(tmp_path)


def load_url(url: str) -> List[Document]:
    os.environ["USER_AGENT"] = "SourceMind/1.0"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Accept":     "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    }
    SELECTORS = [
        "article", "main", "#mw-content-text", ".article-body",
        ".post-content", ".entry-content", '[role="main"]', "#content", "body"
    ]
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = bs4.BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
            tag.decompose()
        text = ""
        for sel in SELECTORS:
            el = soup.select_one(sel)
            if el:
                cand = " ".join(el.get_text(separator=" ").split())
                if len(cand) > 300:
                    text = cand
                    break
        if not text:
            st.error(f"Could not extract content from {url}")
            return []
        title_tag = soup.find("title")
        title     = title_tag.get_text().strip() if title_tag else url
        return [Document(
            page_content=text,
            metadata={"source_name": url, "title": title, "source_type": "url"}
        )]
    except requests.exceptions.Timeout:
        st.error(f"Timeout loading {url}")
        return []
    except requests.exceptions.HTTPError as e:
        st.error(f"HTTP {e.response.status_code} from {url}")
        return []
    except Exception as e:
        st.error(f"URL load failed: {e}")
        return []


def chunk_documents(docs: List[Document]) -> List[Document]:
    return RecursiveCharacterTextSplitter(
        chunk_size=500, chunk_overlap=100,
        separators=["\n\n", "\n", ". ", " ", ""]
    ).split_documents(docs)


# ─────────────────────────────────────────────
# CONFLICT DETECTION
# ─────────────────────────────────────────────
def _extract_json(raw: str) -> dict | None:
    """
    Robust JSON extractor.
    Strips markdown fences, finds the first {...} block, parses it.
    """
    clean = re.sub(r"```(?:json)?", "", raw).strip().strip("`")
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def detect_conflict(pa: str, pb: str, sa: str, sb_src: str, llm) -> dict | None:
    """
    Ask the LLM if two passages from DIFFERENT sources contradict each other.
    Returns a conflict dict on detection, None otherwise.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a strict JSON-only fact-checker.\n"
         "A contradiction = two sources making mutually exclusive claims about the same fact "
         "(different numbers, opposite conclusions, conflicting dates/names).\n\n"
         "Respond ONLY with raw JSON — no markdown, no explanation:\n"
         '{"conflict": true, "topic": "...", "claim_a": "...", "claim_b": "...", '
         '"severity": "high|medium|low"}\n'
         'or {"conflict": false}'),
        ("human",
         f"Source A ({sa[:60]}):\n{pa[:500]}\n\n"
         f"Source B ({sb_src[:60]}):\n{pb[:500]}\n\n"
         "Do these passages contradict each other on any factual claim?")
    ])
    try:
        raw = (prompt | llm | StrOutputParser()).invoke({})
        res = _extract_json(raw)
        if res and res.get("conflict"):
            return {
                "source_a":  sa,
                "source_b":  sb_src,
                "passage_a": pa[:300],
                "passage_b": pb[:300],
                "topic":     res.get("topic", "Unknown"),
                "claim_a":   res.get("claim_a", pa[:100]),
                "claim_b":   res.get("claim_b", pb[:100]),
                "severity":  res.get("severity", "medium"),
            }
    except Exception:
        pass
    return None


def run_conflict_check(
    new_chunks: List[Document], vs: Chroma,
    user_id: str, llm, pbar
) -> list:
    """
    Compare new chunks against existing KB chunks from OTHER sources.

    Distance metric: ChromaDB default L2 (Euclidean) on unit-normalised MiniLM vectors.
    Effective range: 0 (identical) → ~2 (maximally different).
    Conflict sweet spot: 0.1 < dist < 1.4
      - dist < 0.1 = near duplicate (same source repeated)
      - dist > 1.4 = completely different topic (can't logically conflict)
    """
    if not db_get_documents(user_id):
        return []   # no existing documents → nothing to conflict with

    new_conflicts: list = []
    seen_pairs:    set  = set()
    step = max(1, len(new_chunks) // 8)   # sample ≈ 8 representative chunks

    for i, chunk in enumerate(new_chunks):
        if i % step != 0:
            continue
        pbar.progress(
            0.5 + 0.4 * (i / len(new_chunks)),
            text=f"Conflict check {i + 1}/{len(new_chunks)}"
        )
        chunk_src = chunk.metadata.get("source_name", "Unknown")
        try:
            for sim_doc, dist in vs.similarity_search_with_score(chunk.page_content, k=5):
                sim_src = sim_doc.metadata.get("source_name", "Unknown")
                if sim_src == chunk_src:
                    continue                      # skip same-source pairs
                if dist < 0.1 or dist > 1.4:
                    continue                      # too similar or too different

                # Deduplicate pairs we've already checked this ingest run
                pair_key = tuple(sorted([
                    chunk.page_content[:100],
                    sim_doc.page_content[:100]
                ]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                c = detect_conflict(
                    chunk.page_content, sim_doc.page_content,
                    chunk_src, sim_src, llm
                )
                if c:
                    new_conflicts.append(c)
                    db_save_conflict(user_id, c)
        except Exception:
            continue
    return new_conflicts


# ─────────────────────────────────────────────
# INGEST PIPELINE
# ─────────────────────────────────────────────
def generate_summary(text: str, source: str, llm) -> str:
    try:
        return (ChatPromptTemplate.from_template(
            "Write a 2-sentence summary starting 'This document covers...'\n\n"
            "Excerpt:\n{text}\n\nSource: {source}"
        ) | llm | StrOutputParser()).invoke({"text": text[:2000], "source": source})
    except Exception:
        return "Summary unavailable."


def ingest_documents(
    docs: List[Document],
    source_name: str,
    source_type: str,
    user_id: str
) -> dict:
    llm    = get_llm()
    vs     = get_vectorstore(user_id)
    pb     = st.progress(0, text="Chunking...")
    chunks = chunk_documents(docs)
    pb.progress(0.2, text=f"{len(chunks)} chunks created")

    fp = fingerprint(docs[0].page_content if docs else "")
    if fp in db_get_fingerprints(user_id):
        pb.empty()
        return {"status": "duplicate", "source": source_name}

    pb.progress(0.4, text="Embedding and indexing...")
    vs.add_documents(chunks)

    pb.progress(0.5, text="Checking for contradictions...")
    new_conflicts = run_conflict_check(chunks, vs, user_id, llm, pb)

    pb.progress(0.92, text="Generating summary...")
    summary = generate_summary(docs[0].page_content[:2000], source_name, llm)

    db_save_document(user_id, {
        "name":        source_name,
        "chunks":      len(chunks),
        "summary":     summary,
        "fingerprint": fp,
        "source_type": source_type,
    })

    pb.progress(1.0, text="Done!")
    pb.empty()
    return {
        "status":    "success",
        "source":    source_name,
        "chunks":    len(chunks),
        "conflicts": new_conflicts,
        "summary":   summary,
    }


# ─────────────────────────────────────────────
# ANSWER WITH ATTRIBUTION
# ─────────────────────────────────────────────
def _dist_to_similarity(dist: float) -> float:
    """
    Convert L2 distance to a stable similarity score in (0, 1].
    Formula: 1 / (1 + dist)
    - dist=0.0  → similarity=1.00  (identical)
    - dist=1.0  → similarity=0.50  (moderately related)
    - dist=2.0  → similarity=0.33  (very different)
    Never goes negative unlike (1 - dist).
    """
    return round(1.0 / (1.0 + dist), 3)


def answer_with_attribution(question: str, user_id: str) -> dict:
    llm = get_llm()
    vs  = get_vectorstore(user_id)

    try:
        results = vs.similarity_search_with_score(question, k=5)
    except Exception:
        return {
            "answer":    "Knowledge base is empty. Add documents first.",
            "sources":   [],
            "confidence": 0.0,
            "conflicts": [],
        }
    if not results:
        return {
            "answer":    "No relevant documents found.",
            "sources":   [],
            "confidence": 0.0,
            "conflicts": [],
        }

    context_parts: list = []
    sources_used:  list = []
    source_map:    dict = {}
    sc = 1

    for doc, dist in results[:4]:
        src  = doc.metadata.get("source_name", "Unknown")
        page = doc.metadata.get("page", "")

        if src not in source_map:
            source_map[src] = sc
            sc += 1
        sid = source_map[src]

        if src.startswith("http"):
            p        = urlparse(src)
            readable = p.netloc.replace("www.", "") + p.path[:30]
        else:
            readable = Path(src).stem[:40]

        page_tag = f" p.{page + 1}" if page not in ["", None] else ""
        label    = f"[Source {sid}: {readable}{page_tag}]"
        context_parts.append(f"{label}\n{doc.page_content}")
        sources_used.append({
            "label":      f"Source {sid}",
            "name":       src,
            "page":       page,
            "similarity": _dist_to_similarity(dist),   # FIXED: never negative
            "excerpt":    doc.page_content[:120],
        })

    context    = "\n\n".join(context_parts)
    # Confidence = average similarity of top-3 retrieved chunks
    confidence = round(
        sum(_dist_to_similarity(d) for _, d in results[:3]) / min(3, len(results)),
        2
    )

    answer = (ChatPromptTemplate.from_template(
        "Answer using ONLY the sources below. "
        "Cite each fact with (Source 1), (Source 2), etc.\n"
        "If the information is not in any source, say 'Not found in knowledge base.'\n\n"
        "Sources:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    ) | llm | StrOutputParser()).invoke({"context": context, "question": question})

    # Surface any stored conflicts relevant to this answer
    all_conflicts = db_get_conflicts(user_id)
    rel_conflicts = [
        c for c in all_conflicts
        if c.get("topic", "").lower() in (question + answer).lower()
    ]

    return {
        "answer":     answer,
        "sources":    sources_used,
        "confidence": confidence,
        "conflicts":  rel_conflicts[:2],
    }


def auto_title(question: str) -> str:
    q = question.strip()
    return (q[:55] + "…") if len(q) > 55 else q


# ─────────────────────────────────────────────
# KNOWLEDGE GAP DETECTOR
# ─────────────────────────────────────────────
def detect_knowledge_gaps(user_id: str, custom: list | None = None) -> list:
    """
    Auto-generates probe questions from document summaries,
    then checks which ones the KB answers poorly.
    Gap threshold: similarity < 0.55 using 1/(1+dist) formula.
    """
    llm       = get_llm()
    vs        = get_vectorstore(user_id)
    docs      = db_get_documents(user_id)
    probes    = list(custom or [])
    summaries = " ".join(d.get("summary", "") for d in docs)

    if summaries:
        try:
            raw = (ChatPromptTemplate.from_template(
                "You are an analyst. Generate 5 specific, varied questions that test the "
                "total coverage of these topics. Return ONLY a valid JSON array of plain "
                "strings — no dicts, no markdown.\n"
                'Example: ["What is X?", "How does Y work?"]\n\n'
                "Topics: {s}"
            ) | llm | StrOutputParser()).invoke({"s": summaries[:1500]})

            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                for item in parsed:
                    if isinstance(item, dict):
                        q_text = (item.get("question")
                                  or item.get("q")
                                  or str(next(iter(item.values()), "")))
                    else:
                        q_text = str(item)
                    probes.append(q_text.strip())
        except Exception:
            pass

    gaps = []
    for q in probes[:8]:
        q = str(q).strip()
        if not q:
            continue
        try:
            r = vs.similarity_search_with_score(q, k=1)
        except Exception:
            continue
        if not r:
            gaps.append({"question": q, "reason": "No documents in knowledge base"})
            continue
        sim = _dist_to_similarity(r[0][1])
        if sim < 0.55:
            gaps.append({
                "question":   q,
                "similarity": sim,
                "reason":     f"Poor coverage (similarity: {sim:.2f} < 0.55)",
            })
    return gaps


# ─────────────────────────────────────────────
# LOGIN PAGE
# ─────────────────────────────────────────────
def show_login_page():
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("""
        <div class='login-wrap'>
            <div class='login-logo'>🧠</div>
            <div class='login-title'>SourceMind</div>
            <div class='login-sub'>
                Adaptive RAG · Conflict Detection<br>
                Source Attribution · Knowledge Gaps
            </div>
        </div>
        """, unsafe_allow_html=True)

        tab_in, tab_up, tab_reset = st.tabs(["Sign In", "Sign Up", "Reset Password"])
        oauth_url = get_oauth_url()

        # ── Sign In ──────────────────────────────
        with tab_in:
            if oauth_url:
                st.link_button("🔑  Continue with Google",
                               url=oauth_url, use_container_width=True)
                st.markdown("<div class='or-divider'>or</div>", unsafe_allow_html=True)

            email_in = st.text_input("Email", key="si_email",
                                     placeholder="you@example.com")
            pass_in  = st.text_input("Password", type="password", key="si_pass",
                                     placeholder="Your password")
            if st.button("Sign In", key="btn_signin", use_container_width=True):
                if not email_in or not pass_in:
                    st.error("Enter email and password.")
                else:
                    with st.spinner("Signing in..."):
                        err = email_signin(email_in.strip(), pass_in)
                    if err:
                        st.error(err)
                    else:
                        st.rerun()

        # ── Sign Up ──────────────────────────────
        with tab_up:
            if oauth_url:
                st.link_button("🔑  Sign up with Google",
                               url=oauth_url, use_container_width=True)
                st.markdown("<div class='or-divider'>or</div>", unsafe_allow_html=True)

            name_up  = st.text_input("Full Name", key="su_name",
                                     placeholder="Anshuman Pandey")
            email_up = st.text_input("Email", key="su_email",
                                     placeholder="you@example.com")
            pass_up  = st.text_input("Password (min 6 chars)",
                                     type="password", key="su_pass")
            pass_up2 = st.text_input("Confirm Password",
                                     type="password", key="su_pass2")

            if st.button("Create Account", key="btn_signup", use_container_width=True):
                if not name_up or not email_up or not pass_up:
                    st.error("All fields are required.")
                elif pass_up != pass_up2:
                    st.error("Passwords don't match.")
                elif len(pass_up) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    with st.spinner("Creating account..."):
                        err = email_signup(email_up.strip(), pass_up, name_up.strip())
                    if err == "CONFIRM_EMAIL":
                        st.info(
                            "📧 Account created! Check your email for a verification link, "
                            "then come back and **Sign In**.\n\n"
                            "Tip: to skip verification, go to Supabase → Authentication → "
                            "Settings → disable **Enable email confirmations**."
                        )
                    elif err:
                        st.error(err)
                    else:
                        st.rerun()

        # ── Reset Password ────────────────────────
        with tab_reset:
            st.markdown(
                "<p style='color:#6b7280;font-size:0.83rem;'>"
                "We'll send a password reset link to your email.</p>",
                unsafe_allow_html=True
            )
            reset_email = st.text_input("Email", key="reset_email",
                                        placeholder="you@example.com")
            if st.button("Send Reset Link", key="btn_reset", use_container_width=True):
                if not reset_email:
                    st.error("Enter your email.")
                else:
                    with st.spinner("Sending..."):
                        result = send_password_reset(reset_email.strip())
                    if result == "ok":
                        st.success("Reset link sent! Check your inbox.")
                    else:
                        st.error(result)


# ─────────────────────────────────────────────
# CONVERSATION SIDEBAR
# ─────────────────────────────────────────────
def _group_conversations(convs: list) -> dict:
    now   = datetime.now(timezone.utc)
    today = now.date()
    groups: dict = {"Today": [], "Yesterday": [], "This Week": [], "Older": []}
    for c in convs:
        raw = c.get("updated_at") or c.get("created_at", "")
        try:
            dt   = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            diff = (today - dt.date()).days
            if diff == 0:   groups["Today"].append(c)
            elif diff == 1: groups["Yesterday"].append(c)
            elif diff <= 7: groups["This Week"].append(c)
            else:           groups["Older"].append(c)
        except Exception:
            groups["Older"].append(c)
    return groups


def render_conversation_sidebar(user_id: str, convs: list):
    current = st.session_state.get("current_conv_id")

    if st.button("＋  New Chat", use_container_width=True, key="new_chat_btn"):
        st.session_state.pop("current_conv_id", None)
        st.session_state.pop("chat_history", None)
        st.rerun()

    if not convs:
        st.markdown(
            "<p style='color:#4b5563;font-size:0.8rem;padding:8px 4px;'>"
            "No conversations yet.</p>",
            unsafe_allow_html=True
        )
        return

    for group_name, items in _group_conversations(convs).items():
        if not items:
            continue
        st.markdown(
            f"<div class='conv-group-label'>{group_name}</div>",
            unsafe_allow_html=True
        )
        for conv in items:
            cid   = conv["id"]
            title = conv.get("title", "New Chat")
            col_title, col_del = st.columns([5, 1])
            with col_title:
                label = f"▶ {title}" if cid == current else title
                if st.button(label, key=f"conv_{cid}",
                             use_container_width=True, help=title):
                    st.session_state["current_conv_id"] = cid
                    st.session_state["chat_history"]    = db_get_conv_messages(cid)
                    st.rerun()
            with col_del:
                if st.button("🗑", key=f"del_{cid}", help="Delete this chat"):
                    db_delete_conversation(cid)
                    if st.session_state.get("current_conv_id") == cid:
                        st.session_state.pop("current_conv_id", None)
                        st.session_state.pop("chat_history", None)
                    st.rerun()


# ─────────────────────────────────────────────
# CHAT RENDERER
# ─────────────────────────────────────────────
def render_chat(user_id: str, docs_list: list):
    if not docs_list:
        st.info("👈 Add documents from the **Knowledge Base** tab to get started.")
        return

    if "chat_history" not in st.session_state:
        conv_id = st.session_state.get("current_conv_id")
        st.session_state["chat_history"] = (
            db_get_conv_messages(conv_id) if conv_id else []
        )

    conv_id = st.session_state.get("current_conv_id")
    if conv_id:
        convs = db_get_conversations(user_id)
        curr  = next((c for c in convs if c["id"] == conv_id), None)
        if curr:
            st.markdown(
                f"<p style='color:#6b7280;font-size:0.8rem;margin-bottom:8px;'>"
                f"💬 {curr['title']}</p>",
                unsafe_allow_html=True
            )

    for msg in st.session_state["chat_history"]:
        if msg["role"] == "user":
            st.markdown(
                f"<div class='chat-user'>"
                f"<strong style='color:#a78bfa'>You</strong><br>{msg['content']}"
                f"</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"<div class='chat-ai'>"
                f"<strong style='color:#34d399'>SourceMind</strong><br>{msg['content']}",
                unsafe_allow_html=True
            )
            if msg.get("sources"):
                st.markdown(
                    "<div class='chat-meta'>"
                    "<small style='color:#6b7280'>Sources used:</small><br>",
                    unsafe_allow_html=True
                )
                seen: set = set()
                for s in msg["sources"]:
                    raw = s.get("name", "")
                    if raw.startswith("http"):
                        p       = urlparse(raw)
                        display = p.netloc.replace("www.", "") + p.path[:35]
                    else:
                        display = Path(raw).stem[:50]
                    page = (f" · p.{s['page'] + 1}"
                            if s.get("page") not in ["", None] else "")
                    chip = f"{display}{page}"
                    if chip in seen:
                        continue
                    seen.add(chip)
                    sim = s.get("similarity", 0)
                    st.markdown(
                        f"<span class='source-chip'>📄 {chip} · {sim:.0%}</span>",
                        unsafe_allow_html=True
                    )
                st.markdown("</div>", unsafe_allow_html=True)

            conf  = msg.get("confidence", 0)
            color = ("#22c55e" if conf > 0.6 else
                     "#f59e0b" if conf > 0.35 else "#ef4444")
            st.markdown(
                f"<small style='color:#6b7280'>Confidence: {conf:.0%}</small>"
                f"<div class='conf-wrap'><div class='conf-bar' "
                f"style='width:{conf * 100:.0f}%;background:{color};'></div></div>",
                unsafe_allow_html=True
            )
            for c in (msg.get("conflicts") or []):
                st.markdown(
                    f"<div class='conflict-card'>"
                    f"<div class='conflict-title'>⚠️ Conflict on: {c.get('topic', '')}</div>"
                    f"<div class='conflict-side'>📄 {c.get('source_a', '')[:30]}: "
                    f"{c.get('claim_a', '')[:120]}</div>"
                    f"<div class='conflict-side'>📄 {c.get('source_b', '')[:30]}: "
                    f"{c.get('claim_b', '')[:120]}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            st.markdown("</div>", unsafe_allow_html=True)

    with st.form("chat_form", clear_on_submit=True):
        c1, c2 = st.columns([5, 1])
        with c1:
            question = st.text_input(
                "Ask", placeholder="What does the document say about...",
                label_visibility="collapsed"
            )
        with c2:
            submit = st.form_submit_button("Ask →")

    if submit and question.strip():
        if not st.session_state.get("current_conv_id"):
            new_id = db_create_conversation(user_id, auto_title(question))
            st.session_state["current_conv_id"] = new_id
            conv_id = new_id
        else:
            conv_id = st.session_state["current_conv_id"]
            db_touch_conversation(conv_id)

        user_msg = {"role": "user", "content": question,
                    "sources": [], "confidence": 0, "conflicts": []}
        st.session_state["chat_history"].append(user_msg)
        db_save_message(user_id, conv_id, user_msg)

        with st.spinner("Thinking..."):
            result = answer_with_attribution(question, user_id)

        ai_msg = {
            "role":       "assistant",
            "content":    result["answer"],
            "sources":    result["sources"],
            "confidence": result["confidence"],
            "conflicts":  result["conflicts"],
        }
        st.session_state["chat_history"].append(ai_msg)
        db_save_message(user_id, conv_id, ai_msg)

        if len(st.session_state["chat_history"]) == 2:
            db_update_conv_title(conv_id, auto_title(question))

        st.rerun()

    if st.session_state.get("chat_history"):
        if st.button("🗑 Clear this chat"):
            cid = st.session_state.get("current_conv_id")
            if cid:
                db_delete_conversation(cid)
            st.session_state.pop("current_conv_id", None)
            st.session_state.pop("chat_history", None)
            st.rerun()


# ─────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────
def show_main_app(user: dict):
    user_id = user["id"]

    with st.sidebar:
        if user.get("avatar"):
            col_av, col_info = st.columns([1, 3])
            with col_av:
                st.image(user["avatar"], width=36)
            with col_info:
                st.markdown(
                    f"<div class='user-name'>{user['name']}</div>"
                    f"<div class='user-email'>{user['email']}</div>",
                    unsafe_allow_html=True
                )
        else:
            st.markdown(
                f"<div class='user-name'>👤 {user['name']}</div>"
                f"<div class='user-email'>{user['email']}</div>",
                unsafe_allow_html=True
            )

        if st.button("Sign out", key="signout_btn", use_container_width=True):
            sign_out()

        st.divider()
        st.markdown("### 💬 Chats")
        convs = db_get_conversations(user_id)
        render_conversation_sidebar(user_id, convs)

        st.divider()
        docs_list = db_get_documents(user_id)
        conflicts  = db_get_conflicts(user_id)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                f"<div class='metric-card'>"
                f"<div class='metric-num'>{len(docs_list)}</div>"
                f"<div class='metric-label'>Sources</div></div>",
                unsafe_allow_html=True
            )
        with c2:
            st.markdown(
                f"<div class='metric-card'>"
                f"<div class='metric-num'>{len(conflicts)}</div>"
                f"<div class='metric-label'>Conflicts</div></div>",
                unsafe_allow_html=True
            )

    st.markdown("<div class='big-title'>SourceMind</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='subtitle'>"
        "Adaptive RAG · Conflict Detection · Source Attribution · Knowledge Gaps"
        "</div>",
        unsafe_allow_html=True
    )

    tab_chat, tab_kb, tab_src, tab_conf, tab_gaps = st.tabs([
        "💬 Chat", "📚 Knowledge Base", "🗂️ Sources", "⚠️ Conflicts", "🗺️ Gaps"
    ])

    # ── Chat ────────────────────────────────────────
    with tab_chat:
        docs_list = db_get_documents(user_id)
        render_chat(user_id, docs_list)

    # ── Knowledge Base ───────────────────────────────
    with tab_kb:
        st.markdown("### 📚 Knowledge Base")
        col_pdf, col_url = st.columns(2)
        with col_pdf:
            st.markdown("**Upload PDFs**")
            uploaded = st.file_uploader(
                "PDFs", type=["pdf"], accept_multiple_files=True,
                label_visibility="collapsed", key="kb_pdf_upload"
            )
        with col_url:
            st.markdown("**Add URLs** (one per line)")
            url_box = st.text_area(
                "URLs", placeholder="https://example.com/article",
                height=120, label_visibility="collapsed", key="kb_url_input"
            )

        if st.button("⚡ Ingest Documents", use_container_width=True, key="kb_ingest"):
            all_docs: list = []
            sources:  list = []
            for f in (uploaded or []):
                with st.spinner(f"Loading {f.name}..."):
                    pdocs = load_pdf(f)
                    if pdocs:
                        all_docs.extend(pdocs)
                        sources.append(("pdf", f.name))
            for url in [u.strip() for u in url_box.strip().splitlines() if u.strip()]:
                with st.spinner(f"Fetching {url[:50]}..."):
                    udocs = load_url(url)
                    if udocs:
                        all_docs.extend(udocs)
                        sources.append(("url", url))
                        st.toast(f"✓ {url[:40]}")
            if all_docs:
                stype  = sources[0][0] if sources else "unknown"
                label  = ", ".join(s[1][:40] for s in sources[:2])
                result = ingest_documents(all_docs, label, stype, user_id)
                if result["status"] == "duplicate":
                    st.warning("⚠️ Already in knowledge base.")
                else:
                    st.success(f"✅ {result['chunks']} chunks indexed")
                    if result["conflicts"]:
                        st.warning(f"⚠️ {len(result['conflicts'])} conflict(s) detected!")
            elif not uploaded and not url_box.strip():
                st.error("Upload a PDF or enter a URL first.")

        st.divider()
        docs_list = db_get_documents(user_id)
        if docs_list:
            total = sum(d.get("chunks", 0) for d in docs_list)
            st.markdown(f"**{len(docs_list)} source(s) · {total} total chunks**")
            for doc in docs_list:
                icon = "🌐" if doc.get("source_type") == "url" else "📄"
                st.markdown(
                    f"<div class='doc-pill'>"
                    f"<span class='doc-pill-name'>{icon} {doc['name'][:55]}</span>"
                    f"<span class='doc-pill-meta'>{doc.get('chunks', 0)} chunks · "
                    f"{(doc.get('added_at') or '')[:10]}</span></div>",
                    unsafe_allow_html=True
                )
            if st.button("🗑️ Clear All My Data", use_container_width=True, key="clear_all"):
                db_clear_user_data(user_id)
                st.session_state.pop("chat_history", None)
                st.session_state.pop("current_conv_id", None)
                st.rerun()
        else:
            st.info("No documents yet. Upload PDFs or add URLs above.")

    # ── Sources ──────────────────────────────────────
    with tab_src:
        st.markdown("### 🗂️ Document Details")
        docs_list = db_get_documents(user_id)
        if not docs_list:
            st.info("No documents loaded yet.")
        for doc in docs_list:
            icon = "🌐" if doc.get("source_type") == "url" else "📄"
            with st.expander(f"{icon} {doc['name'][:60]}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Chunks", doc.get("chunks", 0))
                c2.metric("Type",   doc.get("source_type", "?").upper())
                c3.metric("Added",  (doc.get("added_at") or "")[:10])
                if doc.get("summary"):
                    st.markdown(f"**Summary:** {doc['summary']}")

    # ── Conflicts ────────────────────────────────────
    with tab_conf:
        st.markdown("### ⚠️ Cross-Document Conflicts")
        st.markdown(
            "<p style='color:#6b7280;font-size:0.83rem;'>"
            "Contradictions automatically detected between your sources. "
            "Add two articles covering the same topic to see conflicts appear here.</p>",
            unsafe_allow_html=True
        )
        conflicts = db_get_conflicts(user_id)
        if not conflicts:
            st.success("✅ No conflicts detected between your sources.")
        else:
            sev_order = {"high": 0, "medium": 1, "low": 2}
            for c in sorted(conflicts,
                            key=lambda x: sev_order.get(x.get("severity", "low"), 2)):
                sev_color = {
                    "high":   "#ef4444",
                    "medium": "#f59e0b",
                    "low":    "#22c55e"
                }.get(c.get("severity", "medium"), "#f59e0b")
                st.markdown(f"""
                <div class='conflict-card'>
                    <div class='conflict-title'>
                        ⚠️ Topic: <span style='color:{sev_color}'>{c.get('topic','?')}</span>
                        &nbsp;·&nbsp;
                        <span style='color:{sev_color}'>{c.get('severity','?').upper()}</span>
                        &nbsp;·&nbsp; {(c.get('detected_at') or '')[:10]}
                    </div>
                    <div style='font-size:0.73rem;color:#6b7280;margin-bottom:6px;'>
                        📄 {c.get('source_a','')[:45]}  vs  📄 {c.get('source_b','')[:45]}
                    </div>
                    <div class='conflict-side'>
                        <span style='color:#a78bfa;font-size:0.68rem;'>SOURCE A CLAIMS:</span><br>
                        {c.get('claim_a','')[:220]}
                    </div>
                    <div class='conflict-side'>
                        <span style='color:#60a5fa;font-size:0.68rem;'>SOURCE B CLAIMS:</span><br>
                        {c.get('claim_b','')[:220]}
                    </div>
                </div>""", unsafe_allow_html=True)

    # ── Knowledge Gaps ───────────────────────────────
    with tab_gaps:
        st.markdown("### 🗺️ Knowledge Gap Analysis")
        c1, c2 = st.columns([3, 1])
        with c1:
            cq = st.text_input(
                "Custom probe question",
                placeholder="What topic should your KB cover?",
                label_visibility="collapsed", key="gap_q"
            )
        with c2:
            run_gaps = st.button("🔍 Detect Gaps", use_container_width=True, key="gap_btn")

        if run_gaps:
            docs_list = db_get_documents(user_id)
            if not docs_list:
                st.warning("Add documents first.")
            else:
                with st.spinner("Probing knowledge base..."):
                    gaps = detect_knowledge_gaps(
                        user_id, [cq.strip()] if cq.strip() else []
                    )
                if not gaps:
                    st.success("✅ Knowledge base covers all probed topics well!")
                else:
                    st.warning(f"Found {len(gaps)} knowledge gap(s):")
                    for g in gaps:
                        st.markdown(
                            f"<div class='gap-item'>"
                            f"❓ <strong>{g['question']}</strong><br>"
                            f"<small style='color:#6b7280'>{g.get('reason','')}</small>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
        else:
            st.info("Click 'Detect Gaps' to analyse your knowledge base coverage.")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
handle_oauth_callback()     # handles ?code= redirect from Google — MUST be first

user = get_current_user()
if user:
    show_main_app(user)
else:
    show_login_page()
