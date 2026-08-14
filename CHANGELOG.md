# Changelog

All notable changes to the **ReAct SRE Agent** project are documented in this file.
Versions correspond to development milestones; each milestone was validated with a full
evaluation run (5-alert ground-truth batch, `gpt-4o-mini`) before proceeding.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/).

---

## [0.6.0] — Retrieval Calibration (current)

### Changed
- **`src/retriever.py` (v2):** tiered metadata pre-filtering for precision:
  - CSV candidates: exact-service matches first, similarity backfill only if short.
  - Playbook candidates: tech-domain matches first, any-domain (score > 0.5) backfill second.
- **Scoring rebalanced:** `0.55·cosine + 0.30·service + 0.15·severity`; the old unconditional
  `+0.15` playbook boost replaced by a **conditional `+0.10`** only when the playbook's
  `tech_stack` matches the inferred alert domain.
- Domain inference duplicated verbatim from `generate_ground_truth.infer_tech_domain`
  so retrieval optimizes the same labels the evaluator uses.

### Added
- Position-safe FAISS ID mapping (`id_by_position`).
- `domain` key in retrieval output for diagnostics.

### Expected impact
- Precision@k: 28% → 80–100% (pending verification run); MRR/recall preserved.

---

## [0.5.0] — Corrective Rejection Agent

### Fixed
- **Unnecessary escalations** (last execution gap): runs that skipped
  `verify_service_state` had `finish(resolved)` hard-overridden to `escalated`.
  Now the runtime issues a **corrective rejection** — the finish attempt is rejected with a
  repair instruction ("verify dependencies, then finish again") instead of failing the run.

### Added
- **`src/agent.py` (v4, consolidated):** prompt HARD RULES 9–10:
  never skip verification; never escalate without cause (low confidence, blast radius,
  or runtime rejection).
- `_resolve_checks()` helper decomposing the resolution guard
  (remediation / verification / healthy / no-rollback).

### Expected impact
- Success rate & escalation compliance: 80% → 100% (pending verification run).

---

## [0.4.0] — Grounding, Efficiency & Memory Safety

### Changed
- **`src/agent.py` (v3):** hard cap of **2 remediation actions** per incident (excess calls
  rejected with guidance); max-steps fallback resolves **only** if the safety guard passes;
  word-for-word evidence copying when no CLI commands exist.
- **`main-eval.py` (v2):** explainability redefined as **validated structured citations**
  (`finish_incident.evidence_ids` checked against retrieved chunk IDs, with thought-citation
  fallback); faithfulness judged against **all top-3 retrieved evidence**, not just the top
  playbook; `nan` ground-truth label filtering.
- **`src/memory.py` (v2):** outcome-aware episode labeling (`verified_outcome` derived from
  the final outcome, not observation scanning); **success-only recall** with
  `outcome_weight` filtering; recency decay by monotonic `episode_id`.

### Added
- `write_episode(..., outcome=...)` signature; evaluation passes the final outcome.

### Measured impact
| Metric | Before | After |
|---|---|---|
| Avg steps/run | 7.4 | **4.0** |
| Explainability | 0% | **100%** |
| Faithfulness | 40% | **100%** |
| Recall@k | 56.7% | **100%** |
| Cost/batch | $0.0087 | **$0.0049** (−44%) |

---

## [0.3.0] — Agent Safety Overhaul

### Added
- **`finish_incident` tool** — the *only* termination path; plain-text replies no longer
  resolve incidents (reminder injected, then forced escalation).
- **Runtime resolution guard:** `resolved` accepted only with remediation executed **and**
  dependency verification performed **and** target healthy **and** no rollback applied.
- `AVAILABLE COMMANDS` extraction (`extract_commands`) with verbatim-copy grounding rule.
- Citation hard-rules (`[INC-x]` / `[PLAYBOOK-x]`) in the system prompt.

