# Architecture Simplification Proposal

*Fractal Market Simulator — December 2025*

---

## Problem Statement

This codebase exists to achieve one outcome: financial independence through algorithmic trading, enabling its creator to leave tech and pursue serious contemplative practice. The quality bar is absolute—every function must be trusted completely before real capital touches it.

Currently, the system is **~21,100 lines of code** (10,784 source + 10,338 tests) organized into five modules. My audit reveals **three layers of accumulated complexity**:

| Layer | Scope | LOC | Description |
|-------|-------|-----|-------------|
| **Dead Code** | 3 modules | ~1,400 | Never imported, never executed |
| **Duplication** | 2 files | ~700 | Copy-pasted bull/bear logic, repeated API patterns |
| **Tech Debt** | 8+ files | ~300 | Bespoke implementations, magic numbers, broad exceptions |

**Total potential reduction: ~2,400 LOC (22% of source)** while improving testability and maintainability.

**The core problem:** This codebase has accumulated structural debt at multiple levels:
- **Dead modules** that suggest patterns not actually used
- **Massive duplication** (BullReferenceDetector mirrors BearReferenceDetector: 600+ LOC)
- **Bespoke implementations** where standard libraries suffice (custom SparseTable: 71 LOC)
- **Over-abstracted interfaces** (25 Pydantic models where 12 would suffice)
- **Scattered magic numbers** and hardcoded thresholds across 4+ files

The ground truth annotation workflow uses exactly **three modules**: `swing_analysis`, `ground_truth_annotator`, and `data/ohlc_loader.py`. But even within those modules, significant simplification is possible.

---

## Key Questions

Before simplifying, we must answer the following questions with precision. The quality of these questions determines the quality of any restructuring.

| # | Question | Stakes |
|---|----------|--------|
| Q1 | What is the minimal set of functionality required to achieve the North Star? | Defines what cannot be cut |
| Q2 | What code exists today that has zero production callers? | Identifies immediate deletion candidates |
| Q3 | What abstractions exist that serve only one implementation? | Identifies premature abstraction |
| Q4 | What legacy paths exist that can be safely retired? | Identifies technical debt to eliminate |
| Q5 | What flexibility exists that has never been used? | Identifies YAGNI violations |
| Q6 | What is the cognitive cost of the current structure? | Quantifies the problem beyond LOC |
| Q7 | What risks does simplification introduce? | Bounds the downside |
| Q8 | **What bespoke implementations reinvent the wheel?** | Identifies library replacement opportunities |
| Q9 | **What duplication exists that violates DRY?** | Identifies consolidation opportunities |
| Q10 | **Are the abstraction levels correct?** | Identifies over/under-abstraction |

---

## Expert Consultation

I will consult a small panel of thinkers whose judgment I trust for these specific questions. This is not roleplay—it is a method for generating high-quality principles by asking "what would X say?" and translating that into actionable guidance.

### Panel Assignments

| Question | Consultant | Why This Consultant |
|----------|------------|---------------------|
| Q1 (Minimal functionality) | **John Gall** (Systemantics) | Understood that complex systems that work evolve from simple systems that work |
| Q2 (Dead code) | **Martin Fowler** (Refactoring) | Literally wrote the book on identifying and removing dead code |
| Q3 (Premature abstraction) | **Sandi Metz** (POODR) | "Duplication is far cheaper than the wrong abstraction" |
| Q4 (Legacy paths) | **Kent Beck** (XP) | "Make the change easy, then make the easy change" |
| Q5 (Unused flexibility) | **Rich Hickey** (Clojure) | "Simple made easy"—complexity from unnecessary options |
| Q6 (Cognitive cost) | **Fred Brooks** (Mythical Man-Month) | Understood conceptual integrity as the critical resource |
| Q7 (Simplification risks) | **Nancy Leveson** (System Safety) | Thinks rigorously about what can go wrong |
| Q8 (Bespoke implementations) | **Raymond Hettinger** (Python Core) | "There should be one obvious way to do it" |
| Q9 (DRY violations) | **Dave Thomas & Andy Hunt** (Pragmatic Programmer) | Coined the DRY principle |
| Q10 (Abstraction levels) | **Robert C. Martin** (Clean Code) | SOLID principles and abstraction boundaries |

---

