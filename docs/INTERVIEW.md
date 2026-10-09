# Interview walkthrough

## A defensible introduction

“I built SourceMind, an adaptive document investigation workspace. It does hybrid retrieval, decomposes complex questions, validates every quotation and audits the support for each claim. It also compares PDFs for contradictions and shows which claims lose support when a source is removed.”

## Five-minute demonstration

1. Open **Explore the Evidence Lab** before signing in. Say clearly that these are reproducible synthetic fixtures that demonstrate engineering checks.
2. Run **Conflicting revenue figures**. Inspect the separate $12m and $18m statements, the PDF page numbers and the unresolved discrepancy. Do not claim the software can know which report is true.
3. Run **A claim with two supporting documents**. Remove either document in the source stress report: the claim retains a citation from the other. Explain that provenance diversity is not proof of independent reporting.
4. Run **Missing evidence**. Inspect the withheld profit claim: its purported quote does not occur in the retrieved passage.
5. Sign into your private workspace, upload two real PDFs, ask a comparison and show the live claim ledger, retrieval trace and PDF disagreement scan. Download the JSON evidence report.

## Questions worth being ready for

**Why hybrid retrieval?** Semantic embeddings handle paraphrases but can miss exact product IDs, numbers and names. BM25 and reciprocal rank fusion add lexical evidence without treating ranks as truth probabilities.

**What is adaptive?** A direct lookup avoids the planner. Comparisons, conversation follow-ups and Forensic mode produce at most three search queries. All answers go through quote validation and a support audit. This is bounded planning, not an unlimited agent loop.

**Why not “confidence: 93%”?** Similarity says how related a passage is to the query. It cannot establish a probability that an answer is true. I show validated quotes, withheld claims and source dependency instead.

**How do you prevent hallucinations?** Reject nonexistent quotation IDs and quote text, require a separate support check, and abstain when checks fail. The semantic judge can still make mistakes, so the evidence is inspectable and the limitations are explicit.

**What does the stress test measure?** The displayed claim's reliance on particular documents. Remove one document's citations, then count unsupported claims. The separate omission experiment re-runs the entire pipeline with one source excluded. Compare the alternative answer and its audited citations with the original. Neither proves causal dependence or objective truth; model/retrieval variation may affect the alternative.

**Why were contradictions missed?** The old pipeline excluded very similar vectors. Numeric edits can have almost identical embeddings, so the new scan keeps them and checks entity, period, units and scope. It validates quotations from both sides.

**How are users isolated?** Session-local clients, verified JWT identity, RLS predicates and matching document/conversation ownership foreign keys. Tests use two distinct identities to try cross-user reads, writes and references.

**What fails on a redeploy?** The old Chroma index lived on an ephemeral app disk; only metadata persisted in Postgres. The new pipeline stores passages and embeddings in Postgres in one transaction. Legacy missing text still requires re-uploading the source.

**What would you scale next?** pgvector HNSW with authenticated filtering, an async PDF ingestion worker, resumable jobs, shared OAuth state, rate limits by account, OCR and a labeled real-model evaluation dataset.

## Credible advertising copy

**“SourceMind: document answers with an evidence ledger. Trace every claim to its page, reveal disagreements, and test how much your answer depends on each source.”**

Avoid “world's first”, “zero hallucinations”, “fully verified truth” or “no one has ever seen this”. Demonstrate the actual behavior and publish reproducible results instead.
