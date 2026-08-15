# -*- coding: utf-8 -*-
"""
AI Agent module: RAG Q&A over the DatabasePDF knowledge base.

Architecture (designed for future extension):
  1. Knowledge-base ingestion ingest(): DatabasePDF/*.pdf -> pdftotext -> chunking -> cache/ai_kb.json
     Adding new sources later (more PDFs / marker-converted markdown / KG triples) only requires extending ingest.
  2. Retrieval Retriever: BM25 (pure CPU, no model download). Can later be swapped for vector retrieval
     (sentence-transformers / OpenAI embeddings) with the same interface: query -> [chunk].
  3. Generation chat(): auto-detects the LLM provider:
       - env var ANTHROPIC_API_KEY  -> Claude
       - env var OPENAI_API_KEY     -> OpenAI
       - backend/ai_config.json     -> {"provider","api_key","model"} manual override
       - none of the above -> falls back to "retrieval mode", returning relevant paper excerpts directly
     The system prompt injects: tool semantics (View1/View2, meaning of render/calibration) +
     current application state (parameter history etc., sent by the frontend with each request) +
     retrieved paper excerpts.
"""

import os
import re
import json
import glob
import hashlib
import subprocess
import logging

import requests
from rank_bm25 import BM25Okapi

HERE = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.join(HERE, "..", "DatabasePDF")
KB_PATH = os.path.join(HERE, "cache", "ai_kb.json")
CONFIG_PATH = os.path.join(HERE, "ai_config.json")

CHUNK_CHARS = 1400     # roughly 300-350 tokens per chunk
CHUNK_OVERLAP = 200
TOP_K = 6

# ---------------------------------------------------------------------------
# 1. Ingestion
# ---------------------------------------------------------------------------

def _pdf_fingerprint():
    """Hash of all PDF paths + mtimes, used to decide whether the knowledge base needs rebuilding"""
    items = []
    for p in sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf"))):
        items.append(f"{os.path.basename(p)}:{os.path.getmtime(p)}")
    return hashlib.md5("|".join(items).encode()).hexdigest()


def _pdf_to_text(path):
    out = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {path}: {out.stderr[:200]}")
    return out.stdout


def _chunk(text, doc):
    """Aggregate paragraphs into ~CHUNK_CHARS chunks with overlap, keeping the source document name"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) > CHUNK_CHARS and buf:
            chunks.append(buf)
            buf = buf[-CHUNK_OVERLAP:] + "\n" + p  # tail overlap
        else:
            buf = (buf + "\n\n" + p) if buf else p
    if buf:
        chunks.append(buf)
    return [{"doc": doc, "id": f"{doc}#{i}", "text": c} for i, c in enumerate(chunks)]


def ingest(force=False):
    """Build/load the knowledge base. Automatically rebuilds when PDFs change."""
    fp = _pdf_fingerprint()
    if not force and os.path.exists(KB_PATH):
        try:
            kb = json.load(open(KB_PATH))
            if kb.get("fingerprint") == fp:
                return kb
        except Exception:
            pass

    chunks = []
    for p in sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf"))):
        doc = os.path.splitext(os.path.basename(p))[0]
        try:
            chunks.extend(_chunk(_pdf_to_text(p), doc))
        except Exception as e:
            logging.error(f"Ingestion failed {p}: {e}")

    kb = {"fingerprint": fp, "chunks": chunks}
    os.makedirs(os.path.dirname(KB_PATH), exist_ok=True)
    json.dump(kb, open(KB_PATH, "w"))
    return kb


# ---------------------------------------------------------------------------
# 2. Retrieval
# ---------------------------------------------------------------------------

def _tokenize(s):
    return re.findall(r"[a-zA-Z0-9]+", s.lower())


class Retriever:
    def __init__(self):
        self.kb = ingest()
        corpus = [_tokenize(c["text"]) for c in self.kb["chunks"]]
        self.bm25 = BM25Okapi(corpus) if corpus else None

    def refresh_if_stale(self):
        if self.kb.get("fingerprint") != _pdf_fingerprint():
            self.__init__()

    def search(self, query, k=TOP_K):
        if not self.bm25:
            return []
        toks = _tokenize(query)
        if not toks:
            return []
        scores = self.bm25.get_scores(toks)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [dict(self.kb["chunks"][i], score=float(scores[i]))
                for i in order if scores[i] > 0]


_retriever = None

def get_retriever():
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    else:
        _retriever.refresh_if_stale()
    return _retriever


# ---------------------------------------------------------------------------
# 3. LLM provider
# ---------------------------------------------------------------------------

def _load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            cfg = json.load(open(CONFIG_PATH))
        except Exception as e:
            logging.error(f"Failed to read ai_config.json: {e}")
    return cfg


def resolve_provider():
    """Return (provider, api_key, model); provider is None when no key is configured"""
    cfg = _load_config()
    if cfg.get("api_key"):
        provider = cfg.get("provider", "anthropic")
        default_model = "claude-sonnet-5" if provider == "anthropic" else "gpt-4o-mini"
        return provider, cfg["api_key"], cfg.get("model", default_model)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", os.environ["ANTHROPIC_API_KEY"], cfg.get("model", "claude-sonnet-5")
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", os.environ["OPENAI_API_KEY"], cfg.get("model", "gpt-4o-mini")
    return None, None, None


SYSTEM_PROMPT = """You are the built-in AI assistant of the "Conformalized Evidential Surrogate \
Exploration Tool", a visualization tool for uncertainty quantification of ensemble-simulation \
surrogate models based on conformalized evidential learning.

