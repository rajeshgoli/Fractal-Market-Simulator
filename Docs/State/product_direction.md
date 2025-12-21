# Product Direction

**Last Updated:** December 21, 2025 (PM8)
**Owner:** Product

---

## Current Objective

**Ship reliable, performant swing detection that correctly identifies the valid swings defined in `Docs/Reference/valid_swings.md`.**

---

## Current Phase: User Testing

DAG visualization complete. Now in **active user testing** phase using the Replay View to validate swing detection behavior against real ES data.

**Status:** Testing uncovered leg creation bugs. Fixes in progress.

**Active issues:** See [GitHub Issues](https://github.com/rajeshgoli/Fractal-Market-Simulator/issues) for current bugs. Issues are filed and resolved rapidly during this phase — GitHub is the source of truth.

**Test data:** `test_data/es-5m.csv` at various offsets. Observations captured in `ground_truth/playback_feedback.json`.

---

## Upcoming: Impulsiveness & Spikiness Scores (#241)

**Status:** Epic filed, ready for engineering.

Refines raw `impulse` (points/bars) into two trader-interpretable metrics:

| Metric | Formula | Range | Meaning |
|--------|---------|-------|---------|
| **Impulsiveness** | Percentile rank vs formed legs | 0-100 | How impulsive relative to history |
| **Spikiness** | Moment-based skewness → sigmoid | 0-100 | Spike-driven (>50) vs smooth (<50) |

**Use case:** Impulsive + low-spikiness leg in formation = trend continuation signal.

**Subissues:** #242-#247 (execute sequentially, atomic commit)

---

## Completed: DAG Visualization Mode (#167)

**Status:** Complete. Enables visual validation of DAG algorithm.

| Feature | Status |
|---------|--------|
| Recursive 10% pruning (#185) | Done |
| Per-chart timeframe aggregation (#186) | Done |
| DAG state API, panel, visualization (#168-#172) | Done |
| Incremental playback, pruning, orphans (#179-#182) | Done |

---

## Completed: Previous Phases

- #163 Sibling swing detection — Complete
- #158 DAG-based swing detection — Complete (4.06s for 10K bars)
- #159 Reference layer — Complete

---

## Valid Swings Detection Status

From `Docs/Reference/valid_swings.md` — ES as of Dec 18, 2025:

| Label | Structure | Status |
|-------|-----------|--------|
| **L1** | 1=6166, 0=4832 | Detected |
| **L2** | 1=5837, 0=4832 | Pending validation |
| **L3** | 1=6955, 0=6524 | Detected |
| **L4** | 1=6896, 0=6524 | Pending validation |
| **L5** | 1=6790, 0=6524 | Pending validation |
| **L6** | 1=6929, 0=6771 | Detected |
| **L7** | 1=6882, 0=6770 | Pending validation |

Full validation blocked until current leg creation bugs are fixed.

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| <5s for 10K bars | Done (#158) |
| 100K window loads in frontend | Done (#158) |
| Valid swings (L1-L7) detected | Blocked by open issues |
| Sibling swings with same 0 detected | Blocked by open issues |
| Parent-child relationships correct | Done (#158) |
| Visual validation of DAG behavior | Done (#167) |
| Multi-timeframe chart view | Done (#186) |

---

## Checkpoint Trigger

**Invoke Product when:**
- All open leg creation bugs fixed
- L1-L7 validation complete
- Unexpected detection behavior observed during testing

---

## Previous Phase (Archived)

- #185, #186 DAG refinements — Complete
- #167 DAG visualization epic — Complete
