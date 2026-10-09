"""Public synthetic fixtures: separate from live provider evaluation."""
from .engine import Passage


def demo_corpus():
    return [
        Passage("p1", "d1", "Orion finance report.pdf", 3, "Orion's audited revenue for fiscal year 2025 was $12 million. The report covers the entire company, in US dollars."),
        Passage("p2", "d2", "Orion investor brief.pdf", 7, "Orion's audited revenue for fiscal year 2025 was $18 million. The report covers the entire company, in US dollars."),
        Passage("p3", "d3", "Orion deployment guide.pdf", 2, "Orion stores each user's document passages in PostgreSQL. Row-level security restricts reads and writes to the authenticated owner."),
        Passage("p4", "d4", "Orion security review.pdf", 4, "Orion stores each user's document passages in PostgreSQL. Access is restricted to each authenticated user through row-level security."),
    ]


def demo_cases():
    return {
        "Conflicting revenue figures": {"question": "What was Orion's audited revenue for fiscal year 2025?", "kind": "conflict"},
        "A claim with two supporting documents": {"question": "Where does Orion store each user's document passages?", "kind": "redundant"},
        "Missing evidence: withhold an invented claim": {"question": "What was Orion's audited revenue and profit for fiscal year 2025?", "kind": "missing"},
    }


def fixture_model(case):
    def call(system, payload):
        if "Create at most 3" in system:
            return {"queries": [case["question"]], "intent": "lookup"}
        if "Audit proposed claims" in system:
            return {"checks": [{"index": i, "status": "supported", "evidence_ids": [e["id"] for e in c["evidence"]],
                               "reason": "Deterministic fixture for this public test case."} for i, c in enumerate(payload["claims"])]}
        if "Find factual contradictions" in system:
            findings = []
            for pair in payload["pairs"]:
                a, b = pair["a"]["text"], pair["b"]["text"]
                kind = "contradiction" if "$12 million" in a+b and "$18 million" in a+b else "no_conflict"
                findings.append({"pair": pair["pair"], "kind": kind, "topic": "2025 audited revenue",
                                 "quote_a": a, "quote_b": b, "explanation": "Same company, fiscal year, scope and currency; incompatible revenue values."})
            return {"findings": findings}
        claims = []
        if case["kind"] == "redundant":
            quotes = [{"id": p["id"], "quote": "Orion stores each user's document passages in PostgreSQL."}
                      for p in payload["passages"] if "PostgreSQL" in p["text"]]
            claims.append({"claim": "Orion stores document passages in PostgreSQL.", "evidence": quotes})
        else:
            for p in payload["passages"]:
                if "audited revenue" in p["text"]:
                    claims.append({"claim": f"{p['source']} reports {('$12' if '$12' in p['text'] else '$18')} million in 2025 audited revenue.",
                                   "evidence": [{"id": p["id"], "quote": p["text"]}]})
            if case["kind"] == "missing":
                claims.append({"claim": "Orion earned $7 million in profit.", "evidence": [{"id": "E1", "quote": "Orion earned $7 million in profit."}]})
        return {"claims": claims, "limitations": ["Revenue figures conflict; the documents do not establish which is correct."] if case["kind"] != "redundant" else []}
    return call