Tool semantics (use these when answering questions about the interface):
- Parameters View: choose a dataset (e.g. Nyx) and set simulation parameters (Nyx: OmM/OmB/h); \
Submit creates one history record.
- Visualization View-1: one row per record with three volume renderings = model prediction / \
aleatoric (data) uncertainty / epistemic (model) uncertainty, computed from the deep evidential \
regression (DER) outputs (gamma, v, alpha, beta).
- Visualization View-2: each row has a confidence slider. "render" = the student-t predictive \
interval for that row's parameters at the chosen confidence level (the Predicted Interval view \
shows the width upper-lower; the other two columns are the lower/upper bound volumes). \
"calibration" = conformal calibration of that interval (C = [q_lo - Q_lo, q_hi + Q_hi], where \
Q_lo/Q_hi are empirical quantiles of non-conformity scores on a calibration set), which carries \
a statistical coverage guarantee. Available calibration levels are 0.1/0.2/0.5/0.75/0.9; the \
requested confidence snaps to the nearest level.
- Para-space View (View 3): ROI-based parameter recommendation. The user loads a Context \
Field (OmM/OmB/h), sets a Region of Interest (voxel ranges, shown as an orange box; views can \
be cropped to it), picks a Reference (Pred / uncalibrated lower/upper bound / conformally \
calibrated lower/upper bound, all at the context parameters and current confidence), and \
presses "Recommend Parameters". The backend runs multi-start Adam gradient optimization \
(activation maximization) on the evidential INR surrogate to find parameters whose prediction \
inside the ROI is closest (RMSE, log10 density) to the reference. Candidates report ROI-mean \
aleatoric/epistemic uncertainty and are re-ranked by the user's Maximize/Minimize preferences; \
"Preview" renders a candidate's prediction/uncertainty triple, "Send to View-1/2" hands the \
parameters back to View 1/2 as a new history record. The "Optimize" button on a View-1/2 \
history row hands that row's parameters to View 3 as the Context Field. See the \
"ParaSpace_View3_Documentation" document for details.