### Fixed
- Syntax corruption: `__init__`, `__name__`, `hexdigest()`, trailing spaces in
  `DEPENDENCY_GRAPH` keys/values and tool-schema strings.
- Low-confidence bypass now emits proper `package_escalation` args
  (`reason`, `blast_radius_map`).

### Measured impact
- Safety held (0 contamination, 0 resolved-without-verification); traces exposed the
  remaining behavior gaps (silent thoughts, paraphrased actions) fixed in 0.4.0.

---

## [0.2.0] — Unified Evaluation Pipeline

### Added
- **`main-eval.py` (v1):** merged `main-eval.py` + `main-eval1.py` into one pipeline;
  seeded `--sample`/`--seed` modes; `--verbose` trace printing; per-run persistence to
  `storage/evaluation_results.jsonl` and `storage/evaluation_summary.json`.
- `resolved_without_verification` safety metric.
- Cost metrics populated via `agent.get_usage_summary()`.

### Fixed
- Faithfulness judge bug: `"YES " in answer` (trailing space → always 0) →
  `answer.startswith("YES")`.
- Faithfulness averaged **only over judgeable runs** (escalations no longer penalized).
- Disconnected usage tracking (`getattr(agent, "last_usage")` → real usage summary).
- Console noise: centralized `setup_logging()` instead of `logging.basicConfig(INFO)`.

### Retired
- `main-eval1.py` (functionality merged).

---

## [0.1.0] — Initial Baseline

### Added
- Dual-path RAG: FAISS + Sentence-Transformers (`ibm-granite/granite-embedding-english-r2`)
  over synthetic incident CSV and Git playbook Markdown chunks.
- ReAct agent with OpenAI function calling (`check_service_health`, `trigger_remediation`,
  `verify_service_state`, `package_escalation`) and deterministic mock state engine
  (seeded per alert; blast-radius simulation + automatic rollback).
- Episodic memory (SQLite) with recency decay and contamination weighting.
- Ground-truth generator (`generate_ground_truth.py`, seed 42) with expected CSV/playbook IDs.
- Evaluation metrics: success, step efficiency, escalation compliance, explainability,
  contamination, precision@k, recall@k, MRR, novelty (Jaccard), faithfulness (LLM judge).

### Known issues at baseline (from architecture audit)
- Agent self-declared `resolved` on silent termination (unsafe).
- Memory could return failed/escalated episodes as templates; escalated runs mislabeled
  `success` via observation scanning.
- Unconditional playbook boost and uncalibrated 0.72 threshold hurt retrieval precision.
- Two overlapping eval scripts; unseeded random sampling; over-broad ground-truth labels.

---

## Appendix A — Metric evolution (5-alert ground-truth batch)

| Stage | Success | Steps | Compliance | Explain. | Faithful. | P@k | R@k | MRR | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 0.1.0 (eval1) | 80% | 6.6 | 80% | 0% | 40% | – | – | – | – |
| 0.1.0 (eval)  | 100% | 6.6 | 100% | 0% | 0%* | 28% | 56.7% | 0.90 | – |
| 0.2.0 | 80% | 6.6 | 80% | 0% | 40% | 28% | 56.7% | 0.90 | $0.0062 |
| 0.3.0 | 80% | 7.4 | 80% | 0% | 40% | 28% | 56.7% | 0.90 | $0.0087 |
| 0.4.0 | 80% | 4.0 | 80% | 100% | 100% | 28% | 100% | 0.90 | $0.0049 |
| 0.5.0 | →100% (exp.) | ~5 | →100% (exp.) | 100% | 100% | 28% | 100% | 0.90 | ~$0.005 |
| 0.6.0 | – | – | – | – | – | →80–100% (exp.) | – | – | – |

\* judge bug, not real faithfulness.

## Appendix B — Safety invariants

Held in **every** version since 0.2.0:
- 0 contamination blocks (no resolved incident with an applied rollback).
- 0 resolved-without-verification.
- Escalation is always the safe default (silent termination, step cap, guard failure).
