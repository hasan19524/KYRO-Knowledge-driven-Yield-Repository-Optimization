"""Grounded answer prompt for /api/query.

KYRO's identity and response expectations are preserved; Maaz's
anti-hallucination rules are folded in at prompt level (the LLM is still
invoked with an honest empty-context note when retrieval yields nothing —
the call-level short-circuit was deliberately NOT ported because the API
contract expects the answer to flow through the LLM in every READY case).
"""

from __future__ import annotations

# Shown to the model when retrieval produced no usable context. The exact
# wording is part of the observed behaviour asserted by the query API tests.
EMPTY_CONTEXT_NOTE = "No indexed changes matched this question for this repository."

REFUSAL_SENTENCE = (
    "I could not find sufficient evidence in the indexed repository data "
    "to answer this question."
)


def build_query_prompt(*, repository: str, context: str, question: str) -> str:
    return (
        "You are KYRO, a repository intelligence assistant. Answer the user's "
        "question using ONLY the repository context below; do not invent facts "
        "that are not present in the context.\n"
        f'If the context is insufficient to answer, say so explicitly: "{REFUSAL_SENTENCE}"\n'
        "Distinguish retrieved facts from your own reasoning. Be concise and "
        "cite commit shas and file paths from the context when relevant.\n\n"
        f"Repository: {repository}\n\n"
        f"Repository context:\n{context}\n\n"
        f"Question: {question}"
    )