### Consultation: John Gall on Minimal Functionality (Q1)

*"A complex system that works is invariably found to have evolved from a simple system that worked. The inverse proposition also appears to be true: A complex system designed from scratch never works and cannot be made to work."*

**Gall's counsel for this codebase:**

The system works today. That means you have a simple core that functions. The question is not "what can I add?" but "what is the irreducible core that produces value?"

For this project:
- **Swing detection** produces the structural understanding
- **Ground truth annotation** captures human judgment
- **The feedback loop** between them refines the detection rules

Everything else—validation frameworks, example scripts, historical data loaders, event detectors for futures that don't exist yet—these are anticipatory complexity. They may never be needed. If they are needed, you can add them when you need them.

**Principle:** Start with the working core. Add only what the current phase demands.

---

### Consultation: Martin Fowler on Dead Code (Q2)

*"If you have code that isn't being used, delete it. If you need it again, you can retrieve it from version control."*

**Fowler's counsel for this codebase:**

Your audit shows three modules with zero production imports:
- `src/validation/` — 923 LOC, never instantiated
- `src/data/loader.py` — 437 LOC, only in documentation
- `src/examples/` — 71 LOC, orphaned demos

Delete them. Not "archive them." Not "comment them out." Delete them. Git remembers everything. The cost of having dead code is real: it suggests patterns that aren't used, it must pass tests, it creates maintenance burden when dependencies change.

The documentation reference to `loader.py` is actually worse than no documentation—it documents capability that doesn't exist in the running system.

**Principle:** Dead code has negative value. Delete it and update documentation to match reality.

---

### Consultation: Sandi Metz on Premature Abstraction (Q3)

*"Prefer duplication over the wrong abstraction. The cost of the wrong abstraction is higher than you think."*

**Metz's counsel for this codebase:**

I see `BullReferenceDetector` and `BearReferenceDetector` as separate classes with symmetric implementations. I see 27 Pydantic models in `api.py` where perhaps 10 would suffice with inheritance or generics. I see a `ReferenceDetectionEngine` wrapper that exists to unify two classes that could have been one class with a direction parameter.

Ask: "Is this abstraction serving the current use case, or a hypothetical future?"

If `BullReferenceDetector` and `BearReferenceDetector` are always instantiated together and always called in symmetric pairs, they should be one `ReferenceDetector` with a direction. The abstraction should match the usage, not the conceptual model.

However—and this is critical—**do not refactor prematurely**. If the current structure works and the duplication is not causing bugs, leave it. The validation module is dead code; the reference detectors are working code. These are different situations.

**Principle:** Only refactor abstractions that are actively causing problems. Duplication in working code is cheaper than incorrect abstraction.

---

### Consultation: Kent Beck on Legacy Paths (Q4)

*"For each desired change, make the change easy (warning: this may be hard), then make the easy change."*

**Beck's counsel for this codebase:**

I see legacy migration functions in `storage.py`: `_migrate_to_uuid_paths()`, `_migrate_to_uuid_review_paths()`. I see schema version handling back to `version=1`.

Ask: "Have all existing data been migrated? If yes, these paths are dead."

Legacy code has a lifecycle:
1. Active migration (keep)
2. Safety net for stragglers (keep with expiration)
3. Historical cruft (delete)

If your annotation sessions are all at schema v4, the v1→v2→v3 migration paths are historical cruft. Delete them. If a user somehow has v1 data, they can migrate through git history.

The `max_rank` parameter marked "deprecated in favor of quota" should be removed. Deprecated doesn't mean "leave forever"—it means "give users time to migrate, then remove."

**Principle:** Deprecation is a process, not a permanent state. Complete the deprecation cycle.

---

### Consultation: Rich Hickey on Unused Flexibility (Q5)

*"Programmers know the benefits of everything and the tradeoffs of nothing."*

**Hickey's counsel for this codebase:**

I see a `resolution.py` module (224 LOC) that handles 9 different resolution formats (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo). How many are actually used?

I see `SwingType` enum with `ORDINARY`, `EXPLOSIVE`, `SWING_HIGH`, `SWING_LOW`—but it's never referenced in production code.

I see `EventSeverity` enum used only internally within one module.

Every option adds complexity:
- Code paths to test
- Documentation to maintain
- Cognitive load for readers ("when would I use this?")
- Bug surface area

