"""SourceMind — inspect the evidence behind every answer."""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from sourcemind.auth import (AuthExpired, OAuthStateStore, accept_session, clear_session,
                            ensure_session, finish_google, new_client, start_google)
from sourcemind.engine import answer, contradiction_scan, omission_experiment
from sourcemind.ingestion import read_pdf, read_url
from sourcemind.repository import Repository
from sourcemind.browser_binding import browser_binding

load_dotenv()
st.set_page_config(page_title="SourceMind · Evidence Lab", page_icon="◈", layout="wide")
LOG = logging.getLogger("sourcemind")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
html,body,[class*="css"] {font-family:'DM Sans',sans-serif;}
.stApp {background:#080e19;color:#edf3ff;}
[data-testid="stSidebar"] {background:#101827;border-right:1px solid #263349;}
h1 {letter-spacing:-.05em;} [data-testid="stMetric"] {background:#121e30;border:1px solid #253650;border-radius:12px;padding:18px;}
.eyebrow {color:#67e8c4;font-size:.78rem;letter-spacing:.18em;text-transform:uppercase;}
.hero {font-size:3.2rem;font-weight:700;letter-spacing:-.06em;margin:0;}
.deck {color:#a6b7d0;max-width:720px;font-size:1.1rem;line-height:1.6;}
.stButton>button[kind="primary"] {background:#41d9b0;color:#051b16;border:0;}
</style>""", unsafe_allow_html=True)


def config(key: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(key, os.environ.get(key, default)))
    except FileNotFoundError:
        return os.environ.get(key, default)


def client():
    if "supabase_client" not in st.session_state:
        st.session_state["supabase_client"] = new_client(config("SUPABASE_URL"), config("SUPABASE_PUBLISHABLE_KEY") or config("SUPABASE_ANON_KEY"))
    return st.session_state["supabase_client"]


@st.cache_resource
def encoder():
    os.environ.setdefault("USE_TF", "0")
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


def embed(text: str) -> list[float]:
    return encoder().encode(text, normalize_embeddings=True).tolist()


def model(system: str, payload: dict) -> dict:
    from groq import Groq
    if not config("GROQ_API_KEY"):
        raise ValueError("Groq is not configured.")
    result = Groq(api_key=config("GROQ_API_KEY"), timeout=45, max_retries=1).chat.completions.create(
        model=config("GROQ_MODEL", "llama-3.3-70b-versatile"), temperature=0,
        response_format={"type": "json_object"}, max_tokens=3000,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
    return json.loads(result.choices[0].message.content)


def failure(action: str, exc: Exception):
    # Provider errors can include private input or credentials: log type only.
    LOG.warning("%s failed (%s)", action, type(exc).__name__)
    text = str(exc).lower()
    if "invalid login" in text:
        st.error("The email or password is incorrect.")
    elif "email not confirmed" in text:
        st.error("Confirm your email before signing in.")
    elif "rate" in text or "429" in text:
        st.error("The service is busy or its rate limit was reached. Please try again shortly.")
    elif "3000" in text:
        st.error("Your knowledge base reached 3,000 passages. Remove a source before adding more.")
    elif "schema cache" in text or "does not exist" in text:
        st.error("The database upgrade has not been applied. Contact the app owner.")
    else:
        st.error(f"{action} could not finish. Please retry.")


def oauth_store():
    return OAuthStateStore(Path(".sourcemind") / "oauth.sqlite")


def oauth_callback():
    if "error" in st.query_params:
        st.query_params.clear()
        st.warning("Google sign-in was canceled or refused. Try email sign-in or start again.")
    if "code" in st.query_params:
        binding = browser_binding("read", key="oauth_return")
        if binding is None:
            st.info("Completing secure Google sign-in…")
            st.stop()
        try:
            response = finish_google(client(), st.query_params["code"], st.query_params.get("oauth_state", ""),
                                     oauth_store(), binding.get("nonce", ""))
            accept_session(st.session_state, response)
        except Exception as exc:
            st.session_state["oauth_failed"] = True
            failure("Google sign-in", exc)
        finally:
            st.query_params.clear()
        if st.session_state.get("user"):
            st.rerun()
    if "token_hash" in st.query_params:
        try:
            kind = st.query_params.get("type", "email")
            if kind not in {"email", "signup", "recovery"}:
                raise ValueError("Invalid verification type")
            response = client().auth.verify_otp({"token_hash": st.query_params["token_hash"], "type": kind})
            accept_session(st.session_state, response)
            st.session_state["recovery"] = kind == "recovery"
        except Exception as exc:
            failure("Email verification", exc)
        finally:
            st.query_params.clear()
        if st.session_state.get("user"):
            st.rerun()


def hero():
    st.markdown("<p class='eyebrow'>Private knowledge · Visible evidence</p><p class='hero'>SourceMind</p>", unsafe_allow_html=True)
    st.markdown("<p class='deck'>Ask your documents. Inspect every claim. Discover disagreements—and see which answers depend on a single source.</p>", unsafe_allow_html=True)


def login_page():
    hero()
    sign_in, sign_up, recover, lab = st.tabs(["Sign in", "Create account", "Reset password", "Explore the Evidence Lab"])
    configured = bool(config("SUPABASE_URL") and (config("SUPABASE_PUBLISHABLE_KEY") or config("SUPABASE_ANON_KEY")))
    with sign_in:
        st.subheader("Welcome to your private workspace")
        if st.session_state.pop("oauth_failed", False):
            st.error("Google sign-in could not finish. Start again in this browser and allow site cookies.")
        if not configured:
            st.info("Account access is awaiting database configuration. The Evidence Lab is available to explore.")
        with st.form("login", clear_on_submit=True):
            email = st.text_input("Email", max_chars=254)
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary", disabled=not configured)
        if submitted:
            try:
                if not email.strip() or not password:
                    raise ValueError("Email and password required")
                accept_session(st.session_state, client().auth.sign_in_with_password({"email": email.strip(), "password": password}))
                st.rerun()
            except Exception as exc:
                failure("Sign-in", exc)
        if config("ENABLE_GOOGLE_AUTH", "true").lower() == "true" and configured:
            if st.button("Prepare Google sign-in"):
                try:
                    url, nonce = start_google(client(), config("REDIRECT_URL", "https://adaptive-rag1.streamlit.app/"), oauth_store())
                    st.session_state["google_url"] = url
                    st.session_state["google_nonce"] = nonce
                except Exception as exc:
                    failure("Google sign-in", exc)
            if st.session_state.get("google_url"):
                # Browser-bound state prevents a callback link opened in another
                # browser from signing that browser into the initiator's account.
                nonce = st.session_state["google_nonce"]
                binding = browser_binding("write", nonce, key=f"oauth_start_{nonce}")
                if binding and binding.get("ready"):
                    st.link_button("Continue with Google", st.session_state["google_url"])
                elif binding is not None:
                    st.error("Allow site cookies to use Google sign-in, or sign in with email.")
        st.caption("Your documents and conversations belong to your account. A full browser reload requires signing in again.")
    with sign_up:
        with st.form("signup", clear_on_submit=True):
            name = st.text_input("Name", max_chars=80)
            email = st.text_input("Email address", max_chars=254)
            password = st.text_input("Choose password (at least 8 characters)", type="password")
            confirm = st.text_input("Repeat password", type="password")
            submitted = st.form_submit_button("Create account", disabled=not configured)
        if submitted:
            if not name.strip() or "@" not in email or len(password) < 8 or password != confirm:
                st.error("Enter a name, valid email and matching passwords of at least 8 characters.")
            else:
                try:
                    res = client().auth.sign_up({"email": email.strip(), "password": password,
                        "options": {"data": {"full_name": name.strip()}, "email_redirect_to": config("REDIRECT_URL", "https://adaptive-rag1.streamlit.app/")}})
                    if res.session:
                        accept_session(st.session_state, res)
                        st.rerun()
                    else:
                        st.success("Check your email to confirm your account, then sign in.")
                except Exception as exc:
                    failure("Account creation", exc)
    with recover:
        st.write("Request a reset email, then follow its link to choose a new password.")
        with st.form("request_reset", clear_on_submit=True):
            email = st.text_input("Account email")
            submitted = st.form_submit_button("Send reset email", disabled=not configured)
        if submitted and email.strip():
            try:
                client().auth.reset_password_email(email.strip(), {"redirect_to": config("REDIRECT_URL", "https://adaptive-rag1.streamlit.app/")})
                st.success("If an account exists, a reset email has been sent.")
            except Exception as exc:
                failure("Password reset", exc)
    with lab:
        evidence_lab()


def recovery_page():
    st.subheader("Choose a new password")
    with st.form("change_password", clear_on_submit=True):
        password = st.text_input("New password", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        submit = st.form_submit_button("Update password")
    if submit:
        if len(password) < 8 or password != confirm:
            st.error("Enter matching passwords of at least 8 characters.")
        else:
            try:
                client().auth.update_user({"password": password})
                st.session_state.pop("recovery", None)
                st.rerun()
            except Exception as exc:
                failure("Password update", exc)


def show_report(report: dict, key: str, repo=None):
    st.caption(f"Evidence status: {report.get('status', 'legacy')} · No numerical confidence is claimed.")
    for limitation in report.get("limitations", []):
        st.info(limitation)
    evidence, stress, trace = st.tabs(["Claim ledger & citations", "Source stress test", "Retrieval trace"])
    with evidence:
        sources = {s["id"]: s for s in report.get("sources", [])}
        for i, claim in enumerate(report.get("claims", []), 1):
            st.markdown(f"**Claim {i}**")
            st.write(claim["claim"])
            for e in claim["evidence"]:
                s = sources[e["id"]]
                page = f" · page {s['page']}" if s.get("page") else ""
                st.caption(f"[{e['id']}] {s['source']}{page}")
                st.code(e["quote"], language=None, wrap_lines=True)
        if report.get("rejected_claims"):
            with st.expander(f"{len(report['rejected_claims'])} withheld claim(s)"):
                for claim in report["rejected_claims"]:
                    st.write(claim["claim"])
                    st.caption(claim["reason"])
    with stress:
        data = report.get("stress", {})
        st.write("What happens to the displayed claims if one document's citations disappear?")
        for row in data.get("removals", []):
            st.write(f"**Remove {row['source']}** → {row['retained_fraction']:.0%} of claims retain a citation")
            if row["unsupported_claims"]:
                st.caption("Claims without remaining support: " + ", ".join(map(str, row["unsupported_claims"])))
        st.caption(data.get("limitation", "No validated claims to test."))
        if repo and report.get("question"):
            cited_docs = {s["document_id"]: s["source"] for s in report.get("sources", []) if s.get("document_id")}
            if cited_docs:
                st.divider()
                st.write("**Test an alternative evidence set**")
                st.caption("Re-run retrieval and both evidence checks on your current library with one document omitted. The original answer is kept.")
                omitted = st.selectbox("Document to omit", list(cited_docs), format_func=cited_docs.get, key=f"omit_choice_{key}")
                if st.button("Re-run without this document", key=f"omit_run_{key}"):
                    try:
                        with st.spinner("Running the investigation without this source…"):
                            st.session_state[f"omission_{key}"] = omission_experiment(report["question"], repo.corpus(), omitted,
                                model, embed, report.get("history", []))
                    except Exception as exc:
                        failure("Source omission experiment", exc)
                alternate = st.session_state.get(f"omission_{key}")
                if alternate:
                    st.write("**Alternative answer**")
                    st.write(alternate["answer"])
                    st.json(alternate["experiment"])
                    with st.expander("Inspect alternative citations"):
                        show_report(alternate, f"alternate_{key}")
    with trace:
        for stage in report.get("trace", []):
            st.json(stage)
        st.json(report.get("metrics", {}))
    st.download_button("Download evidence report", json.dumps(report, indent=2, ensure_ascii=False),
                       file_name="sourcemind-evidence.json", mime="application/json", key=f"export_{key}")


def evidence_lab():
    from sourcemind.lab import demo_corpus, demo_cases, fixture_model
    st.subheader("Evidence Lab")
    st.write("A reproducible engineering demonstration: conflicting numbers, missing evidence and source dependency.")
    st.caption("Uses public synthetic passages and deterministic fixtures. This demonstrates pipeline checks; it is not a live AI quality benchmark.")
    selected = st.selectbox("Challenge", list(demo_cases()))
    case = demo_cases()[selected]
    st.write(case["question"])
    if st.button("Run challenge", key="run_lab", type="primary"):
        st.session_state["lab_report"] = answer(case["question"], demo_corpus(), fixture_model(case))
        st.session_state["lab_selected"] = selected
    if st.session_state.get("lab_report") and st.session_state.get("lab_selected") == selected:
        report = st.session_state["lab_report"]
        st.write(report["answer"])
        show_report(report, "lab")
    with st.expander("Inspect the synthetic source passages"):
        for p in demo_corpus():
            st.caption(f"{p.source} · page {p.page}")
            st.code(p.text, language=None, wrap_lines=True)


def workspace(user: dict):
    repo = Repository(client(), user["id"])
    with st.sidebar:
        st.title("◈ SourceMind")
        st.write(user["name"])
        st.caption(user["email"])
        if st.button("Sign out"):
            try:
                client().auth.sign_out({"scope": "local"})
            except Exception:
                pass
            clear_session(st.session_state)
            st.rerun()
        st.divider()
        mode = st.radio("Investigation depth", ["Adaptive", "Forensic"], help="Forensic always plans multiple searches. Both modes validate citations and audit claims.")
        if st.button("New conversation"):
            st.session_state.pop("conversation_id", None)
            st.rerun()
        for conv in repo.conversations()[:25]:
            if st.button(conv["title"], key=f"conv_{conv['id']}"):
                st.session_state["conversation_id"] = conv["id"]
                st.rerun()
    hero()
    docs = repo.documents()
    cols = st.columns(3)
    cols[0].metric("Private sources", len(docs))
    cols[1].metric("Stored passages", sum(d.get("indexed_chunks", 0) for d in docs))
    cols[2].metric("Evidence checks", "Quote + audit")
    chat, library, conflicts, gaps, lab = st.tabs(["Ask & inspect", "Source library", "PDF disagreements", "Knowledge gaps", "Evidence Lab"])
    with chat:
        conversation_id = st.session_state.get("conversation_id")
        history = repo.messages(conversation_id) if conversation_id else []
        for msg in history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if msg.get("evidence_report"):
                    with st.expander("Inspect answer evidence"):
                        show_report(msg["evidence_report"], msg["id"], repo)
        if not docs:
            st.info("Add PDFs or web pages in the Source library to begin.")
        question = st.chat_input("Ask a question across your documents", disabled=not docs, max_chars=2000)
        if question:
            try:
                if not conversation_id:
                    conversation_id = repo.create_conversation(question)
                    st.session_state["conversation_id"] = conversation_id
                repo.save_message(conversation_id, "user", question)
                with st.spinner("Retrieving passages, checking quotes and auditing claims…"):
                    report = answer(question, repo.corpus(), model, embed=embed, history=history, mode=mode.lower())
                repo.save_message(conversation_id, "assistant", report["answer"], report)
                st.rerun()
            except Exception as exc:
                failure("Answer generation or saving", exc)
    with library:
        st.subheader("Add evidence to your private library")
        st.caption("PDFs: up to 15 MB / 200 pages / 500 passages per source. Workspace: 3,000 passages. Text is sent to Groq when answering or checking disagreements.")
        uploads = st.file_uploader("PDF documents", type=["pdf"], accept_multiple_files=True)
        urls = st.text_area("Public web pages (one URL per line)", max_chars=4000)
        if st.button("Index sources", type="primary"):
            inputs = [("pdf", f) for f in uploads or []] + [("url", u.strip()) for u in urls.splitlines() if u.strip()]
            if not inputs:
                st.warning("Choose a PDF or enter a web page URL.")
            for kind, source in inputs[:10]:
                try:
                    with st.spinner("Extracting pages and storing searchable passages…"):
                        doc = read_pdf(source.getvalue(), source.name) if kind == "pdf" else read_url(source)
                        if doc["fingerprint"] in {d.get("fingerprint") for d in repo.documents()}:
                            st.info(f"Already indexed: {doc['name']}")
                            continue
                        vectors = encoder().encode([c["content"] for c in doc["chunks"]], normalize_embeddings=True, batch_size=32).tolist()
                        result = repo.ingest(doc, vectors)
                        st.success(f"{doc['name']}: {result.get('chunks', 0)} passages stored ({result['status']}).")
                        st.session_state.pop("scan_report", None)
                except ValueError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    failure("Document indexing", exc)
            if len(inputs) > 10:
                st.warning("Only the first 10 sources were processed. Add the remainder in another batch.")
        st.divider()
        for doc in repo.documents():
            with st.expander(doc["name"]):
                st.caption(f"{doc.get('page_count') or '?'} pages · {doc['indexed_chunks']} durable passages · {doc.get('added_at', '')[:10]}")
                st.write(doc.get("summary", ""))
                if not doc["indexed_chunks"]:
                    st.warning("This legacy record has no durable passages. Re-upload the original PDF to restore searchable evidence; then remove this old record.")
                consent = st.checkbox("Remove this source and its stored passages", key=f"remove_ok_{doc['id']}")
                if st.button("Remove source", disabled=not consent, key=f"remove_{doc['id']}"):
                    repo.delete_document(doc["id"])
                    st.session_state.pop("scan_report", None)
                    st.rerun()
    with conflicts:
        st.subheader("Where your PDFs disagree")
        st.write("Compare topical passages across documents, with exact quotations and page numbers on both sides. Historical changes and different scopes are shown separately.")
        budget = st.select_slider("Comparison budget", options=[12, 24, 48], value=12)
        if st.button("Check cross-document disagreements", disabled=len(docs) < 2):
            try:
                with st.spinner("Comparing passages and checking quotation provenance…"):
                    report = contradiction_scan(repo.corpus(), model, max_pairs=budget)
                    repo.save_scan(report)
                    st.session_state["scan_report"] = report
            except Exception as exc:
                failure("Disagreement scan", exc)
        report = st.session_state.get("scan_report")
        if report:
            st.caption(f"{report['checked_pairs']} pairs assessed · {report['unexamined_pairs']} candidate pairs outside budget · {report['failed_pairs']} failed checks")
            st.caption(report["note"])
            findings = report["findings"]
        else:
            findings = [r["finding"] for r in repo.rows("conflicts") if r.get("finding")]
        for finding in findings:
            with st.expander(f"{finding['kind'].replace('_', ' ').title()} · {finding['topic']}", expanded=True):
                left, right = st.columns(2)
                for col, side in [(left, "a"), (right, "b")]:
                    with col:
                        st.caption(f"{finding[f'source_{side}']} · page {finding.get(f'page_{side}') or 'web'}")
                        st.code(finding[f"quote_{side}"], language=None, wrap_lines=True)
                st.write(finding["explanation"])
        if report and not findings:
            st.info("No disagreements found in the assessed pairs. This does not establish that all documents agree.")
        if report:
            st.download_button("Download disagreement report", json.dumps(report, indent=2), "sourcemind-disagreements.json", "application/json")
    with lab:
        evidence_lab()

    with gaps:
        st.subheader("Which questions can your evidence support?")
        st.write("Probe up to three questions. A gap means no answer passed the evidence checks; it does not prove the information is absent from every page.")
        with st.form("coverage_probes"):
            questions = st.text_area("Probe questions (one per line)", max_chars=3000)
            run = st.form_submit_button("Check evidence coverage", disabled=not docs)
        if run:
            try:
                corpus = repo.corpus()
                probes = [q.strip() for q in questions.splitlines() if q.strip()][:3]
                with st.spinner("Testing whether the retrieved evidence supports each question…"):
                    st.session_state["coverage_reports"] = [(q, answer(q, corpus, model, embed)) for q in probes]
            except Exception as exc:
                failure("Coverage check", exc)
        for i, (question, report) in enumerate(st.session_state.get("coverage_reports", [])):
            with st.expander(question):
                st.write("Evidence gap" if report["status"] == "abstained" else "Evidence found" if report["status"] == "supported" else "Partial coverage")
                st.write(report["answer"])
                show_report(report, f"coverage_{i}")


def main():
    try:
        oauth_callback()
        user = ensure_session(st.session_state, client()) if st.session_state.get("user") else None
        if user and st.session_state.get("recovery"):
            recovery_page()
        elif user:
            workspace(user)
        else:
            login_page()
    except AuthExpired as exc:
        st.warning(str(exc))
        login_page()
    except Exception as exc:
        failure("Workspace loading", exc)
        st.button("Retry", on_click=lambda: None)


if __name__ == "__main__":
    main()
