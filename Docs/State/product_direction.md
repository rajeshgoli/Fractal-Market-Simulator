# Product Direction

**Last Updated:** January 1, 2026
**Owner:** Product

---

## Current Objective

**Complete P3/P4 frontend work (#419).**

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

## Completed: Reference Observation + Cleanup (Jan 1, 2026)

**Status:** Complete. Observation mode + architectural cleanup (15 issues, #400-#414).

| Component | Status |
|-----------|--------|
| Filter status API (FilterReason, FilteredLeg) | Complete |
| Show Filtered toggle + explanation panel | Complete |
| UX inversion (filtered highlighted, valid faded) | Complete |
| Lazy DAG init (removed CalibrationPhase) | Complete |
| API namespace restructure (/dag/*, /reference/*) | Complete |
| Cache consolidation (single cache.py) | Complete |
| Dead code removal (replay mode, SWING_* events) | Complete |
| View renamed: DAG View → Structural Legs | Complete |

---

## Completed: Previous Phases

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

---

## Roadmap

1. ✅ **P1: Reference Layer Core** — Complete
2. ✅ **P2: Fib Level Interaction** — Complete
3. ⚠️ **P3: Structure Panel + Confluence** — Backend done, frontend pending (#419)
4. ⚠️ **P4: Level Crossing** — Backend done, frontend pending (#419)
5. ⏳ **Next:** Complete #419, then outcome tracking / rule discovery

---

## Checkpoint Trigger

**Invoke Product when:**
- #419 epic complete
- Unexpected behavior observed during testing
- Direction uncertainty requiring user values