If you only use 5m and 1h resolutions, supporting 9 is unnecessary flexibility. If `SwingType` was added for a feature that never shipped, it's dead enum.

**Principle:** Flexibility you don't use is complexity you don't need. Narrow the interface to what's actually used.

---

### Consultation: Fred Brooks on Cognitive Cost (Q6)

*"The programmer, like the poet, works only slightly removed from pure thought-stuff. He builds his castles in the air, from air, creating by exertion of the imagination. Yet the program construct, unlike the poet's words, is real in the sense that it moves and works, producing visible outputs separate from the construct itself."*

**Brooks' counsel for this codebase:**

Conceptual integrity is the most important consideration in system design. A system with a single design vision is easier to use and maintain than one designed by committee or accumulated by accretion.

This codebase has conceptual integrity in its core:
- Multi-scale swing detection (S, M, L, XL)
- Fibonacci-based structural levels
- Ground truth annotation with cascading workflow

But it has lost conceptual integrity at the edges:
- Validation module suggests a different workflow than the annotation tool
- Example scripts suggest demo paths that don't match the real CLI
- The loader module suggests batch historical analysis that isn't used

These edges create confusion. New readers ask: "Should I use the validation module or the annotation tool?" The answer is "the annotation tool, the validation module is dead"—but the code doesn't communicate that.

**Principle:** Structural simplicity enables conceptual integrity. Remove the edges that confuse the vision.

---

### Consultation: Nancy Leveson on Risks (Q7)

*"Accidents are not caused by a chain of events. They are caused by a complex web of dysfunctional interactions."*

**Leveson's counsel for this codebase:**

The risks of simplification are not in the deletion itself—git preserves everything—but in:

1. **Breaking tests that verify deleted code:** After deletion, you must verify the remaining tests still pass. Some tests may import deleted modules.

2. **Breaking documentation:** References to deleted modules in docs, README, or CLAUDE.md must be updated.

3. **Breaking implicit dependencies:** Are there configuration files, scripts, or external tools that reference deleted paths?

4. **Removing functionality that's actually needed:** The code you think is dead may be called through a path you didn't trace.

Mitigations:
- Grep exhaustively before deletion
- Run full test suite after each deletion
- Update all documentation atomically with deletions
- Create a single reversible commit for each module deletion
- If uncertain, instrument with logging before deletion to verify zero calls

**Principle:** Deletion is low-risk if you verify comprehensively before and test exhaustively after.

---

### Consultation: Raymond Hettinger on Bespoke Implementations (Q8)

*"There should be one—and preferably only one—obvious way to do it. Python comes with batteries included."*

**Hettinger's counsel for this codebase:**

I see a custom `SparseTable` class (71 LOC in `swing_detector.py:18-88`) implementing Range Minimum/Maximum Query. This is a well-known algorithm, but Python's scientific stack already handles this:

```python
# Current: Custom SparseTable (71 LOC)
class SparseTable:
    def __init__(self, values: List[float], mode: str = 'min'):
        self.n = len(values)
        self.k = self.n.bit_length()
        self.table = [[...] * self.n for _ in range(self.k)]
        # ... 47 more lines of preprocessing

# Alternative: NumPy sliding window (3 LOC)
from scipy.ndimage import minimum_filter1d, maximum_filter1d
min_in_window = minimum_filter1d(values, size=lookback*2+1, mode='nearest')
max_in_window = maximum_filter1d(values, size=lookback*2+1, mode='nearest')
```

The SparseTable gives O(1) query after O(N log N) preprocessing. The scipy approach gives O(N) for sliding window. For swing detection (called once per scale, not in a hot loop), the scipy approach is simpler and "fast enough."

**Other bespoke implementations:**
- Manual Decimal quantization in `level_calculator.py` that Decimal.quantize() handles directly
- Custom gap detection in `ohlc_loader.py` that pandas.diff() could handle

**Principle:** Use standard libraries unless you have a measured performance requirement that they cannot meet. Custom implementations require custom tests, custom documentation, and custom debugging.

---

### Consultation: Dave Thomas & Andy Hunt on DRY Violations (Q9)

*"Every piece of knowledge must have a single, unambiguous, authoritative representation within a system."*

**Thomas & Hunt's counsel for this codebase:**

