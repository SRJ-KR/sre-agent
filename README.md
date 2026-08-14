# 🚨 ReAct SRE Agent — RAG-Grounded, Safety-Guarded Incident Remediation

A **ReAct (Reason + Act) SRE AI agent** that receives infrastructure alerts and autonomously **resolves or escalates** them, grounded by a **dual-path RAG pipeline** (historical incidents + Git playbooks), an **episodic memory**, and a strict set of **runtime safety guardrails** — with a full **10+ metric evaluation framework** including LLM-as-a-Judge faithfulness and API cost tracking.

Built with **OpenAI function calling (gpt-4o-mini)**, **FAISS**, **Sentence Transformers**, and **SQLite**.

---

## ✨ Highlights

- **Dual-path RAG** — retrieves both past incident records (strategy) and playbook chunks (exact CLI commands), with **tiered metadata pre-filtering** and rebalanced scoring.
- **Safety-first agent** — incidents can only end via an explicit `finish_incident` tool; `resolved` is **validated at runtime** (remediation + dependency verification + healthy target + no rollback).
- **Corrective rejections** — the runtime rejects unsafe or incomplete actions with repair instructions instead of silently failing.
- **Episodic memory** — SQLite-backed, **outcome-aware** (escalated/failed runs are never reused as templates), recency-decayed recall.
- **Evidence grounding** — remediation actions must be **verbatim** copies of retrieved commands; citations are **validated against retrieval** for explainability.
- **Unified evaluation** — execution, safety, retrieval-quality, faithfulness (LLM judge), explainability, and **cost metrics**, persisted per-run to JSONL/JSON.

---

## 🏗️ Architecture

```
data/raw/
  synthetic_training_sre_alerts.csv      playbooks.zip
        │                                      │
        └────────── data_processing.py ────────┘
                          │  parse CSV + chunk Markdown playbooks
                          ▼
                 storage/chunks.json
                          │  vector_store.py (Sentence-Transformers + FAISS)
                          ▼
            faiss.index + meta_store.pkl
                          │
 generate_ground_truth.py ─▶ data/raw/test_against.csv   (seeded, labeled)
                          │
                          ▼
        retriever.py — Dual-Path Retrieval (tiered metadata filters)
                          │
        memory.py — Episodic Memory (SQLite, success-only recall)
                          │
        agent.py — ReAct Loop + Runtime Safety Guard (OpenAI tools)
                          │
        main-eval.py — Unified Evaluation + Persistence + Dashboard
```

### Agent tool set

| Tool | Purpose |
|---|---|
| `check_service_health` | Inspect target or dependency health |
| `trigger_remediation` | Execute a remediation action (max **2** per incident, verbatim from evidence) |
| `verify_service_state` | Post-action blast-radius verification (`scope=dependencies`) |
| `package_escalation` | Hand off to a human engineer with reason + blast-radius map |
| `finish_incident` | **Only** termination path; `resolved` validated by the runtime guard |

### Retrieval scoring (calibrated)

```
final_score = 0.55·cosine + 0.30·service_match + 0.15·severity_match
            + 0.10  (playbooks only, if tech-domain matches)
```

Selection is **tiered**: exact-service CSV and domain-matched playbooks first, similarity backfill second.

---

## 📁 Repository Layout

```
.
├── config.py                  # paths, models, thresholds, logging
├── generate_ground_truth.py   # seeded ground-truth test set generator
├── main-eval.py               # unified evaluation pipeline (CLI flags: --sample, --seed, --verbose)
├── requirements.txt
├── .env                       # OPENAI_API_KEY (not committed)
├── data/
│   ├── raw/                   # synthetic_training_sre_alerts.csv, playbooks.zip, test_against.csv
│   └── processed/playbooks/   # extracted playbook Markdown
├── storage/                   # chunks.json, faiss.index, meta_store.pkl,
│                              # episodes.db, evaluation_results.jsonl,
│                              # evaluation_summary.json, agent_run.log
└── src/
    ├── data_processing.py     # CSV parsing + playbook chunking
    ├── vector_store.py        # embedding + FAISS index build
    ├── retriever.py           # calibrated dual-path retriever
    ├── memory.py              # episodic memory (SQLite)
    └── agent.py               # ReAct agent + mock state engine + guards
```

---

## 🛡️ Safety Guardrails

1. **No implicit termination** — a plain-text reply never resolves an incident; only `finish_incident` ends the loop.
2. **Validated resolution** — `resolved` requires: remediation executed **and** dependency verification performed **and** target healthy **and** no rollback applied.
3. **Corrective rejection** — `finish(resolved)` missing verification is rejected with a repair instruction (verify, then retry).
4. **Remediation cap** — at most 2 remediation actions per incident; excess calls are rejected.
5. **Low-confidence bypass** — retrieval below threshold escalates immediately with a properly packaged reason.
6. **Blast-radius enforcement** — degraded dependencies trigger automatic rollback and forced escalation.
7. **Contamination-proof memory** — episodes with rollback + claimed success get weight 0; only validated successes are recalled.
8. **Grounded actions** — actions must be verbatim AVAILABLE COMMANDS or word-for-word evidence sentences.
9. **Citation requirement** — every thought must cite retrieved evidence IDs (`[INC-x]`, `[PLAYBOOK-x]`).
10. **Deterministic simulation** — the mock state engine is seeded per alert ID for reproducible evaluations.

