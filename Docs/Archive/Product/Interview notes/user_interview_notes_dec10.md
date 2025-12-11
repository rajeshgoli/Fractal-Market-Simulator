# User Interview Notes: Product Direction Sync

**Date:** December 10, 2025
**Interviewer:** Product Manager (Claude)
**Interviewee:** Rajesh (Project Owner / Domain Expert)
**Context:** Product sync following architect's completion of Swing Visualization Harness

---

## Background

Following completion of the Swing Visualization Harness phase, the project architect proposed transitioning to Market Data Generator development with 5 major product decisions requiring resolution. This interview clarified the user's actual priorities and corrected scope misalignment.

---

## Key Clarifications from User

### Immediate Goal Reframing

**User Position:** Primary objective is **validation of swing detection logic on historical data**, not generation of new market data.

**Specific Requirements:**
- Load existing historical OHLC datasets (1m, 5m, 1d resolution) from project folder
- Support user-specified start and end date ranges for analysis
- Visual validation of swing detection behavior on real market history
- Focus on reference swing detection, level generation, move detection, and closure logic

**Explicit Out of Scope:** Market data generation until foundation is validated

### Priority and Scope Correction

**User Feedback:** Architect's framing jumped ahead to generator decisions prematurely.

**Core Concern:** "The hard problem here is not UI or breadth, but correctness and robustness of the structural logic."

**Risk Assessment:** Layering additional complexity before core mechanics validation creates more risk than value.

### Validation Approach Preference

**Primary Mechanism:** Visual validation through expert review
- Replay historical data with swing annotations across four synchronized views
- Rapid sanity-checking of system interpretation versus expert market intuition
- Statistical validation and quantitative metrics deferred until basic logic validation complete

**Rationale:** Statistical metrics would provide false confidence before knowing if basic logic works correctly.

### Timeline and Gating Philosophy

**User Position:** Progress should be gated by correctness, not calendar estimates.

**Completion Criteria:** Visual validation phase complete when swing detection, level generation, move detection, and closure logic behave correctly across variety of historical regimes and edge cases.

**Expected Iteration:** At least one cycle of bug fixes and refinements after initial validation findings.

---

## Strategic Direction Confirmed

### Immediate Next Phase: Historical Data Validation
1. Configure harness to load historical datasets with date range specification
2. Systematic visual validation of core detection logic
3. Identification and documentation of bugs, edge cases, enhancement needs
4. Iterative refinement until expert confidence achieved

### Future Phase Gating
- **Generator development** explicitly deferred until validation and refinement cycles complete
- Reconvene for scope decisions only after core structural engine proven robust
- Next discussion should focus on stochastic rule design and generation **after** foundation is solid

---

## Implementation Implications

### Technical Scope
- Leverage existing harness infrastructure for historical data replay
- Maintain four-scale synchronized visualization architecture
- Add date range configuration capability
- Preserve all existing event detection and annotation features

### Success Criteria
- Expert can confidently rely on system's structural analysis
- Detection logic behaves sensibly across diverse market regimes
- All significant issues identified and catalogued for resolution
- Foundation ready for behavioral modeling work

---

## Key Quotes

"My primary objective right now is not to validate generated data, but to validate swing detection and related logic on historical data."

"The hard problem here is not UI or breadth, but correctness and robustness of the structural logic."

"I don't think it's useful to talk about durations yet. Progress should be gated by correctness, not by calendar estimates."

"The project needs a sharper focus on validating the core structural engine using historical data before expanding scope."

---

## Outcome

**Agreed Direction:** Swing Detection Validation Phase using historical data
**Market Data Generation:** Explicitly out of scope until foundation validated
**Progress Gating:** Correctness-based, not timeline-based
**Next Action:** Configure harness for historical data loading and begin systematic validation