The most severe DRY violation is `bull_reference_detector.py`. This file contains two nearly-identical classes:

| Component | BullReferenceDetector | BearReferenceDetector | Identical? |
|-----------|----------------------|----------------------|------------|
| `load_csv()` | Lines 632-685 | Lines 258-311 | **YES** (30 LOC) |
| `_find_swing_points()` | Lines 772-796 | Lines 395-419 | **YES** (25 LOC) |
| `_classify_explosive()` | Lines 856-877 | Lines 482-503 | **YES** (22 LOC) |
| Detection logic | Lines 798-829 | Lines 421-452 | Mirror (35 LOC) |
| Subsumption | Lines 879-926 | Lines 505-552 | Mirror (47 LOC) |

**Total duplicated code: 600+ LOC** — more than half the file.

The fix is straightforward: extract a base class parameterized by direction.

```python
class ReferenceSwingDetector:
    def __init__(self, direction: Literal["bull", "bear"], config: DetectorConfig):
        self.direction = direction
        self.primary_price = "high" if direction == "bull" else "low"
        self.secondary_price = "low" if direction == "bull" else "high"

    def detect(self, bars: List[Bar]) -> List[ReferenceSwing]:
        # Single implementation with self.primary_price/secondary_price
        pass
```

**Other DRY violations:**

1. **Annotation response conversion** (api.py lines 508-520, 531-544, 816-829): Same 12-line conversion repeated 3 times. Extract `_annotation_to_response()` helper.

2. **CSV export escaping** (storage.py + api.py): `replace(",", ";").replace("\n", " ")` appears 5+ times. Extract `escape_csv_field()`.

3. **Fibonacci level definitions** appear in 4 different files:
   - `swing_detector.py:12-14`
   - `level_calculator.py:13-15`
   - `bull_reference_detector.py:79-105`
   - `event_detector.py:80-81`

   Should be one constant: `FIB_LEVELS = [0.0, 0.382, 0.5, 0.618, 1.0, 1.382, 1.5, 1.618, 2.0]`

**Principle:** When you see the same code in two places, you have two bugs waiting to diverge. Consolidate now.

---

### Consultation: Robert C. Martin on Abstraction Levels (Q10)

*"The proper use of comments is to compensate for our failure to express ourselves in code."*

**Martin's counsel for this codebase:**

I see two opposite problems: **over-abstraction** in the API layer and **under-abstraction** in the core detection.

**Over-abstraction (api.py):**

25 Pydantic models for what could be 12. Examples:
- `MatchItem`, `FPSampleItem`, `FNItem` share 90% of fields → merge into `ReviewItem` with type discriminator
- `CascadeAdvanceResponse`, `CascadeSkipResponse` → merge into `CascadeTransitionResponse`
- `ComparisonScaleResult`, `ComparisonSummary` share structure → use inheritance

Each model is a maintenance point. When you add a field, you must add it to multiple similar models.

**Under-abstraction (swing_detector.py):**

Swings are represented as dictionaries with 13+ optional keys:
```python
{
    "high_price": float,
    "high_bar_index": int,
    "low_price": float,
    "low_bar_index": int,
    "size": float,
    "rank": int,  # Optional, added later
    "impulse": float,  # Optional, added later
    "fib_confluence_score": float,  # Optional, added later
    # ... 5 more optional fields
}
```

This should be a dataclass:
```python
@dataclass
class ReferenceSwing:
    high_price: float
    high_bar_index: int
    low_price: float
    low_bar_index: int
    size: float
    rank: int = 0
    impulse: float = 0.0
    fib_confluence_score: float = 0.0
    # ... explicit optional fields
```

Benefits: type checking catches errors, IDE autocomplete works, documentation is self-evident.

**The 351-line `detect_swings()` function** is also under-abstracted. It applies 12 sequential filters with inline logic. Should use a pipeline pattern:

```python
pipeline = SwingFilterPipeline()
pipeline.add(SizeFilter(min_candle_ratio))
pipeline.add(ProminenceFilter(min_prominence))
pipeline.add(StructuralSeparationFilter(larger_swings))
pipeline.add(QuotaFilter(quota))
result = pipeline.apply(raw_swings)
```

**Principle:** The right level of abstraction makes code self-documenting. Too little means readers must trace through logic; too much means readers must navigate unnecessary indirection.

