# Fractal Market Simulator - User Guide

## Why Use This Tool?

Markets exhibit fractal structure: large moves are composed of smaller moves following the same rules. This project provides tools to visualize, validate, and eventually generate realistic OHLC price data based on these structural dynamics.

**Key insight:** Short-term price action is driven by liquidity and momentum at key structural levels (Fibonacci ratios), not random walks. Moves complete at 2x extensions, find support/resistance at 0.382/0.618 retracements, and exhibit predictable behavior at decision zones.

**Use cases:**
- **Validate swing detection** against your own expert judgment
- **Debug structural events** with synchronized multi-timeframe replay
- **Visualize discretization** to see how price action translates to structural events
- **Build training data** for GAN-style market simulation models

For the full specification and rules, see [Product North Star](product_north_star.md).

---

## Table of Contents

1. [Replay View](#replay-view) - Multi-timeframe temporal debugging
2. [Discretization View](#discretization-view) - Structural event visualization
3. [Ground Truth Annotator](#ground-truth-annotator) - Expert swing annotation
4. [Session Management](#session-management) - File storage and lifecycle
5. [Keyboard Shortcuts Reference](#keyboard-shortcuts-reference)

---

## Replay View

The Replay View provides a split-chart interface for temporal debugging. Compare price action at different aggregation levels simultaneously while stepping through time.

### Quick Start

```bash
# Start the server
source venv/bin/activate
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --resolution 5m --window 10000

# Open Replay View
open http://127.0.0.1:8000/replay
```

### Layout

- **Top Chart**: Overview chart (default: L aggregation)
- **Bottom Chart**: Detail chart (default: S aggregation)
- **Playback Controls**: Step through bars, play/pause, speed control

### Aggregation Options

Each chart has an independent aggregation selector:

| Option | Description |
|--------|-------------|
| Source (1:1) | Raw source bars without aggregation |
| S | Small-scale aggregation |
| M | Medium-scale aggregation |
| L | Large-scale aggregation |
| XL | Extra-large aggregation |

### Time Synchronization

Both charts stay time-synchronized:
- Advancing position moves both charts to the corresponding bar
- Each chart maps the shared source bar index to its own aggregated bar
- Independent zoom allows different zoom levels per chart

### Playback Controls

| Control | Icon | Description |
|---------|------|-------------|
| Jump to Start | \|◄ | Go to first bar |
| Step Back | ◄ | Move back one source bar |
| Play/Pause | ▶/⏸ | Start/stop automatic playback |
| Step Forward | ► | Move forward one source bar |
| Jump to End | ►\| | Go to last bar |
| Speed | - | 0.5x, 1x, 2x, 5x, 10x playback speed |

The bar position indicator shows current position (e.g., "Bar: 1234 / 50000").

### Event-Driven Linger

When significant events occur during playback, the view auto-pauses to let you absorb the information:

**Linger Behavior:**
- Playback pauses when a configured event fires at the current bar
- A 30-second timer wheel appears around the pause button
- Timer countdown displays remaining seconds
- When timer completes, playback auto-resumes
- Click Play to skip ahead and resume immediately
- Click Pause to freeze the timer

**Event Filters (Sidebar):**

Configure which events trigger linger via checkboxes:

| Event Type | Default | Notes |
|------------|---------|-------|
| SWING_FORMED | ON | New swing detected at scale |
| COMPLETION | ON | Ratio reached 2.0 |
| INVALIDATION | ON | Ratio crossed below threshold |
| LEVEL_CROSS | OFF | Too frequent for practical use |
| SWING_TERMINATED | OFF | Redundant with completion/invalidation |

**Multiple Events:**
When multiple events occur at the same bar, they are queued and shown sequentially. The indicator displays queue position (e.g., "1/3").

### Swing Explanation Panel

When lingering on a SWING_FORMED event, the explanation panel displays detailed information about why the swing was detected:

**Panel Content:**

| Field | Description |
|-------|-------------|
| Scale Badge | XL, L, M, or S scale |
| Direction Badge | BULL (green) or BEAR (red) |
| High Endpoint | Price, bar index, and timestamp |
| Low Endpoint | Price, bar index, and timestamp |
| Size | Points and percentage of swing |
| Scale Reason | Why this size qualifies for this scale (e.g., "Size 112.50 >= XL threshold 100") |
| Separation | Distance in FIB levels from previous swing at same scale |

**Anchor Swings:**
For the first swing at a scale (anchor swing), the separation section shows "Largest swing in calibration window - anchor point" instead of separation metrics.

**Chart Annotations:**
When showing a SWING_FORMED explanation:
- **Current swing**: Bright markers with H/L labels and prices on both charts
- **Previous swing**: Dimmed markers with "prev H" / "prev L" labels on both charts
- Markers appear on both top and bottom charts at the appropriate aggregated bars

**Empty State:**
When not lingering on a SWING_FORMED event, the panel shows guidance: "Advance playback or step to a SWING_FORMED event to see explanation."

### Use Cases

1. **Multi-timeframe analysis**: View the same moment at different aggregation levels
2. **Swing verification**: Step through to verify swing formations
3. **Event debugging**: Correlate discretization events with price action
4. **Structure identification**: Compare larger and smaller scale structures

---

## Discretization View

The Discretization View visualizes structural events (level crossings, completions, invalidations) overlaid on the OHLC chart. Use it to verify that discretization logic corresponds to visible price action.

### Quick Start

```bash
# Start the server
source venv/bin/activate
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --resolution 5m --window 10000

# Open Discretization View
open http://127.0.0.1:8000/discretization

# Click "Run Discretization" button to process the window
```

### Running Discretization

1. Click **"Run Discretization"** to process the current window
2. The system detects swings and generates structural events
3. Events appear as markers on the chart

### Event Markers

| Event Type | Color | Shape | Meaning |
|------------|-------|-------|---------|
| Level Cross (Up) | Blue | ▲ | Price crossed a Fib level upward |
| Level Cross (Down) | Orange | ▼ | Price crossed a Fib level downward |
| Completion | Green | ★ | Swing reached 2x extension |
| Invalidation | Red | ✕ | Swing fell below threshold |
| Swing Formed | Purple | ● | New swing detected |

### Shock Visualization

Impulsive moves get enhanced markers:
- **range_multiple > 2.0**: Larger marker (1.5x size)
- **range_multiple > 3.0**: Red highlight
- **levels_jumped >= 3**: Extra-large marker

### Filtering Events

Use the sidebar filters to focus on specific events:

| Filter | Description |
|--------|-------------|
| Scale | Show only XL, L, M, or S events |
| Event Type | Show only level crosses, completions, etc. |
| Shock Threshold | Minimum `range_multiple` to display |
| Min Levels Jumped | Filter for multi-level jumps |
| Show gaps only | Only display gap events |

### Viewing Swing Fib Levels

Click any swing in the **"Active Swings"** sidebar to overlay its Fibonacci levels on the chart:
- Purple lines at defended pivot (0) and origin (1)
- Blue lines in retracement zone (0.382, 0.5, 0.618)
- Orange lines in extension zone (1.382, 1.5, 1.618)
- Green lines at completion zone (2.0+)

### Tooltip Details

Hover over any event marker to see:
- Bar index and timestamp
- Level crossed (for level cross events)
- **Effort annotation**: Dwell bars, test count
- **Shock annotation**: Levels jumped, range multiple, gap flag
- **Parent context**: Larger-scale position (scale, band, ratio)

### Statistics Panel

The sidebar shows real-time counts:
- Level Crosses
- Completions
- Invalidations
- Shock Events (range_multiple > 2.0)

### What to Assess

When viewing the discretization overlay, consider:
- **Do completions/invalidations correspond to obvious structural moves?**
- **Are level crossings logged where you'd expect them?**
- **Do shock events (larger markers) match impulsive price action?**
- **Is the narrative coherent, or mostly noise?**

This assessment informs whether to proceed to hypothesis validation or refine swing detection further.

---

## Ground Truth Annotator

The Ground Truth Annotator is a web-based tool for expert annotation of swing references. It provides a two-click workflow for marking swings on aggregated OHLC charts, with automatic direction inference.

### Quick Start

```bash
# Activate environment
source venv/bin/activate

# Basic annotation (single scale)
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --scale S

# Cascade mode (XL → L → M → S workflow) - recommended
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --cascade --offset random

# Open in browser
open http://127.0.0.1:8000
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--data FILE` | Path to OHLC CSV data file (required) |
| `--port PORT` | Server port (default: 8000) |
| `--host HOST` | Server host (default: 127.0.0.1) |
| `--storage-dir DIR` | Directory for annotation sessions |
| `--resolution RES` | Source data resolution (default: 1m) |
| `--window N` | Total bars to work with (default: 50000) |
| `--scale SCALE` | Scale to annotate: S, M, L, XL (default: S) |
| `--target-bars N` | Target bars to display in chart (default: 200) |
| `--cascade` | Enable XL → L → M → S cascade workflow |
| `--offset N` | Start offset in bars. Use 'random' for random position (default: 0) |
| `--start-date DATE` | Filter data to start at this date. Overrides --offset. Formats: `2020-Jan-01`, `2020-01-01` |

### Examples

```bash
# Annotate small-scale swings on 1m data
python -m src.ground_truth_annotator.main --data test_data/es-1m.csv --scale S

# Annotate medium-scale swings with more bars displayed
python -m src.ground_truth_annotator.main --data test_data/es-1m.csv --scale M --target-bars 300

# Annotate on 5m data with custom port
python -m src.ground_truth_annotator.main --data data/es-5m.csv --resolution 5m --scale L --port 8001

# Cascade mode (XL → L → M → S) with automatic Review Mode transition
python -m src.ground_truth_annotator.main --data test_data/es-1m.csv --cascade

# Random window selection for sampling different market regions
python -m src.ground_truth_annotator.main --data test_data/es-1m.csv --cascade --offset random

# Fixed offset to start at specific bar
python -m src.ground_truth_annotator.main --data test_data/es-1m.csv --cascade --offset 100000

# Start from specific date (test recent market regimes)
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --start-date 2020-Jan-01 --window 10000
```

### The Two-Click Annotation Workflow

1. **Click Start**: Click on the price level of the swing start. The system uses your click's Y-position to determine intent (high vs low) and **automatically snaps** to the bar with the closest matching extremum within a tolerance radius. A "Start" marker appears on the snapped candle.
2. **Click End**: Click on the price level of the swing end. The system snaps to the bar with the closest matching extremum. A confirmation panel appears in the sidebar.
3. **Confirm Direction**: The system infers the direction automatically:
   - If start.high > end.high → **Bull Reference** (downswing)
   - If start.low < end.low → **Bear Reference** (upswing)
4. **Accept or Reject**: Press `A` (or click Accept) to save, or press `R` (or click Reject) to cancel. Charts remain fully visible during confirmation.

### Snap-to-Extrema

Clicks automatically snap to the best matching extremum based on where you click:

- **Click above candle midpoint**: System looks for HIGHs, finds the bar with high closest to your click price
- **Click below candle midpoint**: System looks for LOWs, finds the bar with low closest to your click price

This allows precise selection of **intermediate structure** (e.g., lower highs, higher lows) without forcing snaps to the most extreme values in range. Click on what you see—the system finds it.

| Scale | Snap Radius (bars) |
|-------|-------------------|
| XL | 5 |
| L | 10 |
| M | 20 |
| S | 30 |

Larger scales use tighter tolerances because fewer aggregated bars are visible.

**Disabling Snap**: Hold `Shift` while clicking to use the exact clicked bar instead of snap-to-extrema. Useful when nearby extrema cause the snap to select the wrong bar.

### Direction Inference

The annotator determines swing direction based on **where you click** on each candle:

| Start Click | End Click | Direction | Meaning |
|-------------|-----------|-----------|---------|
| Near HIGH | Near LOW | Bull Reference | Downswing (high → low) |
| Near LOW | Near HIGH | Bear Reference | Upswing (low → high) |
| Same on both | (fallback) | Price comparison | Uses clicked prices |

Click position relative to candle midpoint determines intent:
- **Above midpoint** → You're marking the HIGH
- **Below midpoint** → You're marking the LOW

This allows precise control over direction even when bar structure is ambiguous (e.g., first bar has higher high but you want to mark a bear reference from its low).

### User Interface

#### Chart Area
- **OHLC Candlesticks**: Green (bullish) and red (bearish) candles
- **Selection Markers**: Blue arrows show selected start/end points
- **Annotation Markers**: Numbered circles show saved annotations
- **Fibonacci Preview Lines**: When confirming an annotation, purple dashed lines appear at key Fibonacci levels (0, 0.382, 1.0, 2.0) to help assess swing proportions. Lines auto-clear on confirm or cancel.

#### Sidebar
- **Annotation List**: All saved annotations with direction and bar range
- **Delete Button**: Click × to remove an annotation
- **Export Session**: Download current session as JSON file
- **Keyboard Hints**: Quick reference for shortcuts
- **Confirmation Panel**: Appears inline when confirming annotations (charts remain visible)

#### Toast Notifications

Brief notifications appear at the bottom of the screen to confirm actions:
- "Annotation saved" - After accepting an annotation
- "Annotation deleted" - After removing an annotation
- "Session exported" - After downloading session JSON
- "Start and end snapped to same bar..." - When snap-to-extrema causes both clicks to resolve to the same bar (hold Shift to disable snap)

Toasts auto-dismiss after 2 seconds.

#### Header
- **Scale Badge**: Shows current scale being annotated
- **Bar Count**: Number of aggregated bars displayed
- **Annotation Count**: Total annotations for this session

### Comparison Analysis

After annotating swings, the system compares your annotations against automatic detection to identify:
- **False Negatives**: Swings you marked that the system missed
- **False Positives**: Swings the system detected that you didn't mark
- **Matches**: Swings both you and the system identified

#### Matching Logic

A user annotation matches a system-detected swing when:
1. **Direction matches**: Both are bull or both are bear
2. **Start index within tolerance**: User's start is within 20% of swing duration from system's start
3. **End index within tolerance**: User's end is within 20% of swing duration from system's end
4. **Minimum tolerance**: At least 5 bars tolerance for short swings (configurable)

### Review Mode

After completing annotation (all 4 scales in cascade mode), use Review Mode to provide qualitative feedback on detection quality.

#### Starting Review Mode

1. Complete all scales in the cascade workflow (XL → L → M → S)
2. Click "Start Review Mode →" button in the sidebar
3. Or navigate directly to `/review`

#### Three-Phase Review Process

Review Mode guides you through three phases:

**Phase 1: Matches Review**

Review swings where your annotation matched system detection.

- **Purpose**: Confirm detections are actually correct
- **Actions**:
  - `G` or click "Looks Good" - Confirm match is correct
  - `W` or click "Actually Wrong" - Flag match as incorrect
  - `→` - Next swing
  - `S` - Skip all matches (advance to Phase 2)

**Phase 2: FP Sample Review**

Review a sample of false positives (system detected, you didn't mark).

- **Purpose**: Understand why system detects swings you didn't mark
- **Quick Dismiss** (one-click): Use preset buttons for common reasons:
  - `1` or click "Too small" - Detection insignificant at this scale
  - `2` or click "Too distant" - Isolated from surrounding structure
  - `3` or click "Not prominent" - Swing point doesn't stand out from neighbors
  - `4` or click "Counter trend" - Swing against prevailing trend direction
  - `5` or click "Better high" - User sees a better high for this swing
  - `6` or click "Better low" - User sees a better low for this swing
  - `7` or click "Better both" - Both better high and low available
- **Better Reference** (inline, optional): Mark "what I would have chosen" directly on the chart:
  - Click the chart to mark the high point first
  - Click again to mark the low point
  - Fibonacci preview lines appear at 0.382, 0.5, 0.618 levels
  - Press `C` to clear selection and start over
  - Then press a dismiss button (`1`-`4` or `N`) to submit with the reference
  - If no reference is marked, dismiss submits without one
  - This data helps tune detection parameters
- **Other Actions**:
  - `N` or click "Dismiss (Other)" - Mark as noise with dropdown reason
  - `V` or click "Actually Valid" - Admit you missed this swing
  - `C` - Clear better reference selection
  - `S` - Skip remaining FPs (advance to Phase 3)

**Phase 3: FN Feedback**

Explain each false negative (you marked, system missed).

- **Purpose**: Capture qualitative signal for improving detection
- **Actions**:
  - Select a preset explanation using keyboard shortcuts `1`-`5` (auto-submits and advances):
    - `1` - "Biggest swing I see at this scale"
    - `2` - "Most impulsive move"
    - `3` - "Reversal pattern"
    - `4` - "Structure break"
    - `5` - "Timeframe fit"
  - Or type a custom explanation in the text field and press `Enter` or click "Submit Feedback"
  - Optional: Select category (pattern, size, context, structure, other)
- **Note**: Preset buttons auto-submit and advance (same as FP dismiss flow). All FNs must have feedback before completing review.

#### Summary View

After all phases, see statistics:
- Matches: reviewed count, correct/incorrect
- False Positives: sampled count, noise/valid
- False Negatives: total count, explained count

#### Session Quality Control

Before exporting or moving to the next window, provide session metadata and mark quality:

**Session Metadata (optional)**:
- **Difficulty Rating (1-5)**: How hard was this annotation session?
- **Market Regime**: Bull, Bear, or Chop - characterize the overall market behavior
- **Comments**: Free-form notes about the session

**Session Quality**:
- **Keep Session** - Include this session in ground truth analysis (saves with metadata)
- **Discard (Practice)** - Exclude from analysis (deletes session files)

This allows filtering analysis data to only include high-quality annotation sessions, and the metadata helps correlate detection quality with market conditions.

#### Session Flow (Cascade Mode)

When using `--cascade` mode, the session follows this flow:

1. **Annotation Phase**: Progress through XL → L → M → S scales
2. **Completion**: After completing S scale, automatically redirect to Review Mode
3. **Review Phase**: Provide qualitative feedback on detection quality
4. **Next Window**: Click "Load Next Window (Random)" to start a new session at a random offset

This flow enables efficient sampling across different market regions, building a diverse ground truth dataset.

#### Load Next Window

After completing review, click **"Load Next Window (Random)"** to:
- Create a new annotation session
- Select a random offset into the data file
- Preserve all current settings (cascade mode, resolution, window size)
- Start fresh annotation at a different market region

Alternatively, click **"← Back to Annotation"** to return to the current session's annotation view.

---

## Session Management

### Directory Structure

```
ground_truth/
├── ground_truth.json              # All completed sessions (version-controlled)
└── sessions/                      # In-progress only (ephemeral, gitignored)
    └── inprogress-{timestamp}.json
```

### Session Lifecycle

1. **Session start** → Creates `ground_truth/sessions/inprogress-{timestamp}.json`
2. **During session** → Updates working file as you annotate
3. **Finalize "keep"** → Appends session+review to `ground_truth.json`, deletes working files
4. **Finalize "discard"** → Deletes working files (practice sessions leave no trace)

### Stale Session Cleanup

Sessions older than 3 hours are automatically cleaned up on annotator startup.

### Session Quality and Labeling

At the end of Review Mode, you can:

1. **Add a label** (optional): Enter a descriptive label like "trending_market" or "volatile_range"
2. **Keep Session**: Saves with clean timestamp filename (includes label if provided)
3. **Discard Session**: Deletes the session files entirely

Labels are sanitized for filesystem safety (spaces → underscores, special chars removed, lowercase).

### Ground Truth File

The `ground_truth/ground_truth.json` file contains all completed sessions:

```json
{
  "metadata": {
    "schema_version": 1,
    "created_at": "...",
    "last_updated": "..."
  },
  "sessions": [
    {
      "finalized_at": "...",
      "original_filename": "2025-dec-15-1225-label",
      "session": { ... },
      "review": { ... }
    }
  ]
}
```

This file is version-controlled and represents your accumulated ground truth data.

---

## Keyboard Shortcuts Reference

### Annotation Mode

| Key | Action |
|-----|--------|
| `Esc` | Cancel current selection |
| `A` | Accept annotation (when confirming) |
| `R` | Reject annotation (when confirming) |
| `N` | Next scale (cascade mode only) |
| `Enter` | Confirm annotation (alternative to A) |
| `Del` / `Backspace` | Delete last annotation |
| `Shift` + Click | Disable snap-to-extrema for this click |

### Review Mode

| Phase | Key | Action |
|-------|-----|--------|
| Matches | `G` | Good (correct) |
| Matches | `W` | Wrong (incorrect) |
| Matches | `S` | Skip all |
| FP Sample | `1` | Quick dismiss: Too small |
| FP Sample | `2` | Quick dismiss: Too distant |
| FP Sample | `3` | Quick dismiss: Not prominent |
| FP Sample | `4` | Quick dismiss: Counter trend |
| FP Sample | `5` | Quick dismiss: Better high |
| FP Sample | `6` | Quick dismiss: Better low |
| FP Sample | `7` | Quick dismiss: Better both |
| FP Sample | `N` | Dismiss with other reason |
| FP Sample | `V` | Valid (I missed it) |
| FP Sample | `C` | Clear better reference selection |
| FP Sample | `S` | Skip remaining |
| FN Feedback | `1`-`5` | Select preset (auto-submits and advances) |
| FN Feedback | `Enter` | Submit (when custom comment typed) |
| All | `→` | Next swing |
| All | `←` | Previous swing |
