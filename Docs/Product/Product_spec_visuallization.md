# Specification Clarifications for Swing Visualization Harness

## Scale Calibration

### 1. Reference Window vs. Playback Data
Playback begins at the end of the reference window and advances forward into subsequent data. The reference window is never replayed; it exists solely to establish initial structure and calibrate scale boundaries. When playback exhausts available data, it stops at the final bar and displays a terminal state indicator. No looping or restart behavior is required.

### 2. Swing Size Measurement
Correct. Swing size is the absolute price range: `size = abs(high - low)`. This is consistent with how the existing swing detector represents swings.

### 3. Quartile Boundaries and Edge Cases
For skewed distributions, quartiles still apply but the boundaries will reflect the skew. This is acceptable; the goal is relative scale separation, not absolute thresholds.

If the reference window contains fewer than 20 swings, fall back to fixed point-based thresholds calibrated to the instrument. For ES futures, reasonable defaults would be: S < 15 points, M = 15-40 points, L = 40-100 points, XL > 100 points. These can be stored as instrument-specific configuration.

For ties at quartile boundaries, assign the swing to the higher scale. This is arbitrary but consistent.

### 4. Swings Smaller Than S-Scale
Option (b): filter them out entirely. They are not shown and do not generate events. The S-scale view should display only swings that meet the S-scale threshold. Micro-structure visibility is explicitly out of scope for this harness; the purpose is validating detection at meaningful structural scales.

---

## Aggregation Logic

### 5. Aggregation Ratios
Use median swing duration in bars as the basis. "Resolves across" means the number of bars from swing high to swing low (or low to high for bear swings).

If the median S-scale swing resolves across 20 one-minute bars, the S-scale view uses one-minute bars. If median M-scale swing resolves across 25 fifteen-minute bars, the M-scale view uses 15-minute bars.

Snap to standard timeframes. Acceptable aggregations are: 1, 5, 15, 30, 60, 240 minutes. Choose the standard timeframe that produces a bar count closest to the 10-30 target range for the median swing at that scale.

### 6. Incomplete Bar Rendering
Option (b): use only closed bars for Fibonacci level calculations. Levels remain stable until a bar closes. The incomplete bar is rendered with a distinct visual style (e.g., hollow or hatched) but does not affect structural calculations. This reduces noise and matches how traders interpret structure.

---

## Event Detection

### 7. Level Crossing Definition
Option (c): a crossing occurs when a bar's range spans from one side of the level to the other, meaning the bar opened on one side and closed on the other. This filters out wick-only touches and aligns with structural significance.

For the initial implementation, this is sufficient. A future refinement could distinguish between "closed through" and "wicked through" as separate event types, but that is out of scope for this build.

### 8. Multiple Level Crossings in One Step
Option (a): log one event per level crossed. If price gaps from 1.0 to 1.5, log crossings at 1.1, 1.382, and 1.5. Each is a distinct minor event. The event log should capture the full picture; visual annotation can highlight only the most significant (furthest level reached) to avoid clutter.

### 9. Invalidation Level Clarification
Invalidation occurs when price closes below the -0.1 level OR when price encroaches below -0.15 at any point (wick or close). This means a wick to -0.16 triggers invalidation even if the bar closes above -0.1.

For S-scale only, invalidation can alternatively trigger at a close below 0 (the swing low itself). This accommodates the higher noise at smaller scales. For M, L, and XL scales, the -0.1/-0.15 rule applies strictly.

For simplicity in the initial implementation, apply the -0.1 close / -0.15 encroachment rule uniformly across all scales. The S-scale exception can be added as a refinement if testing reveals excessive false invalidations at small scales.

### 10. Event Scope Across Scales
Completion or invalidation at one scale does not automatically cascade to other scales. Each scale maintains its own reference swings independently.

However, when a swing completes (reaches 2x), it is not deleted. The swing transitions to a "completed" state, and its Fibonacci levels remain active because price may retrace to 1.5 or 1.382. The swing is only removed from active display when a new swing of approximately the same size (within 20% tolerance) forms and becomes the new reference for that scale.

Invalidation follows the same pattern: an invalidated swing transitions to an "invalidated" state but its levels remain visible until a replacement swing forms.

This means the harness must track swing state (active, completed, invalidated) separately from swing existence.

---

## Swing Selection and Display

### 11. "Most Prominent" Ambiguity
The tiebreaker for multiple explosive swings is recency. If the biggest swing is 100 points and two explosive swings exist at 82 and 78 points, show the more recent explosive swing.

"Explosive" is quantified as points-per-bar: the swing's point range divided by its duration in bars. A swing is considered explosive if its points-per-bar exceeds 1.5x the median points-per-bar for swings at that scale.

The selection algorithm is:
1. Identify the biggest swing at this scale.
2. Identify all explosive swings at this scale (points-per-bar > 1.5x median).
3. Filter explosive swings to those within 80% of the biggest swing's size.
4. If any remain, select the most recent. Otherwise, select the biggest.