---

## 📊 Evaluation Framework

| Group | Metrics |
|---|---|
| **Execution** | Success rate, step efficiency, escalation compliance |
| **Safety** | Contamination blocks, resolved-without-verification |
| **Explainability** | Validated evidence citations (cited IDs checked against retrieval) |
| **Faithfulness** | LLM-as-a-Judge over all retrieved evidence (judgeable runs only) |
| **Retrieval** | Precision@k, Recall@k, MRR, Novelty (Jaccard) |
| **Cost** | API calls, prompt/completion/total tokens, estimated USD |

Results persist to `storage/evaluation_results.jsonl` and `storage/evaluation_summary.json`.

### Measured progress (5-alert ground-truth batch, gpt-4o-mini)

| Stage | Success | Steps | Explain. | Faithful. | Prec@k | Recall@k | MRR | Cost |
|---|---|---|---|---|---|---|---|---|
| Baseline | 80–100% | 6.6 | 0% | 0–40% | 28% | 56.7% | 0.90 | – |
| Unified eval | 80% | 6.6 | 0% | 40% | 28% | 56.7% | 0.90 | $0.0062 |
| Agent guardrails v1 | 80% | 7.4 | 0% | 40% | 28% | 56.7% | 0.90 | $0.0087 |
| **Grounding + memory + eval v2** | 80% | **4.0** | **100%** | **100%** | 28% | **100%** | 0.90 | **$0.0049** |
| + Corrective rejection | →100% (exp.) | ~5 | 100% | 100% | 28% | 100% | 0.90 | ~$0.005 |
| + Calibrated retriever | – | – | – | – | →80–100% (exp.) | – | – | – |

**Safety invariants held in every version:** 0 contamination, 0 resolved-without-verification.

---

## 🚀 Quickstart

### 1. Install

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
echo "OPENAI_API_KEY=sk-..." > .env
```

`requirements.txt`:

```
openai
sentence-transformers
faiss-cpu
pandas
numpy
python-dotenv
tqdm
```

### 2. Add data

Place `synthetic_training_sre_alerts.csv` and `playbooks.zip` in `data/raw/`.

### 3. Run

```bash
# Generate the seeded ground-truth test set (first time only)
python generate_ground_truth.py

# Full-batch evaluation (builds index automatically on first run)
python main-eval.py

# Quick seeded smoke test with full traces
python main-eval.py --sample 5 --seed 42 --verbose
```

---

## ⚙️ Configuration Knobs (`config.py`)

| Knob | Default | Effect |
|---|---|---|
| `RETRIEVAL_CONFIDENCE_THRESHOLD` | 0.72 | Below this blended score → immediate escalation |
| `MAX_AGENT_STEPS` | 8 | Hard cap on ReAct loop |
| `EMBEDDING_MODEL_NAME` | `ibm-granite/granite-embedding-english-r2` | Embedding model (CPU) |
| `OPENAI_MODEL_NAME` | `gpt-4o-mini` | Agent + judge model |
| `NUM_TEST_SAMPLES` / `RANDOM_SEED` | 5 / 42 | Ground-truth generation |

---

## 🧾 Project Evolution (Changelog)

- **M0 — Baseline:** dual-path RAG + ReAct agent + two overlapping eval scripts; audit revealed syntax bugs, unsafe auto-resolution, broken faithfulness judge, disconnected cost tracking, memory contamination.
- **M1 — Eval unification:** merged eval scripts; judgeable-only faithfulness; wired cost tracking; seeded sampling; result persistence.
- **M2 — Agent safety v1:** `finish_incident` + runtime resolution guard; cleaned schemas/dependency graph; verbatim-command grounding.
- **M3 — Behavior + memory v2:** remediation cap, citation enforcement, max-steps fallback; explainability via validated citations; faithfulness over all evidence; outcome-aware episodic memory.
- **M4 — Corrective rejection:** missing-verification finishes rejected with repair instructions; anti-escalation prompt rules.
- **M5 — Retrieval calibration:** tiered metadata pre-filtering; rebalanced weights; conditional domain boost.

---

## ⚠️ Limitations & Future Work

- Environment is a **deterministic mock state engine** (synthetic data); real tool integration is future work.
- Ground truth labels whole playbook domains as relevant; finer-grained labels would sharpen precision/recall.
- Planned: hybrid BM25 + dense retrieval, threshold calibration experiments, command-aware chunking, richer dependency graphs.

---

*Built iteratively with eval-driven development: every metric regression was diagnosed via traces before code changes, and safety was never traded for success rate.*
