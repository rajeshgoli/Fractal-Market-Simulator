# Resolved Questions

---

## Q1: Stale CLI Path References Need Cleanup

**From:** Product
**To:** Architect
**Status:** Resolved
**Date:** 2024-12-11

**Question:** Stale `src.cli.main` references in CLAUDE.md, src/data/loader.py, and Docs/State/architect_notes.md need cleanup. Should these be updated to `src.visualization_harness.main`, or is there a planned CLI restructuring?

**Resolution (Architect):** **Updated all stale references.** No CLI restructuring is planned.

Investigation confirmed:
- `src/cli/` directory does not exist and never existed
- All CLI functionality lives in `src/visualization_harness/` (main.py, harness.py)
- References to `src.cli.main` were incorrect documentation artifacts

**Files updated:**
| File | Change |
|------|--------|
| `src/data/loader.py:404,434` | Updated error message CLI commands |
| `src/visualization_harness/harness.py:8-10` | Updated docstring usage examples |
| `CLAUDE.md:116-193` | Restructured Core Components to match actual directory layout |
| `Docs/State/architect_notes.md:56-57` | Updated validation commands |

**Additional cleanup:**
- Consolidated 6 fake directories (`src/analysis/`, `src/visualization/`, `src/playback/`, `src/logging/`, `src/cli/`, `src/legacy/`) into actual structure (`src/swing_analysis/`, `src/visualization_harness/`, `src/data/`)
- CLAUDE.md architecture section now accurately reflects codebase

---

## Q-2025-12-11-2

**From:** Architect
**To:** Product
**Status:** Resolved
**Date:** December 11, 2025

**Question:** UX decisions for validation refinement - per-scale swing caps and hysteresis

**Resolution (Product):** **Collect during validation, not before.**

These are tuning parameters that should be informed by actual usage:
- Per-scale swing caps (S=5, M=3, L=2, XL=1 vs uniform 5) - Current uniform default is a reasonable starting point
- Hysteresis for dynamic aggregation - Unclear if this is a problem until user experiences rapid switching

**Rationale:** We don't have enough signal to make these decisions ahead of time. Current defaults work. If they cause friction during validation, user will tell us. That's the highest-signal way to tune.

**Action:** No engineering work. Observe during validation sessions and adjust if feedback indicates need.

---

## Q-2025-12-11-1

**From:** Director
**To:** Product
**Status:** Resolved
**Date:** December 11, 2025

**Question:** Should Product have direct tool access via MCP server?

**Resolution (Product):** **Defer.** Wrong timing, wrong problem.

**Reasoning:**

1. **Timing is wrong.** Phase 2 stability nearly complete. Validation sessions imminent. Building MCP infrastructure now would delay the path to the actual goal (generator).

2. **Problem is wrong.** The core validation question is: "Does swing detection match expert market structure intuition?" This requires domain expertise, not automation. Product seeing screenshots cannot substitute for 12 years of market structure experience.

3. **Scope is non-trivial.** CLI execution + screenshot capture + keyboard simulation + output parsing = significant engineering that doesn't advance the generator.

4. **North star alignment.** User stated: "I don't care about visualization other than for debugging." The goal is generating realistic OHLC data, not more harness tooling.

5. **Current workflow works.** User validates → Product interprets feedback → direction updated. The "expensive oracle" model is appropriate here because the oracle has the expertise we actually need.

**If revisited later:** Consider only if validation reveals a pattern where Product needs to triage before User engagement. Even then, a simpler approach (CLI output parsing only, no screenshot/keyboard sim) would likely suffice.

---

## Q-2025-12-11-A

**From:** Product
**To:** Architect
**Status:** Resolved
**Date:** December 11, 2025

**Question:** Pre-compute swing cache vs algorithm rewrite - which is cheaper?

**Resolution:** Architect recommended algorithm rewrite. O(N log N) rewrite was achievable and carries forward to generator phase. Caching would be throwaway work. Algorithm rewrite completed Dec 11.

---

## Q-2025-12-10-A

**From:** Architect
**To:** Product
**Status:** Resolved
**Date:** December 10, 2025

**Question:** Ready to proceed to Market Data Generator phase?

**Resolution:** No. User clarified in interview that validation on historical data must complete first. Generator phase explicitly deferred.
