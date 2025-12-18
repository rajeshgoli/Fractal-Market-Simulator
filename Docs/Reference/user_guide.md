# Fractal Market Simulator - User Guide

## Why Use This Tool?

Markets exhibit fractal structure: large moves are composed of smaller moves following the same rules. This project provides tools to visualize, validate, and eventually generate realistic OHLC price data based on these structural dynamics.

**Key insight:** Short-term price action is driven by liquidity and momentum at key structural levels (Fibonacci ratios), not random walks. Moves complete at 2x extensions, find support/resistance at 0.382/0.618 retracements, and exhibit predictable behavior at decision zones.

**Use cases:**
- **Validate swing detection** against your own expert judgment
- **Debug structural events** with synchronized multi-timeframe replay
- **Visualize discretization** to see how price action translates to structural events
- **Build training data** for GAN-style market simulation models

---

## Table of Contents

1. [Replay View](#replay-view) - Multi-timeframe temporal debugging
2. [Ground Truth Annotator](#ground-truth-annotator) - Expert swing annotation
3. [Session Management](#session-management) - File storage and lifecycle
4. [Keyboard Shortcuts Reference](#keyboard-shortcuts-reference)

---

## Replay View

The Replay View provides a split-chart interface for temporal debugging. Compare price action at different aggregation levels simultaneously while stepping through time.

### Quick Start

```bash
# Build the React frontend (one-time or after changes)
cd frontend && npm run build && cd ..

# Start the server
source venv/bin/activate
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --resolution 5m --window 10000

# Open Replay View
open http://127.0.0.1:8000/replay
```

### Layout

- **Header**: Navigation menu, timestamp display, calibration status badge
- **Sidebar**: Event filter toggles with descriptions
- **Top Chart**: Overview chart (default: L / 1H aggregation)
- **Bottom Chart**: Detail chart (default: S / 5m aggregation)
- **Playback Controls**: Transport buttons with timer wheel
- **Explanation Panel**: Calibration report or swing details during linger pauses

### Calibration Phase

When loading Replay View, a calibration phase runs automatically:

1. **Calibrating**: First 10K bars are analyzed for swings at all scales (XL, L, M, S)
2. **Calibrated**: Report displays with active swings ready for review
3. **Playing**: After starting playback, normal replay mode begins

**Calibration Report shows:**
- Scale filters to toggle which scales to display
- Active swings count dropdown (how many to show per scale)
- Calibration report with swings detected per scale
- Scale thresholds (XL ≥ 100 pts, L ≥ 40 pts, M ≥ 15 pts, S = all)
- Navigation through active swings with `[` / `]` keys
- Start Playback button (also Space/Enter)

### Scale Filters and Active Swing Count

The calibration panel includes controls for filtering displayed swings:

**Scale Filters (checkboxes):**
- XL, L, M, S toggles to enable/disable each scale
- Default: XL, L, M enabled; S disabled (S swings are often too noisy)
- Disabled scales appear grayed out in the calibration report

**Active Swings Count (dropdown):**
- Shows 1-5 options
- Default: 2 (shows top 2 biggest swings per enabled scale)
- Swings are ranked by size (pts) within each scale
- Changing this updates the navigation total immediately

**Calibration Report columns:**
| Column | Description |
|--------|-------------|
| Scale Filters | Toggle checkboxes + count dropdown |
| Calibration Report | Swing counts per scale (N shown) |
| Scale Thresholds | Size requirements per scale |
| Navigation | Swing cycling + Start Playback |

**Active Swing Definition:**
A swing is "active" at calibration end if:
- Not invalidated (defended pivot intact)
- Not completed (hasn't reached 2.0 extension)
- Current price is within 0.382-2.0 zone

The currently selected active swing displays on both charts with Fib levels and H/L markers highlighting the high and low candles.

### Forward-Only Playback

After pressing Play (or Space/Enter) in the calibrated state, playback enters **forward-only mode**:

**How it works:**
- Playback advances **beyond** the calibration window
- Each bar is fetched incrementally (not pre-loaded)
- Swing detection runs in real-time as new bars arrive
- Chart right edge extends as new data loads

**Real-time Event Types:**
| Event | Description |
|-------|-------------|
| SWING_FORMED | New swing detected at current bar |
| SWING_INVALIDATED | Swing's defended pivot violated |
| SWING_COMPLETED | Swing reached 2.0 Fib extension |
| LEVEL_CROSS | Price crossed significant Fib level (0.382, 0.5, 0.618, 1.0, 1.382, 1.618) |

**Event Behavior:**
- Events trigger auto-pause with linger timer
- Navigate between events with arrow keys when multiple occur
- Press **Escape** or click X to dismiss linger and resume playback

**Limitations:**
- Step Back is disabled in forward-only mode (can't un-see data)
- Use Jump to Start to reset and re-watch from calibration end

### Aggregation Options

Each chart has an independent aggregation selector:

| Scale | Timeframe | Description |
|-------|-----------|-------------|
| S | 5m | Small-scale (source resolution) |
| M | 15m | Medium-scale |
| L | 1H | Large-scale |
| XL | 4H | Extra-large scale |

Note: Timeframe labels depend on source resolution. The table above assumes 5m source data.

### Time Synchronization

Both charts stay time-synchronized:
- Advancing position moves both charts to the corresponding bar
- Each chart maps the shared source bar index to its own aggregated bar
- Independent zoom allows different zoom levels per chart

### Playback Controls

| Control | Icon | Description |
|---------|------|-------------|
| Jump to Start | \|◀ | Go to first bar (reset to calibration end) |
| Previous Event | ◀◀ | Jump to previous event |
| Play/Pause | ▶/⏸ | Start/stop automatic playback |
| Next Event | ▶▶ | Jump to next event |
| Jump to End | ▶\| | Go to last bar |
| Speed | dropdown | 1x, 2x, 5x, 10x, 20x playback speed |

**Event Navigation:**
- The ◀◀ and ▶▶ buttons navigate by **event**, not bar
- Events include SWING_FORMED, SWING_INVALIDATED, SWING_COMPLETED (LEVEL_CROSS configurable via filters)
- Button disabled when no previous/next event available
- Event counter shows current position: "Event 5/23"

**Fine Control:** Use keyboard shortcuts with Shift modifier for bar-by-bar movement.

**Speed is aggregation-relative:** "2x per 1H" means 2 aggregated bars per second at the L (1H) aggregation level, which translates to 24 source bars per second if source resolution is 5m.

**Status Indicators (bottom right):**
| Indicator | Description |
|-----------|-------------|
| Event | Current event index (e.g., "Event 5/23") |
| Bar | Bars processed since playback started (starts at 1) |
| Calibrated | Number of bars used for calibration |
| Offset | Window offset in source data |
| Remaining | Bars remaining until end of data |

### Event-Driven Linger

When significant events occur during playback, the view auto-pauses:

**Linger Behavior:**
- Playback pauses when a configured event fires at the current bar
- A 30-second timer wheel appears around the pause button
- Timer countdown displays remaining seconds
- When timer completes, playback auto-resumes
- Press **Escape** or click X to dismiss and resume immediately
- Click Pause to freeze the timer

**Event Filters (Sidebar):**

| Event Type | Default | Notes |
|------------|---------|-------|
| SWING_FORMED | ON | New swing detected at scale |
| COMPLETION | ON | Ratio reached 2.0 |
| INVALIDATION | ON | Ratio crossed below threshold |
| LEVEL_CROSS | OFF | Too frequent for practical use |
| SWING_TERMINATED | OFF | Redundant with completion/invalidation |

**Scale Filters (Sidebar):**

During forward playback, the sidebar also shows scale filters (S/M/L/XL). Toggle these to show/hide events for specific scales. Filters persist during playback.

**Show Stats Toggle (Sidebar):**

During playback, a "Show Stats" toggle appears in the sidebar. When enabled, it displays the calibration stats panel (thresholds, swing counts by scale) instead of the swing explanation panel. This is useful for referencing calibration data while observing playback events.

**Multiple Events:**
When multiple events occur at the same bar, they are queued and shown sequentially. The indicator displays queue position (e.g., "1/3"). Use ◀/▶ buttons or arrow keys to navigate between events.

### Swing Explanation Panel

When lingering on a SWING_FORMED event, the explanation panel displays:

| Field | Description |
|-------|-------------|
| Scale Badge | XL, L, M, or S |
| Direction Badge | BULL (green) or BEAR (red) |
| High Endpoint | Price, bar index, timestamp |
| Low Endpoint | Price, bar index, timestamp |
| Size | Points and percentage |
| Scale Reason | Why this qualifies (e.g., "Size 112.50 >= XL threshold 100") |
| Separation | FIB distance from previous swing at same scale |

**Anchor Swings:** For the first swing at a scale, separation shows "Largest swing in calibration window - anchor point".

### Swing Overlay

During linger pauses on SWING_FORMED events:
- **Current swing**: Bright markers with H/L labels and Fibonacci level lines
- **Previous swing**: Dimmed markers for context
- Markers appear on both charts at the appropriate aggregated bars

**Fib Level Colors:**
- Purple: Defended pivot (0) and origin (1)
- Blue: Retracement zone (0.382, 0.5, 0.618)
- Green: Completion target (2.0)

### Always-On Feedback Capture

The feedback input is always visible during playback (not just during linger events), allowing you to capture observations at any point:

**How it works:**
- Text input appears in the sidebar after calibration completes
- Visible during both the calibration review phase and forward playback
- Type observations at any time (e.g., "Calibration found only 1 XL swing but I see several obvious ones")
- Submit with `Ctrl+Enter` or click Save
- **Auto-pause:** Clicking in the box or typing automatically pauses playback
- During linger events, timer pauses when input is focused

**Rich Context Snapshot:** Each observation captures complete state:
- Current state (calibrating, calibration_complete, playing, paused)
- Window offset used for session
- Bars elapsed since calibration
- Current bar index
- Swings found (count by scale: XL, L, M, S)
- Swings invalidated count
- Swings completed count
- Optional event context (if during linger event)

**Status Indicator:** Shows "paused" badge when playback was auto-paused for typing.

**Storage:** Observations persist to `ground_truth/playback_feedback.json` grouped by session.

---

## Ground Truth Annotator

The Ground Truth Annotator is a web-based tool for expert annotation of swing references. It provides a two-click workflow for marking swings on aggregated OHLC charts.

### Quick Start

```bash
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
| `--data FILE` | Path to OHLC CSV file (required) |
| `--port PORT` | Server port (default: 8000) |
| `--host HOST` | Server host (default: 127.0.0.1) |
| `--storage-dir DIR` | Working directory for sessions (default: annotation_sessions) |
| `--resolution RES` | Source data resolution: 1m, 5m, 15m, 30m, 1h, 4h, 1d (default: 1m) |
| `--window N` | Total bars to work with (default: 50000) |
| `--scale SCALE` | Scale to annotate: S, M, L, XL (default: S) |
| `--target-bars N` | Target bars to display (default: 200) |
| `--cascade` | Enable XL → L → M → S workflow |
| `--offset N` | Start offset in bars, or 'random' (default: 0) |
| `--start-date DATE` | Start at date (overrides --offset). Formats: 2020-Jan-01, 2020-01-01 |

### Examples

```bash
# Annotate small-scale swings on 1m data
python -m src.ground_truth_annotator.main --data es-1m.csv --scale S

# Cascade mode with random window
python -m src.ground_truth_annotator.main --data es-1m.csv --cascade --offset random

# Start from specific date
python -m src.ground_truth_annotator.main --data es-5m.csv --start-date 2020-Jan-01 --window 10000

# Custom port
python -m src.ground_truth_annotator.main --data es-5m.csv --scale L --port 8001
```

### Two-Click Annotation Workflow

1. **Click Start**: Click the price level of the swing start. System snaps to nearest matching extremum.
2. **Click End**: Click the price level of the swing end. Confirmation panel appears.
3. **Direction Inference**: Automatic based on price movement:
   - start.high > end.high → **Bull Reference** (downswing)
   - start.low < end.low → **Bear Reference** (upswing)
4. **Accept/Reject**: Press `A` to save, `R` to cancel.

### Snap-to-Extrema

Clicks snap to the best matching extremum:
- **Click above candle midpoint**: Snaps to nearest HIGH
- **Click below candle midpoint**: Snaps to nearest LOW

| Scale | Snap Radius (bars) |
|-------|-------------------|
| XL | 5 |
| L | 10 |
| M | 20 |
| S | 30 |

**Disable Snap:** Hold `Shift` while clicking to use exact clicked bar.

### Direction Inference

| Start Click | End Click | Direction | Meaning |
|-------------|-----------|-----------|---------|
| Near HIGH | Near LOW | Bull Reference | Downswing (high → low) |
| Near LOW | Near HIGH | Bear Reference | Upswing (low → high) |

Click position relative to candle midpoint determines intent.

### User Interface

**Chart Area:**
- OHLC candlesticks (green bullish, red bearish)
- Selection markers (blue arrows)
- Annotation markers (numbered circles)
- Fibonacci preview lines during confirmation (0, 0.382, 1.0, 2.0)

**Sidebar:**
- Annotation list with delete buttons
- Export session button
- Keyboard hints
- Confirmation panel (inline, charts remain visible)

**Toast Notifications:** Brief confirmations at bottom of screen (auto-dismiss after 2s).

### Comparison Analysis

After annotating, the system compares against automatic detection:
- **Matches**: Both you and the system identified
- **False Negatives**: You marked, system missed
- **False Positives**: System detected, you didn't mark

**Matching Tolerance:** Start/end within 20% of swing duration, minimum 5 bars.

### Review Mode

After completing annotation, Review Mode provides qualitative feedback on detection quality.

**Starting Review Mode:**
1. Complete all scales in cascade workflow
2. Click "Start Review Mode →" in sidebar
3. Or navigate to `/review`

#### Phase 1: Matches Review

Confirm detections are correct.

| Key | Action |
|-----|--------|
| `G` | Good (correct) |
| `W` | Wrong (incorrect) |
| `→` | Next swing |
| `S` | Skip all matches |

#### Phase 2: FP Sample Review

Review false positives (system detected, you didn't mark).

**Quick Dismiss:**
| Key | Reason |
|-----|--------|
| `1` | Too small |
| `2` | Too distant |
| `3` | Not prominent |
| `4` | Counter trend |
| `5` | Better high available |
| `6` | Better low available |
| `7` | Better both available |

**Better Reference (optional):** Click chart to mark high, click again for low, then dismiss. This data helps tune detection.

| Key | Action |
|-----|--------|
| `N` | Dismiss (other reason) |
| `V` | Actually valid (I missed it) |
| `C` | Clear better reference |
| `S` | Skip remaining FPs |

#### Phase 3: FN Feedback

Explain false negatives (you marked, system missed).

**Preset Explanations (auto-submit):**
| Key | Explanation |
|-----|-------------|
| `1` | Biggest swing I see at this scale |
| `2` | Most impulsive move |
| `3` | Reversal pattern |
| `4` | Structure break |
| `5` | Timeframe fit |

Or type custom explanation and press `Enter`.

#### Summary View

After all phases:
- Matches: reviewed/correct/incorrect counts
- False Positives: sampled/noise/valid counts
- False Negatives: total/explained counts

#### Session Metadata

Before finalizing, optionally provide:
- **Difficulty (1-5)**: How hard was this session?
- **Market Regime**: Bull, Bear, or Chop
- **Comments**: Free-form notes

**Quality Decision:**
- **Keep Session**: Include in ground truth (saves to ground_truth.json)
- **Discard (Practice)**: Delete session files

### Cascade Workflow

With `--cascade` mode:

1. **Annotation**: Progress XL → L → M → S
2. **Comparison**: Auto-compare after each scale
3. **Review**: Qualitative feedback after S scale
4. **Next Window**: Click "Load Next Window (Random)" for new session

---

## Session Management

### Directory Structure

```
ground_truth/
├── ground_truth.json              # All completed sessions (version-controlled)
└── sessions/                      # In-progress only (gitignored)
    └── inprogress-{timestamp}.json
```

### Session Lifecycle

1. **Start** → Creates `ground_truth/sessions/inprogress-{timestamp}.json`
2. **During session** → Updates working file as you annotate
3. **Finalize "keep"** → Appends to `ground_truth.json`, deletes working files
4. **Finalize "discard"** → Deletes working files

### Stale Session Cleanup

Sessions older than 3 hours are automatically cleaned up on startup.

### Ground Truth File

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

This file is version-controlled and represents accumulated ground truth data.

---

## Keyboard Shortcuts Reference

### Annotation Mode

| Key | Action |
|-----|--------|
| `Esc` | Cancel current selection |
| `A` | Accept annotation |
| `R` | Reject annotation |
| `N` | Next scale (cascade mode) |
| `Enter` | Accept annotation (alternative) |
| `Del` / `Backspace` | Delete last annotation |
| `Shift` + Click | Disable snap-to-extrema |

### Review Mode

| Phase | Key | Action |
|-------|-----|--------|
| Matches | `G` | Good (correct) |
| Matches | `W` | Wrong (incorrect) |
| Matches | `S` | Skip all |
| FP Sample | `1`-`7` | Quick dismiss with reason |
| FP Sample | `N` | Dismiss (other) |
| FP Sample | `V` | Valid (I missed it) |
| FP Sample | `C` | Clear better reference |
| FP Sample | `S` | Skip remaining |
| FN Feedback | `1`-`5` | Preset explanation (auto-submit) |
| FN Feedback | `Enter` | Submit custom comment |
| All | `→` | Next swing |
| All | `←` | Previous swing |

### Replay View

| Key | Context | Action |
|-----|---------|--------|
| `Space` | Calibrated | Start playback |
| `Enter` | Calibrated | Start playback |
| `[` | Calibrated | Previous active swing |
| `]` | Calibrated | Next active swing |
| `Space` | Playing | Play/Pause |
| `[` or `←` | Playing | Jump to previous event |
| `]` or `→` | Playing | Jump to next event |
| `Shift+[` | Playing | Step back one bar (fine control) |
| `Shift+]` | Playing | Step forward one bar (fine control) |
| `←` | Linger (multi-event) | Previous event in queue |
| `→` | Linger (multi-event) | Next event in queue |
| `Escape` | Linger | Dismiss linger and resume playback |
