# Product Direction

**Last Updated:** January 1, 2026
**Owner:** Product

---

## Current Objective

**Complete P3/P4 frontend work (#419), then Reference Layer exploration.**

---

## Current Phase: P3/P4 Frontend Completion

Reference Layer backend is complete. Frontend gaps identified and filed as #419.

**Active epic:** #419 (2 sub-issues: #420, #421)

| Sub-Issue | Scope | Status |
|-----------|-------|--------|
| #420 | Structure Panel + Telemetry Events | Pending |
| #421 | Confluence Zones + Track Button | Pending |

**What's missing:**
- Structure Panel UI (touched/active/current sections)
- Confluence zones on chart (thicker bands)
- Telemetry recent events section
- Track button on legs

---

## Next Phase: Reference Layer Exploration

**Spec:** `Docs/Working/reference_layer_exploration.md`

Reference Layer is the exploration ground for salience formulas — same pattern as DAG layer with pruning algorithms. Wire up multiple approaches, tune empirically, see what works.

**Exploration areas:**
- Salience weights (range/impulse/recency per scale)
- Formation thresholds and breach tolerances
- Structural importance: `counter_leg_range × leg_range`
- Other formulas TBD through experimentation

**Enabler:** Reference Layer tuning UI (expose ReferenceConfig like DetectionConfig)

---

## Parallel: Outcome Layer Definition

**Spec:** `Docs/Working/outcome_layer_spec.md` (draft)

New layer for rule discovery, downstream of Reference Layer:
- Touch detection (what "price touched level" means)
- Outcome labeling (bounce vs breakout vs continuation)
- Feature extraction (structural importance, scale, location, confluence)
- Statistical model: P(outcome | features)

Architecture not finalized — will iterate as Reference Layer exploration progresses.

---

## Completed: Reference Layer Backend (Jan 1, 2026)

**Status:** Complete. P3+P4 backend implemented, frontend partial.

| Phase | Backend | Frontend |
|-------|---------|----------|
| P1: Core + Levels at Play | Complete | Complete |
| P2: Fib Level Interaction | Complete | Complete |
| P3: Structure Panel + Confluence | Complete | **Partial** |
| P4: Level Crossing | Complete | **Partial** |

Backend APIs exist but aren't wired to UI:
- `/api/reference/structure` — Not called
- `/api/reference/confluence` — Not called
- `/api/reference/telemetry` — Events section missing

---

## Completed: Previous Phases

- #400-#414 Reference Observation + Cleanup — Complete
- #361-#387 Reference Layer Phase 1 — Complete
- #388-#393 Reference Layer Phase 2 (Fib Interaction) — Complete
- #347-#349 Turn ratio UX, inner structure removal, frontend cleanup — Complete
- #324 Self-contained playback — Complete
- #250 Hierarchy exploration mode — Complete
- #241 Impulsiveness & spikiness scores — Complete
- #167 DAG visualization mode — Complete
- #163 Sibling swing detection — Complete
- #158 DAG-based swing detection — Complete (4.06s for 10K bars)

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| <5s for 10K bars | Done (#158) |
| 100K window loads in frontend | Done (#158) |
| Valid swings (L1-L7) detected | Done (Dec 25) |
| Reference Layer filters valid references | Done (#361-#387) |
| Reference Layer observability | Done (#400-#414) |
| Structure Panel shows level touches | **Pending** (#420) |
| Confluence zones render on chart | **Pending** (#421) |
| Reference Layer tuning UI | **Pending** |
| Salience formula validated empirically | **Pending** |
| Outcome Layer touch detection | **Future** |
| Rule discovery statistics | **Future** |

---

## Roadmap

1. ✅ **P1: Reference Layer Core** — Complete
2. ✅ **P2: Fib Level Interaction** — Complete
3. ⚠️ **P3: Structure Panel + Confluence** — Backend done, frontend pending (#419)
4. ⚠️ **P4: Level Crossing** — Backend done, frontend pending (#419)
5. ⏳ **Reference Layer Exploration** — Tuning UI + salience formula experiments
6. ⏳ **Outcome Layer** — Rule discovery (parallel with #5)

---

## Checkpoint Trigger

**Invoke Product when:**
- #419 epic complete
- Reference Layer tuning reveals unexpected behavior
- Outcome Layer definition needs user input
- Direction uncertainty requiring user values