Answering rules:
- Answer in English.
- When you cite the reference excerpts, add the source index at the end of the sentence, e.g. [1].
- If the references are insufficient, say so explicitly; never fabricate.
- Use the application state provided below when answering questions about the current interface."""


def _format_context(snippets, app_state):
    parts = []
    if app_state:
        parts.append("## Current application state\n" + json.dumps(app_state, ensure_ascii=False, indent=1))
    if snippets:
        refs = []
        for i, s in enumerate(snippets, 1):
            refs.append(f"[{i}] From \"{s['doc']}\":\n{s['text']}")
        parts.append("## Reference excerpts (retrieved from papers)\n" + "\n\n".join(refs))
    return "\n\n".join(parts)


# Reasoning models spend part of this budget on internal "thinking" blocks before they emit
# any answer text, so it has to cover both. At 3000 a complex state-aware question could burn
# the whole budget while thinking and come back with no text block at all (an empty chat bubble).
MAX_ANSWER_TOKENS = 8000


def _no_text_message(stop_reason):
    if stop_reason == "max_tokens":
        return ("(The model ran out of response budget before producing an answer. Try a more "
                "specific question, or raise MAX_ANSWER_TOKENS in backend/ai_agent.py.)")
    return f"(The model returned no answer text; stop_reason={stop_reason}.)"


def _call_anthropic(api_key, model, system, messages):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": model, "max_tokens": MAX_ANSWER_TOKENS, "system": system,
              "messages": messages},
        timeout=180)
    r.raise_for_status()
    data = r.json()
    # Only "text" blocks are the answer; "thinking" blocks are internal and must not be shown.
    text = "".join(b.get("text", "") for b in data.get("content", [])
                   if b.get("type") == "text")
    return text if text.strip() else _no_text_message(data.get("stop_reason"))


def _call_openai(api_key, model, system, messages):
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model,
              "messages": [{"role": "system", "content": system}] + messages,
              "max_tokens": MAX_ANSWER_TOKENS},
        timeout=180)
    r.raise_for_status()
    choice = r.json()["choices"][0]
    text = choice.get("message", {}).get("content") or ""
    return text if text.strip() else _no_text_message(choice.get("finish_reason"))


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def status():
    provider, _, model = resolve_provider()
    kb = get_retriever().kb
    docs = sorted({c["doc"] for c in kb["chunks"]})
    return {
        "provider": provider,           # null means retrieval mode
        "model": model,
        "kb_docs": docs,
        "kb_chunks": len(kb["chunks"]),
    }


def chat(messages, app_state=None):
    """
    messages: [{role: 'user'|'assistant', content: str}, ...] (the last one is the user question)
    app_state: current UI state sent by the frontend (optional)
    Returns {answer, sources, provider, mode}
    """
    query = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            query = m.get("content", "")
            break

    snippets = get_retriever().search(query)
    sources = [{"index": i + 1, "doc": s["doc"], "text": s["text"][:400]}
               for i, s in enumerate(snippets)]

    provider, api_key, model = resolve_provider()
    if provider is None:
        # Retrieval mode: no LLM key configured, return relevant excerpts
        if snippets:
            answer = ("(Retrieval mode: no LLM API key configured. Below are the most relevant "
                      "excerpts from the knowledge base. To enable full answers, put "
                      "{\"provider\":\"anthropic\",\"api_key\":\"...\"} in backend/ai_config.json, "
                      "or set ANTHROPIC_API_KEY / OPENAI_API_KEY and restart the backend.)\n\n")
            for i, s in enumerate(snippets[:3], 1):
                answer += f"[{i}] {s['doc']}\n{s['text'][:600]}\n\n"
        else:
            answer = ("(Retrieval mode) Nothing relevant found in the knowledge base. It currently "
                      "contains only the three papers under DatabasePDF, and retrieval is keyword-"
                      "based — try including English terms such as calibration, evidential, interval.")
        return {"answer": answer, "sources": sources, "provider": None, "mode": "retrieval"}

    system = SYSTEM_PROMPT + "\n\n" + _format_context(snippets, app_state)
    # Keep only the last 12 messages to control token usage
    trimmed = [{"role": m["role"], "content": m["content"]} for m in messages[-12:]]
    try:
        if provider == "anthropic":
            answer = _call_anthropic(api_key, model, system, trimmed)
        else:
            answer = _call_openai(api_key, model, system, trimmed)
    except requests.HTTPError as e:
        body = e.response.text[:300] if e.response is not None else str(e)
        return {"answer": f"LLM call failed ({provider}/{model}): {body}",
                "sources": sources, "provider": provider, "mode": "error"}
    except Exception as e:
        return {"answer": f"LLM call failed: {e}", "sources": sources,
                "provider": provider, "mode": "error"}

    return {"answer": answer, "sources": sources, "provider": provider, "mode": "llm"}