---

## Principles → Implications

Translating the expert guidance into specific actions for this codebase:

| Principle | Implication for This Repo |
|-----------|---------------------------|
| Start with working core | Keep `swing_analysis`, `ground_truth_annotator`, `data/ohlc_loader.py` |
| Dead code has negative value | Delete `src/validation/`, `src/data/loader.py`, `src/examples/` |
| Complete deprecation cycles | Remove `max_rank` parameter, legacy migration functions |
| Narrow to what's used | Remove unused enums (`SwingType`), audit resolution formats |
| Use standard libraries | Replace SparseTable with scipy, simplify Decimal handling |
| Consolidate duplicates | Merge Bull/Bear detectors, extract response converters, centralize FIB constants |
| Right-size abstractions | Consolidate Pydantic models (25→12), add ReferenceSwing dataclass |
| Decompose large functions | Break `detect_swings()` (351 LOC) into filter pipeline |
| Verify before change, test after | Grep for imports, run tests, update docs atomically |

---

## Strategy Options

I present three options, ordered from most to least aggressive. Each could be implemented; they differ in risk, scope, and cognitive payoff.

---

### Option A: Structural Overhaul (Aggressive)

**Philosophy:** Fix the architecture, not just the dead code. Consolidate duplicates, replace bespoke implementations with libraries, right-size abstractions.

#### Actions

**PHASE 1: Delete Dead Code (1,431 LOC)**
- `src/validation/` — entire directory (923 LOC)
- `src/data/loader.py` — unused loader (437 LOC)
- `src/examples/` — entire directory (71 LOC)

**PHASE 2: Eliminate Duplication (600+ LOC saved)**

*bull_reference_detector.py refactor:*
```python
# Before: Two classes with mirrored logic (1,244 LOC)
class BullReferenceDetector: ...  # 600 LOC
class BearReferenceDetector: ...  # 600 LOC (copy-paste)

# After: Single parameterized class (~600 LOC)
class ReferenceSwingDetector:
    def __init__(self, direction: Literal["bull", "bear"]): ...
```

*api.py consolidation:*
- Extract `_annotation_to_response()` helper (saves 24 LOC)
- Merge `MatchItem`, `FPSampleItem`, `FNItem` → `ReviewItem` (saves ~40 LOC)
- Merge `CascadeAdvanceResponse`, `CascadeSkipResponse` → `CascadeTransitionResponse`
- Pydantic models: 25 → 12

*Centralize constants:*
- Create `src/swing_analysis/constants.py` with FIB_LEVELS (removes 4 duplicate definitions)
- Create `src/ground_truth_annotator/csv_utils.py` with `escape_csv_field()`

**PHASE 3: Replace Bespoke Implementations (~100 LOC saved)**

*Replace SparseTable with scipy:*
```python
# Before (71 LOC custom class)
class SparseTable:
    def __init__(self, values, mode='min'): ...
    def query(self, left, right): ...

# After (3 LOC using scipy)
from scipy.ndimage import minimum_filter1d, maximum_filter1d
```

*Simplify Decimal handling in level_calculator.py*

**PHASE 4: Add Missing Abstractions**

*Add ReferenceSwing dataclass:*
```python
@dataclass
class ReferenceSwing:
    high_price: float
    high_bar_index: int
    low_price: float
    low_bar_index: int
    size: float
    direction: Literal["bull", "bear"]
    rank: int = 0
    impulse: float = 0.0
    # ... explicit optional fields
```

**PHASE 5: Decompose Large Functions**

*Break down detect_swings() (351 LOC → ~200 LOC + filter classes):*
```python
class SwingFilterPipeline:
    filters: List[SwingFilter]
    def apply(self, swings: List[ReferenceSwing]) -> List[ReferenceSwing]

class SizeFilter(SwingFilter): ...
class ProminenceFilter(SwingFilter): ...
class StructuralSeparationFilter(SwingFilter): ...
class QuotaFilter(SwingFilter): ...
```

**PHASE 6: Tech Debt Cleanup**
- Fix 29 instances of broad `except Exception`
- Remove deprecated `max_rank` parameter
- Remove legacy migration functions in storage.py
- Extract magic numbers to named constants

#### Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Source LOC | 10,784 | ~8,300 | **-23%** |
| Modules | 5 | 3 | -40% |
| Files (src/) | 25 | ~18 | -28% |
| bull_reference_detector.py | 1,244 | ~600 | -52% |
| api.py Pydantic models | 25 | 12 | -52% |
| detect_swings() | 351 LOC | ~200 LOC | -43% |
| Broad exception handlers | 29 | 0 | -100% |

#### Risk Profile
- **Breaking risk:** Medium (refactoring working code)
- **Rollback risk:** Medium (multiple interconnected changes)
- **Cognitive payoff:** Very High (cleaner architecture, better testability)
- **Execution effort:** High (2-3 days with care)

#### Mitigations
- Execute in phases with commits between each
- Full test suite after each phase
- Integration test (run annotator) after phase 2
- Performance benchmark (swing detection <60s) after phase 3

---

### Option B: Dead Code Elimination (Moderate)

**Philosophy:** Delete everything that doesn't serve the ground truth annotation workflow. Focus on removal, not refactoring.

#### Actions

**DELETE (1,431+ LOC):**
- `src/validation/` — entire directory (923 LOC)
- `src/data/loader.py` — unused historical loader (437 LOC)
- `src/examples/` — entire directory (71 LOC)
- Legacy migration functions in `storage.py` (~50 LOC)
- `SwingType` enum in `bull_reference_detector.py` (~10 LOC)
- `max_rank` parameter and related code in `swing_detector.py` (~20 LOC)

**QUICK WINS (no structural change):**
- Extract `_annotation_to_response()` helper in api.py
- Centralize FIB_LEVELS constant (single file, import elsewhere)
- Fix the 5 most egregious `except Exception` handlers

**UPDATE:**
- `CLAUDE.md` — remove references to validation module, examples, loader
- `Docs/State/architect_notes.md` — reflect actual (simplified) architecture
- `Docs/Reference/developer_guide.md` — remove `loader.py` examples

#### Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Source LOC | 10,784 | ~9,300 | -14% |
| Modules | 5 | 3 | -40% |
| Files (src/) | 25 | ~20 | -20% |

#### Risk Profile
- **Breaking risk:** Low (dead code verified via grep)
- **Rollback risk:** Low (git preserves everything)
- **Cognitive payoff:** High (40% fewer modules to understand)
- **Execution effort:** Medium (3-4 hours with care)

---

### Option C: Minimal Cleanup (Conservative)

**Philosophy:** Only remove items that are provably unused AND have no documentation references.

#### Actions

**DELETE (~100 LOC):**
- `src/examples/generate_example.py` — orphaned
- `src/examples/generate_swing_sample.py` — orphaned
- `SwingType` enum — defined, never used

**ANNOTATE:**
- Add deprecation warnings to `loader.py`
- Add `# TODO: Remove if unused by [date]` to validation module
- Mark `max_rank` parameter as deprecated in docstring

#### Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Source LOC | 10,784 | ~10,700 | -1% |
| Modules | 5 | 5 | 0% |
| Files (src/) | 25 | 23 | -8% |

#### Risk Profile
- **Breaking risk:** Near zero
- **Rollback risk:** Near zero
- **Cognitive payoff:** Low (still 5 modules, duplication untouched)
- **Execution effort:** Very low (30 minutes)

---

## Trade-off Analysis

*In the voice of Michael Feathers (Working Effectively with Legacy Code):*

The question is not "which option has zero risk?" The question is "which option positions you best for the next 12 months of development?"

**Option A (Structural Overhaul)** is the only option that addresses *why* the codebase accumulated debt in the first place. The bull/bear duplication exists because no one extracted the abstraction when it was cheap. The 351-line function exists because no one added structure as it grew. Option A pays down principal, not just interest.

The risk is real: you're refactoring working code. But the North Star requires trading code that can be trusted completely. Code that's hard to read is code that's easy to distrust. A unified `ReferenceSwingDetector` is easier to audit than two mirrored classes with subtle divergences.

**Option B (Dead Code Elimination)** is the pragmatist's choice. Delete what's clearly dead, leave the structural debt for another day. This is defensible if you're under time pressure or if the structural debt isn't actively slowing you down.

But consider: the bull/bear duplication has already created maintenance burden. Every change to swing detection logic must be made twice. Every bug fix must be verified in two places. This compounds.

