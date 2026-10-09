from __future__ import annotations

from typing import Any


class HybridRanker:
    @staticmethod
    def fuse_and_rank(
        exact_results: list[dict[str, Any]],
        fts_results: list[dict[str, Any]],
        query: str,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        scores: dict[str, float] = {}
        items: dict[str, dict[str, Any]] = {}
        reasons: dict[str, str] = {}

        q_lower = query.lower()

        # Score exact results (Weight: 1.5)
        for rank, item in enumerate(exact_results):
            key = item.get("symbol_key") or f"{item['file_path']}::{item['title']}"
            items[key] = item
            rrf = 1.5 / (60.0 + rank + 1)
            scores[key] = scores.get(key, 0.0) + rrf
            reasons[key] = "exact_symbol_match"

        # Score FTS results (Weight: 1.0, except 'occurrence' rows which are
        # single call-site mentions and get down-weighted to avoid short-document
        # BM25 bias drowning out actual declarations/docs).
        for rank, item in enumerate(fts_results):
            key = item.get("symbol_key") or f"{item['file_path']}::{item['title']}"
            if key not in items:
                items[key] = item
            weight = 0.3 if item.get("entity_type") == "occurrence" else 1.0
            rrf = weight / (60.0 + rank + 1)
            scores[key] = scores.get(key, 0.0) + rrf

            # Add bonus if title or signature directly mentions query tokens
            title_lower = (item.get("title") or "").lower()
            if q_lower in title_lower:
                scores[key] += 0.02
                reasons[key] = "title_exact_phrase_match"
            elif key not in reasons:
                reasons[key] = "fts_lexical_match"

        # Sort by final score descending
        sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)

        ranked: list[dict[str, Any]] = []
        for rank, k in enumerate(sorted_keys[:limit]):
            entry = dict(items[k])
            entry["score"] = round(scores[k], 4)
            entry["rank"] = rank + 1
            entry["match_reason"] = reasons.get(k, "hybrid_match")
            ranked.append(entry)

        return ranked
