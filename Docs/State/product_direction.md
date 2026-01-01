# Product Direction

**Last Updated:** January 1, 2026
**Owner:** Product

---

## Current Objective

**Reference Layer exploration + Outcome Layer definition.**

---

## Current Phase: Exploration & Rule Discovery

P1-P4 Reference Layer is **complete**. Foundation enables:
- Level formation/breach observation in real-time
- Confluence zone visualization
- Level crossing event tracking
- Structure panel with touched/active/current levels

**Two parallel tracks:**

| Track | Purpose | Status |
|-------|---------|--------|
| Reference Layer Exploration | Tune salience formula empirically | Ready — needs tuning UI |
| Outcome Layer | Rule discovery: P(outcome \| features) | Draft — needs interview |

---

## Reference Layer Exploration

**Spec:** `Docs/Working/reference_layer_exploration.md`

Reference Layer is the exploration ground for salience formulas — same pattern as DAG layer with pruning algorithms. Wire up multiple approaches, tune empirically, see what works.

**Exploration areas:**
- Salience weights (range/impulse/recency per scale)
- Formation thresholds and breach tolerances
- Structural importance: `counter_leg_range × leg_range`
- Other formulas TBD through experimentation

**Enabler:** Reference Layer tuning UI (expose ReferenceConfig like DetectionConfig)

---

## Outcome Layer Definition

**Spec:** `Docs/Working/outcome_layer_spec.md` (draft — needs interview)

New layer for rule discovery, downstream of Reference Layer:
- Touch detection (what "price touched level" means)
- Outcome labeling (bounce vs breakout vs continuation)
- Feature extraction (structural importance, scale, location, confluence)
- Statistical model: P(outcome | features)

**Open questions requiring user input:**
- Touch definition (wick vs close, tolerance band)
- Outcome definition (bounce magnitude, lookforward window)
- Feature prioritization
- Validation approach

---

## Completed: Reference Layer (Jan 1, 2026)

**Status:** Complete (all 4 phases — backend + frontend).

| Phase | Backend | Frontend |
|-------|---------|----------|
| P1: Core + Levels at Play | ✅ Complete | ✅ Complete |
| P2: Fib Level Interaction | ✅ Complete | ✅ Complete |
| P3: Structure Panel + Confluence | ✅ Complete | ✅ Complete (#420) |
| P4: Level Crossing | ✅ Complete | ✅ Complete (#421) |

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
| <5s for 10K bars | ✅ Done (#158) |
| 100K window loads in frontend | ✅ Done (#158) |
| Valid swings (L1-L7) detected | ✅ Done (Dec 25) |
| Reference Layer filters valid references | ✅ Done (#361-#387) |
| Reference Layer observability | ✅ Done (#400-#414) |
| Structure Panel shows level touches | ✅ Done (#420) |
| Confluence zones render on chart | ✅ Done (#421) |
| Reference Layer tuning UI | **Next** |
| Salience formula validated empirically | **Next** |
| Outcome Layer touch detection | **Next** |
| Rule discovery statistics | **Future** |

---

## Roadmap

1. ✅ **P1: Reference Layer Core** — Complete
2. ✅ **P2: Fib Level Interaction** — Complete
3. ✅ **P3: Structure Panel + Confluence** — Complete (#420)
4. ✅ **P4: Level Crossing** — Complete (#421)
5. ⏳ **Reference Layer Exploration** — Tuning UI + salience formula experiments
6. ⏳ **Outcome Layer** — Rule discovery (parallel with #5)

---

## Checkpoint Trigger

**Invoke Product when:**
- Reference Layer tuning reveals unexpected behavior
- Outcome Layer definition needs user input (interview required)
- Direction uncertainty requiring user values
- Ready to validate salience formula empirically
