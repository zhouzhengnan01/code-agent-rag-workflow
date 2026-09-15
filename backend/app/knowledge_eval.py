import time

from .knowledge_service import search


async def evaluate(payload):
    cases = payload.get("cases") or []
    if not isinstance(cases, list) or not cases or len(cases) > 100:
        raise ValueError("cases must contain between 1 and 100 evaluation cases")
    local_ids = payload.get("local_knowledge_ids") or []
    ragflow_ids = payload.get("ragflow_knowledge_ids") or []
    if not local_ids or not ragflow_ids:
        raise ValueError("local_knowledge_ids and ragflow_knowledge_ids are required")
    top_k = min(max(int(payload.get("top_k", 5)), 1), 20)
    runs = {"local": [], "ragflow": []}
    for case in cases:
        query = str(case.get("query") or "").strip()
        if not query:
            raise ValueError("Every evaluation case requires a query")
        expected = {str(value) for value in case.get("expected_sources") or []}
        for label, ids in (("local", local_ids), ("ragflow", ragflow_ids)):
            diagnostics = {}
            started = time.perf_counter()
            results = await search(query, ids, top_k, diagnostics=diagnostics)
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            sources = [str(item.get("source") or "") for item in results]
            first_rank = next((index for index, source in enumerate(sources, 1) if source in expected), None)
            hits = len(expected.intersection(sources))
            runs[label].append({
                "query": query,
                "expected_sources": sorted(expected),
                "sources": sources,
                "scores": [round(float(item.get("score") or 0), 6) for item in results],
                "hit_at_k": 1 if first_rank else 0,
                "reciprocal_rank": round(1 / first_rank, 6) if first_rank else 0,
                "source_recall_at_k": round(hits / len(expected), 6) if expected else None,
                "latency_ms": latency_ms,
                "diagnostics": diagnostics,
            })
    summary = {}
    for label, rows in runs.items():
        evaluated = [row for row in rows if row["expected_sources"]]
        summary[label] = {
            "cases": len(rows),
            "evaluated_cases": len(evaluated),
            "hit_at_k": round(sum(row["hit_at_k"] for row in evaluated) / len(evaluated), 6) if evaluated else None,
            "mrr": round(sum(row["reciprocal_rank"] for row in evaluated) / len(evaluated), 6) if evaluated else None,
            "mean_source_recall_at_k": round(sum(row["source_recall_at_k"] for row in evaluated) / len(evaluated), 6) if evaluated else None,
            "mean_latency_ms": round(sum(row["latency_ms"] for row in rows) / len(rows), 2),
        }
    return {"top_k": top_k, "summary": summary, "runs": runs}