**Option C (Minimal Cleanup)** is procrastination with extra steps. Adding TODO comments doesn't reduce complexity—it documents your awareness of complexity while committing to future cleanup that may never happen.

**Comparative Analysis:**

| Criterion | A (Structural) | B (Dead Code) | C (Minimal) |
|-----------|----------------|---------------|-------------|
| Source LOC reduction | 23% (~2,500) | 14% (~1,500) | 1% (~100) |
| Risk | Medium | Low | Near Zero |
| Execution time | 2-3 days | 3-4 hours | 30 min |
| Testability improvement | High | Low | None |
| Future maintenance reduction | High | Medium | None |
| Alignment to North Star | Very High | High | Low |
| Breaks if untested? | Possibly | Unlikely | No |

**The asymmetry of regret:**

If you execute Option A and something breaks: you debug, you fix, you learn where your test coverage is weak. Net outcome: better architecture AND better tests.

If you execute Option C and nothing breaks: you've deferred the work. The duplication remains. The bespoke implementations remain. The 351-line function remains. Net outcome: unchanged, with time spent on TODO comments.

The regret-minimizing choice is Option A, executed carefully with phase gates.

---

## Recommendation

**Execute Option A (Structural Overhaul), phased over 3 work sessions.**

The evidence supports aggressive action:
- **Dead code:** 1,400+ LOC with zero production imports
- **Duplication:** 600+ LOC of copy-pasted bull/bear logic
- **Bespoke implementations:** 71 LOC custom SparseTable replaceable with 3 LOC scipy
- **Over-abstraction:** 25 Pydantic models where 12 suffice
- **Tech debt:** 29 broad exception handlers, 351-line function, magic numbers

The risks are manageable with phase gates and full test runs between each.

### Sequencing Plan

#### Session 1: Dead Code Elimination (3-4 hours)

**Phase 1.1: Verify deletions (30 min)**
```bash
grep -r "from src.validation" --include="*.py" .
grep -r "from src.data.loader" --include="*.py" .
grep -r "from src.examples" --include="*.py" .
```
Confirm zero production hits.

**Phase 1.2: Delete dead modules (1 hour)**
1. Delete `src/validation/` directory
2. Delete `src/data/loader.py`
3. Delete `src/examples/` directory
4. Update `src/data/__init__.py` if needed
5. Run test suite: `python -m pytest tests/ -v`
6. Commit: "Remove dead code: validation/, loader.py, examples/"

**Phase 1.3: Delete legacy code (30 min)**
1. Remove `SwingType` enum from `bull_reference_detector.py`
2. Remove `max_rank` parameter from `swing_detector.py`
3. Remove legacy migration functions from `storage.py`
4. Run test suite
5. Commit: "Remove deprecated code: SwingType, max_rank, migrations"

**Phase 1.4: Quick wins (1 hour)**
1. Extract `_annotation_to_response()` helper in `api.py`
2. Create `src/swing_analysis/constants.py` with centralized FIB_LEVELS
3. Update imports in 4 files that duplicate FIB constants
4. Run test suite
5. Commit: "Centralize FIB constants, extract API helpers"

**Phase 1.5: Update docs (30 min)**
1. Update `CLAUDE.md` — remove dead module references
2. Update `Docs/Reference/developer_guide.md` — remove loader examples
3. Commit: "Update docs to reflect simplified architecture"

**Checkpoint:** Run annotator end-to-end, verify core workflow.

---

#### Session 2: Consolidate Duplication (6-8 hours)

**Phase 2.1: Create ReferenceSwingDetector base (3 hours)**
1. Create `src/swing_analysis/reference_detector.py`
2. Extract shared logic from `BullReferenceDetector`/`BearReferenceDetector`
3. Parameterize by direction: `primary_price`, `secondary_price`
4. Keep old classes as thin wrappers initially for backward compat
5. Run test suite
6. Commit: "Extract ReferenceSwingDetector base class"

**Phase 2.2: Migrate callers (1 hour)**
1. Update imports in `swing_detector.py`
2. Update any direct instantiations
3. Remove thin wrappers
4. Run test suite
5. Commit: "Complete Bull/Bear detector consolidation"

