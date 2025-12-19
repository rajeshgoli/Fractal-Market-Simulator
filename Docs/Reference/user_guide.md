# Fractal Market Simulator - User Guide

## Why Use This Tool?

Markets exhibit fractal structure: large moves are composed of smaller moves following the same rules. This project provides tools to visualize, validate, and eventually generate realistic OHLC price data based on these structural dynamics.

**Key insight:** Short-term price action is driven by liquidity and momentum at key structural levels (Fibonacci ratios), not random walks. Moves complete at 2x extensions, find support/resistance at 0.382/0.618 retracements, and exhibit predictable behavior at decision zones.

**Use cases:**
- **Debug structural events** with synchronized multi-timeframe replay
- **Visualize discretization** to see how price action translates to structural events
- **Build training data** for GAN-style market simulation models

---

## Table of Contents

1. [Replay View](#replay-view) - Multi-timeframe temporal debugging
2. [Keyboard Shortcuts Reference](#keyboard-shortcuts-reference)

---

## Replay View

The Replay View provides a split-chart interface for temporal debugging. Compare price action at different aggregation levels simultaneously while stepping through time.

### Quick Start

```bash
# Build the React frontend (one-time or after changes)
cd frontend && npm run build && cd ..

# Start the replay server (uses HierarchicalDetector)
source venv/bin/activate
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --window 10000

# Options:
#   --port 8000         Server port (default: 8000)
#   --window 50000      Calibration window size (default: 50000)
#   --offset random     Random window offset (default: 0)
#   --start-date 2020-Jan-01  Start at specific date
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

1. **Calibrating**: First 10K bars are analyzed to build the hierarchical swing tree
2. **Calibrated**: Report displays with tree statistics and active swings ready for review
3. **Playing**: After starting playback, normal replay mode begins

**Calibration Report shows:**
- Tree navigation filters (depth, status, direction)
- Active swings count dropdown (how many largest defended swings to show)
- Structure summary with hierarchy statistics
- Range distribution and validation quick-checks
- Navigation through active swings with `[` / `]` keys
- Start Playback button (also Space/Enter)

### Tree Filters and Display Configuration

The calibration panel now uses a **hierarchical tree-based UI** instead of S/M/L/XL scale filtering:

**Tree Filters (Column 1):**

| Filter | Options | Default | Description |
|--------|---------|---------|-------------|
| Depth | Root only, 2 levels, 3 levels, All | All | How many tree levels to show |
| Status | Defended, Completed, Invalidated | Defended + Completed | Which swing statuses to include |
| Direction | Bull, Bear | Both | Filter by swing direction |
| Active Count | 1-5 | 2 | Top N largest defended swings to display |

**Structure Summary (Column 2):**

| Metric | Description |
|--------|-------------|
| Root swings | Count of swings with no parents (+ bull/bear breakdown) |
| Total nodes | Total swings in the tree |
| Max depth | Deepest hierarchy level |
| Avg children/node | Average branching factor |
| Defended by Depth | Counts of defended swings at each tree level |
| Recently invalidated | Swings invalidated in last 10 bars |

**Defended by Depth** shows clickable counts for each depth level:
- **Depth 1 (roots)**: Top-level swings (no parents)
- **Depth 2**: Children of root swings
- **Depth 3**: Grandchildren
- **Deeper**: All deeper levels combined

Click "Browse →" to filter navigation to that depth level.

**Range Distribution + Validation (Column 3):**

| Metric | Description |
|--------|-------------|
| Largest | Largest swing range in points |
| Median | Median swing range |
| Smallest | Smallest swing range |

**Validation Quick-Check:**
- Root swings have children (green check if all roots have children)
- Sibling swings detected (green check if siblings exist)
- No orphaned nodes (green check if all non-root swings have parents)

**Navigation (Column 4):**
- Shows current/total swing count
- Displays depth level badge (D0, D1, D2, etc.) and direction (BULL/BEAR)
- Navigation with `[` / `]` keys or arrow buttons
- Start Playback button

**Active Swing Definition:**
A swing is "active" (defended) at calibration end if:
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

## Keyboard Shortcuts Reference

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