### 12. Single Swing Per Scale View
Option (a): show only the single most prominent swing per scale view. When an event occurs on a different swing, that swing temporarily takes precedence with an annotation identifying it.

The rationale is clarity. Showing multiple overlaid swings with different level sets creates visual noise that defeats the purpose of the harness. The user can infer that other reference swings exist; the harness surfaces them when structurally relevant (i.e., when they experience events).

A future refinement could add a toggle to show all active swings with visual distinction, but this is out of scope for the initial build.

### 13. Swing Lifecycle Visibility
Option (b): invalidated and completed swings remain visible with a distinct state indicator (e.g., grayed out, dashed lines for levels) until a replacement swing forms. This is essential for debugging because the user needs to see what was invalidated and why, not just what replaced it.

---

## Playback Mechanics

### 14. Step Size Units
Option (b): the default step size is one underlying data bar (one minute for one-minute data). This provides maximum granularity for observing structure forming.

The S-scale aggregation determines the *display* bar size, not the step size. The user can increase step size for faster playback, but the default should allow observing each tick of structural change.

### 15. Automatic Mode Pause Behavior
Pause on any major event at any scale. The user can configure which scales trigger pauses if frequent pauses become problematic, but the default is to pause on all major events.

The rationale is that major events are rare by definition (completions and invalidations, not level crossings). If they occur frequently enough to disrupt playback, that itself is diagnostic information about the swing detection logic.

### 16. Reset Behavior
Option (b): preserve the event log. The log is cumulative across playback runs within a session. This allows comparison and pattern recognition across multiple passes.

A separate "clear log" action can be provided, but reset should not implicitly clear.

---

## State and Persistence

### 17. Reference Swing Update Scope
Option (a): assign new swings to the scale whose range contains their size. If a swing's size falls exactly on a boundary, assign to the higher scale (consistent with question 3).

If a swing's size falls outside all calibrated ranges (larger than XL or smaller than S), handle as follows: swings larger than XL are assigned to XL; swings smaller than S are filtered out (consistent with question 4).

### 18. Scale Boundary Stability
Option (a): scale boundaries remain fixed from the reference window for the duration of the playback session. Stability is more important than adaptiveness for a validation harness. If the user suspects regime change has made the calibration stale, they can restart with a new reference window.

Periodic recalibration would introduce a confounding variable that makes it harder to isolate swing detection behavior from scale classification behavior.

---

## Technical Constraints

### 19. Data Volume and Memory
Sub-second responsiveness is required for manual step mode. Target latency is under 500ms per step for a dataset of 200,000 bars.

Achieve this by:
1. Limiting the visible window in each view to the most recent N bars (e.g., 200 bars per view), not rendering full history.
2. Precomputing aggregated bars for all scales during initial load rather than on each step.
3. Caching Fibonacci levels for active swings and updating only when swings change state.

If 500ms proves unachievable with matplotlib, the latency requirement can be relaxed to 2 seconds for the initial build, with performance optimization as a follow-up task.

### 20. Rendering Technology
Matplotlib is not a hard requirement. If initial testing shows matplotlib cannot meet the 500ms target, switch to Plotly with WebGL or a lightweight alternative like PyQtGraph. The visualization is a means to an end; the important deliverable is the validation capability, not the specific rendering library.

Recommend starting with matplotlib for simplicity, measuring actual latency with representative data, and pivoting only if necessary.

---

## Sequencing and Dependencies

### 21. Existing Module Readiness
Before building the harness, verify:

1. The swing detector correctly identifies the 674→646→702 example from the spec as a valid bullish reference swing with 2x completion at 702. Write a unit test for this specific case if one does not exist.

2. The level calculator produces all required levels: -0.1, 0, 0.1, 0.382, 0.5, 0.618, 1.0, 1.1, 1.382, 1.5, 1.618, 2.0. Verify output against hand-calculated values for a known swing.

3. The OHLC loader correctly parses both semicolon-separated European format and comma-separated Unix timestamp format. Test with sample files in each format.

If any issues are found, fix them before proceeding. The harness will amplify bugs in these modules, not diagnose them.

### 22. Minimum Viable Harness
Defer the following to a second pass:

1. Automatic playback mode. Manual stepping is sufficient for initial validation. Automatic mode is a convenience feature.

2. The "pin a specific swing" manual override. The default selection heuristic should be adequate for initial use. If it proves inadequate, that feedback will inform how to design the override.

3. Configurable pause behavior for automatic mode. Since automatic mode itself is deferred, its configuration is also deferred.

Retain in the first pass:

1. Event logging. This is essential for post-hoc analysis and cannot be deferred.

2. All four scale views. Reducing to fewer views would undermine the core validation purpose.

3. Visual state indicators for completed/invalidated swings. These are simple to implement and essential for understanding lifecycle behavior.

The minimum viable harness is: four synchronized views with manual stepping, event logging, and swing state visualization. Automatic playback and manual overrides come in pass two.