**Phase 2.3: Consolidate API models (2 hours)**
1. Create `ReviewItemBase` Pydantic model
2. Merge `MatchItem`, `FPSampleItem`, `FNItem` using inheritance
3. Merge `CascadeAdvanceResponse`, `CascadeSkipResponse`
4. Update endpoint return types
5. Run test suite
6. Commit: "Consolidate Pydantic models: 25 → 12"

**Phase 2.4: Extract CSV utilities (30 min)**
1. Create `src/ground_truth_annotator/csv_utils.py`
2. Extract `escape_csv_field()` function
3. Update 5+ call sites
4. Run test suite
5. Commit: "Extract CSV utilities"

**Checkpoint:** Run annotator end-to-end, run comparison export.

---

#### Session 3: Replace Bespoke & Decompose (4-6 hours)

**Phase 3.1: Replace SparseTable (1 hour)**
1. Add `scipy` import (already in requirements if using numpy)
2. Replace `SparseTable` with `scipy.ndimage.minimum_filter1d` / `maximum_filter1d`
3. Benchmark: confirm detection still <60s for 6M bars
4. Run test suite
5. Commit: "Replace custom SparseTable with scipy filters"

**Phase 3.2: Add ReferenceSwing dataclass (1 hour)**
1. Create dataclass in `swing_detector.py` or new file
2. Update dict literals to dataclass instantiations
3. Update dict access to attribute access
4. Run test suite
5. Commit: "Add ReferenceSwing dataclass for type safety"

**Phase 3.3: Extract filter pipeline (2-3 hours)**
1. Create `SwingFilter` protocol/base class
2. Extract `SizeFilter`, `ProminenceFilter`, `StructuralSeparationFilter`, `QuotaFilter`
3. Create `SwingFilterPipeline` orchestrator
4. Refactor `detect_swings()` to use pipeline
5. Run test suite
6. Commit: "Extract swing filter pipeline from detect_swings()"

**Phase 3.4: Fix exception handling (30 min)**
1. Replace 29 `except Exception` with specific types
2. Add logging where silent passes exist
3. Run test suite
4. Commit: "Replace broad exception handlers with specific types"

**Final checkpoint:** Full integration test, performance benchmark.

---

### Done Criteria

- [ ] `src/validation/`, `src/data/loader.py`, `src/examples/` deleted
- [ ] `BullReferenceDetector`/`BearReferenceDetector` consolidated to single class
- [ ] Pydantic models reduced from 25 to 12
- [ ] `SparseTable` replaced with scipy
- [ ] `ReferenceSwing` dataclass in use
- [ ] `detect_swings()` uses filter pipeline
- [ ] All 29 broad exception handlers fixed
- [ ] All tests pass
- [ ] Swing detection <60s for 6M bars (performance preserved)
- [ ] Annotation tool launches and completes workflow
- [ ] Documentation updated
- [ ] **Total source LOC ≤ 8,500** (from 10,784)

### Reversibility

Each session produces 4-5 atomic commits. Revert granularly:
```bash
git revert <commit-hash>  # Revert specific change
git revert HEAD~4..HEAD   # Revert entire session
```

If Phase 2 (consolidation) proves too risky mid-execution:
- Keep Session 1 changes (dead code deletion)
- Revert Session 2 work
- Ship Option B instead

---

## Summary

This codebase has accumulated **~2,400 LOC of structural debt** (22% of source):
- **1,400 LOC** dead code (validation, loader, examples)
- **600 LOC** duplicated bull/bear logic
- **100+ LOC** bespoke implementations replaceable with libraries
- **200+ LOC** reducible through API model consolidation
- **29 instances** of silent exception swallowing

**Recommendation:** Execute Option A (Structural Overhaul) in three focused sessions. The result is a codebase that is:
- **23% smaller** (10,784 → ~8,300 LOC)
- **More testable** (filter pipeline, typed dataclasses)
- **More maintainable** (single reference detector, centralized constants)
- **More trustworthy** (explicit exception handling, no silent failures)

The North Star is trading code you can trust completely. Structural clarity is a prerequisite for that trust. The time invested in this cleanup pays compound dividends: every future change is easier, every future bug is more locatable, every future audit is faster.

*"Perfection is achieved not when there is nothing more to add, but when there is nothing left to take away."* — Antoine de Saint-Exupéry
