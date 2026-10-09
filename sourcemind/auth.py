"""Session-local Supabase auth and one-use, expiring PKCE redirect state."""
from __future__ import annotations

import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl


class AuthExpired(RuntimeError):
    pass


class OAuthStateStore:
    """Server-local state survives a new Streamlit WebSocket on OAuth return.

    No access tokens are stored here. Deployments with multiple replicas need a
    shared store; a restart deliberately invalidates pending sign-in attempts.
    """
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("CREATE TABLE IF NOT EXISTS oauth_state (nonce TEXT PRIMARY KEY, verifier TEXT NOT NULL, expires REAL NOT NULL)")

    def put(self, nonce: str, verifier: str, ttl: int = 600):
        if not verifier:
            raise ValueError("Missing PKCE verifier")
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("DELETE FROM oauth_state WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO oauth_state VALUES (?, ?, ?)", (nonce, verifier, time.time()+ttl))

    def consume(self, nonce: str) -> str:
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT verifier, expires FROM oauth_state WHERE nonce = ?", (nonce,)).fetchone()
            db.execute("DELETE FROM oauth_state WHERE nonce = ?", (nonce,))
        if not row or row[1] <= time.time():
            raise AuthExpired("Google sign-in expired. Start again from the login page.")
        return row[0]


def new_client(url: str, key: str):
    from supabase import ClientOptions, create_client
    if not url or not key:
        raise ValueError("Supabase is not configured.")
    # Never cache this client across Streamlit sessions. Its mutable auth state
    # includes JWTs and PKCE storage, so global caching can cross user boundaries.
    return create_client(url, key, options=ClientOptions(flow_type="pkce", persist_session=True,
                         auto_refresh_token=False, postgrest_client_timeout=30))


def start_google(client, redirect_url: str, store: OAuthStateStore) -> tuple[str, str]:
    nonce = secrets.token_urlsafe(32)
    parts = urlsplit(redirect_url)
    query = dict(parse_qsl(parts.query))
    query["oauth_state"] = nonce
    redirect = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    response = client.auth.sign_in_with_oauth({"provider": "google", "options": {"redirect_to": redirect}})
    # supabase-auth's storage protocol has get_item; storage key is versioned by
    # the pinned SDK. Fail closed if that SDK contract changes.
    verifier = client.auth._storage.get_item(f"{client.auth._storage_key}-code-verifier")
    store.put(nonce, verifier)
    return response.url, nonce


def finish_google(client, code: str, nonce: str, store: OAuthStateStore, browser_nonce: str):
    if not code or not nonce:
        raise AuthExpired("Google returned an incomplete callback. Start again from this app.")
    if not browser_nonce:
        raise AuthExpired("The sign-in browser cookie is missing. Allow site cookies and start again.")
    if not secrets.compare_digest(nonce, browser_nonce):
        raise AuthExpired("A different Google sign-in attempt replaced this one. Close other login tabs and start again.")
    return client.auth.exchange_code_for_session({"auth_code": code, "code_verifier": store.consume(nonce)})


def accept_session(state, response):
    if not response or not response.session or not response.user:
        raise AuthExpired("No authenticated session was returned.")
    user = response.user
    # Presentation metadata is never used for authorization.
    metadata = user.user_metadata or {}
    state["user"] = {"id": user.id, "email": user.email or "", "name": metadata.get("full_name") or user.email or "Member"}
    state["access_token"] = response.session.access_token
    state["refresh_token"] = response.session.refresh_token
    state["expires_at"] = response.session.expires_at or (time.time()+300)


def ensure_session(state, client):
    """Refresh rotated credentials and validate identity on every app rerun."""
    if not state.get("user"):
        return None
    try:
        if state.get("expires_at", 0) < time.time()+60:
            response = client.auth.refresh_session(state.get("refresh_token"))
            accept_session(state, response)
        verified = client.auth.get_user(state["access_token"]).user
        if not verified or verified.id != state["user"]["id"]:
            raise AuthExpired("Session identity mismatch")
        # The per-session client already owns its JWT; attaching the validated
        # token also ensures PostgREST uses that identity after a refresh.
        client.postgrest.auth(state["access_token"])
        return state["user"]
    except Exception as exc:
        clear_session(state)
        raise AuthExpired("Your session expired or authentication is unavailable. Please sign in again.") from exc


def clear_session(state):
    # Clear uploaded files, retrieved passages, forms, history, tokens and client.
    # This mapping is session-local; unrelated users' sessions are untouched.
    for key in list(state):
        del state[key]
