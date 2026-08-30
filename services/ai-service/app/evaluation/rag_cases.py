"""RAG eval cases — Postgres-only (pgvector), same reason app/rag/search.py itself isn't covered
by the offline SQLite test suite. Run these live: `python scripts/run_evaluations.py`."""

from app.evaluation.base import EvalCase, EvalOutcome, register_case
from app.rag.context import build_rag_context
from app.rag.pipeline import ingest_document
from app.rag.search import hybrid_search

_KNOWN_CONTENT = "Krixil AI uses pgvector for semantic search over documents tenants upload."
_KNOWN_FILENAME = "eval_fixture_pgvector.txt"


async def _known_document_retrieval(session, tenant_ctx, provider, storage) -> EvalOutcome:
    document = await ingest_document(
        session, storage, provider, tenant_ctx, _KNOWN_FILENAME, _KNOWN_CONTENT.encode()
    )
    if document.status != "ready":
        return EvalOutcome(
            passed=False,
            details={"reason": "fixture document failed to ingest", "status": document.status},
        )

    results = await hybrid_search(session, tenant_ctx, provider, "pgvector semantic search")
    found = any(r.filename == _KNOWN_FILENAME for r in results)
    return EvalOutcome(
        passed=found, details={"result_count": len(results), "found_expected_document": found}
    )


register_case(
    EvalCase(name="rag.known_document_retrieval", category="rag", run=_known_document_retrieval)
)


async def _chat_context_cites_relevant_document(
    session, tenant_ctx, provider, storage
) -> EvalOutcome:
    document = await ingest_document(
        session, storage, provider, tenant_ctx, _KNOWN_FILENAME, _KNOWN_CONTENT.encode()
    )
    if document.status != "ready":
        return EvalOutcome(
            passed=False,
            details={"reason": "fixture document failed to ingest", "status": document.status},
        )

    _rag_message, citations = await build_rag_context(
        session, tenant_ctx, provider, "How does Krixil AI do semantic search?"
    )
    cited = any(c.document_id == document.id for c in citations)
    return EvalOutcome(
        passed=cited, details={"citation_count": len(citations), "cited_expected_document": cited}
    )


register_case(
    EvalCase(
        name="citation_quality.chat_cites_relevant_document",
        category="citation_quality",
        run=_chat_context_cites_relevant_document,
    )
)
