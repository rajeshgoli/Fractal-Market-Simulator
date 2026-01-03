# Product Direction

**Last Updated:** January 3, 2026
**Owner:** Product

---

## Current Objective

**Multi-tenant demo deployment.**

---

## Current Phase: Foundation & Shareability

Reference Layer (P1-P4) is **complete**. Product is working beautifully — legs and Fibonacci levels render correctly, playback works as envisioned.

**Next: Build concrete foundations before exploratory work.**

---

## Roadmap

| # | Track | Rationale | Status |
|---|-------|-----------|--------|
| 1 | **Multi-tenant demo** | Quick win — working app to keep and share | **Next** |
| 2 | **Impulse rework** | Technical foundation — infra exists to validate | Queued |
| 3 | **Outcome Layer** | Statistical grounding — ground intuitions with data | Queued |
| 4 | **Fractal narrative** | Exploratory UX — build on solid foundation | Future |

**Philosophy:** Concrete → Foundation → Grounding → Exploration

---

## Track 1: Multi-tenant Demo

**Status:** Interview in progress

Minimal multi-tenant capability to host a shareable demo:
- Session ID + per-user caching
- Fixed backtest data (ES 30-minute)
- Google OAuth (minimal auth)
- CI/CD: push to main → deployed
- User's domain

**Goal:** Portfolio piece — live demo to point to.

---

## Track 2: Impulse Rework

**Status:** Queued (after multi-tenant)

Current impulse detection in DAG needs improvement. Infrastructure exists to visualize and validate. Enhances downstream features (fractal visualization, outcome layer).

---

## Track 3: Outcome Layer

**Status:** Queued (after impulse)
**Spec:** `Docs/Working/outcome_layer_spec.md` (draft)

Statistical foundation for rule discovery:
- Touch detection (what "price touched level" means)
- Outcome labeling (bounce vs breakout vs continuation)
- Feature extraction (structural importance, scale, location, confluence)
- Statistical model: P(outcome | features)

**Purpose:** Ground intuitions about trading rules with data before building narrative UX.

---

## Track 4: Fractal Narrative

**Status:** Future (after outcome layer)

The "stepping stones" visualization — showing how parent targets are reached through cascading child structures. Requires:
- Statistical grounding (Track 3) to know what's worth showing
- Better impulse detection (Track 2) to identify meaningful structures
- UX exploration to handle visual clutter constraint

---

## Completed: Reference Layer (Jan 1, 2026)

**Status:** Complete (all 4 phases).

| Phase | Status |
|-------|--------|
| P1: Core + Levels at Play | Complete |
| P2: Fib Level Interaction | Complete |
| P3: Structure Panel + Confluence | Complete (#420) |
| P4: Level Crossing | Complete (#421) |

---

## Completed: Previous Phases

- #400-#414 Reference Observation + Cleanup
- #361-#387 Reference Layer Phase 1
- #388-#393 Reference Layer Phase 2 (Fib Interaction)
- #347-#349 Turn ratio UX, inner structure removal, frontend cleanup
- #324 Self-contained playback
- #250 Hierarchy exploration mode
- #241 Impulsiveness & spikiness scores
- #167 DAG visualization mode
- #163 Sibling swing detection
- #158 DAG-based swing detection (4.06s for 10K bars)

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| <5s for 10K bars | Done (#158) |
| 100K window loads in frontend | Done (#158) |
| Valid swings (L1-L7) detected | Done (Dec 25) |
| Reference Layer filters valid references | Done (#361-#387) |
| Reference Layer observability | Done (#400-#414) |
| Structure Panel shows level touches | Done (#420) |
| Multi-tenant demo deployed | **Next** |
| Impulse detection improved | Queued |
| Outcome Layer statistics | Queued |
| Fractal narrative UX | Future |

---

## Checkpoint Trigger

**Invoke Product when:**
- Multi-tenant scope needs clarification
- Impulse rework reveals design questions
- Outcome Layer definition needs user input
- Ready to begin fractal narrative exploration
