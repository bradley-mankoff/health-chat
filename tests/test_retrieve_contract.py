"""Contract tests for positive-relevance retrieval (HCH-5).

Shared rule: BM25 scores <= 0 carry no lexical signal and must never
surface unrelated record or guideline context. Triage across matched
domains is deterministic (sorted-domain iteration); an empty record
result falls back to a generic record query inside _run_chat.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from rank_bm25 import BM25Okapi
import asyncio

import server
from server import _tokenize, retrieve, top_k_relevant, triage_guidelines


def _fake_index(monkeypatch):
    records = [
        "hemoglobin 14.2 g/dL normal range",
        "cholesterol total 250 mg/dL high",
        "vitamin d 18 ng/mL low",
    ]
    gl = {
        "lipids": {
            "bm25": BM25Okapi([_tokenize("cholesterol LDL HDL triglyceride lipid guideline")]),
            "chunks": ["lipid guideline chunk"],
        },
        "anemia": {
            "bm25": BM25Okapi([_tokenize("anemia iron hemoglobin hematocrit guideline")]),
            "chunks": ["anemia guideline chunk"],
        },
    }
    monkeypatch.setattr(server, "INDEX", {
        "bm25": BM25Okapi([_tokenize(r) for r in records]),
        "chunks": records,
        "guidelines": gl,
        "structured": [],
        "files": [],
    })
    return records


def test_top_k_relevant_drops_non_positive():
    assert top_k_relevant([0.0, -1.0, 2.0, 1.0], 4) == [2, 3]


def test_top_k_relevant_empty_and_bounds():
    assert top_k_relevant([], 3) == []
    assert top_k_relevant([1.0], 0) == []
    assert top_k_relevant([0.5], 10) == [0]
    assert top_k_relevant([-2.0, 0.0], 2) == []


def test_top_k_relevant_stable_ties():
    assert top_k_relevant([1.0, 1.0, 0.5], 2) == [0, 1]


def test_retrieve_unrelated_returns_empty(monkeypatch):
    _fake_index(monkeypatch)
    assert retrieve("breakfast weather forecast") == []


def test_retrieve_known_query_returns_record(monkeypatch):
    records = _fake_index(monkeypatch)
    out = retrieve("hemoglobin level")
    assert out and out[0] == records[0]
def test_triage_tie_prefers_sorted_domain(monkeypatch):
    # Identical stub scores in both matched domains: the alphabetically
    # first domain must win every time, independent of hash seed.
    class _Stub:
        def get_scores(self, toks):
            return [1.0]

    gl = {
        "lipids": {"bm25": _Stub(), "chunks": ["lipid guideline chunk"]},
        "anemia": {"bm25": _Stub(), "chunks": ["anemia guideline chunk"]},
    }
    monkeypatch.setattr(server, "INDEX", {
        "bm25": None, "chunks": [], "guidelines": gl,
        "structured": [], "files": [],
    })
    out = triage_guidelines("anemia cholesterol", k_per_domain=1, k_total=1)
    assert out == ["anemia guideline chunk"]


def test_run_chat_falls_back_on_empty_ctx(monkeypatch):
    calls = []

    def fake_retrieve(query, k=server.TOP_K):
        calls.append((query, k))
        return []

    monkeypatch.setattr(server, "retrieve", fake_retrieve)
    monkeypatch.setattr(server, "INDEX", {
        "bm25": None, "chunks": [], "guidelines": {},
        "structured": [], "files": [],
    })

    async def _boom(*a, **k):
        raise RuntimeError("stop before LLM")

    async def _drive():
        monkeypatch.setattr(server.httpx, "AsyncClient", _boom)
        server.JOBS["t-fallback"] = {"status": "queued"}
        body = server.ChatIn(question="zzz no such record", history=[])
        await server._run_chat("t-fallback", body)
        del server.JOBS["t-fallback"]

    asyncio.run(_drive())
    assert calls[0][0] == "zzz no such record"
    assert calls[1] == ("health medication result lab test blood", 6)
