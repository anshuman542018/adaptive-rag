"""Authenticated, durable Postgres storage. No unscoped data caches."""
from __future__ import annotations
from .engine import Passage


class Repository:
    def __init__(self, client, user_id: str):
        self.client, self.user_id = client, user_id

    def rows(self, table: str, columns: str = "*") -> list[dict]:
        result, offset = [], 0
        while True:
            page = self.client.table(table).select(columns).eq("user_id", self.user_id).order("id").range(offset, offset+499).execute().data or []
            result.extend(page)
            if table == "document_chunks" and len(result) > 3000:
                raise ValueError("Knowledge base exceeds the 3,000-passage application limit.")
            if len(page) < 500:
                return result
            offset += 500

    def documents(self):
        documents = self.rows("documents", "*,document_chunks(count)")
        for document in documents:
            counts = document.pop("document_chunks", [])
            document["indexed_chunks"] = counts[0].get("count", 0) if counts else 0
        return sorted(documents, key=lambda d: d.get("added_at", ""), reverse=True)

    def corpus(self) -> list[Passage]:
        docs = {d["id"]: d for d in self.documents()}
        return [Passage(r["id"], r["document_id"], docs[r["document_id"]]["name"],
                        r.get("page"), r["content"], r.get("embedding") or [])
                for r in self.rows("document_chunks") if r["document_id"] in docs]

    def ingest(self, document: dict, vectors: list[list[float]]) -> dict:
        if len(vectors) != len(document["chunks"]):
            raise ValueError("Embedding count does not match passages.")
        chunks = [{**c, "embedding": v, "embedding_model": "all-MiniLM-L6-v2"}
                  for c, v in zip(document["chunks"], vectors)]
        return self.client.rpc("ingest_document", {"p_document": {k: v for k, v in document.items() if k != "chunks"},
                                "p_chunks": chunks}).execute().data

    def delete_document(self, document_id: str):
        # FK cascades remove chunks. Do not clear any other user's rows.
        self.client.table("documents").delete().eq("id", document_id).eq("user_id", self.user_id).execute()
        self.client.table("conflicts").delete().eq("user_id", self.user_id).execute()

    def conversations(self):
        return sorted(self.rows("conversations"), key=lambda c: c.get("updated_at", ""), reverse=True)

    def create_conversation(self, title: str) -> str:
        data = self.client.table("conversations").insert({"user_id": self.user_id, "title": title[:80]}).execute().data
        if not data:
            raise RuntimeError("Conversation was not saved.")
        return data[0]["id"]

    def messages(self, conversation_id: str):
        return (self.client.table("chat_messages").select("*").eq("user_id", self.user_id)
                .eq("conversation_id", conversation_id).order("created_at").limit(200).execute().data or [])

    def save_message(self, conversation_id: str, role: str, content: str, result: dict | None = None):
        self.client.table("chat_messages").insert({"user_id": self.user_id,
            "conversation_id": conversation_id, "role": role, "content": content,
            "sources": (result or {}).get("sources", []), "confidence": 0,
            "evidence_report": result or {}}).execute()
        from datetime import datetime, timezone
        self.client.table("conversations").update({"updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", conversation_id).eq("user_id", self.user_id).execute()

    def save_scan(self, report: dict):
        # Keep legacy columns for existing deployment compatibility.
        findings = report.get("findings", [])
        for finding in findings:
            self.client.table("conflicts").upsert({"user_id": self.user_id,
                "source_a": finding["source_a"], "source_b": finding["source_b"],
                "topic": finding["topic"], "claim_a": finding["quote_a"], "claim_b": finding["quote_b"],
                "severity": "medium", "finding": finding,
                "pair_key": "|".join(sorted([finding["chunk_a"], finding["chunk_b"]]))}, on_conflict="user_id,pair_key").execute()
