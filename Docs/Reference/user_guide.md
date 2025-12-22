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
#   --mode calibration  Visualization mode (default: calibration)
#   --mode dag          Market Structure View for leg visualization
```

### Visualization Modes

The server supports two visualization modes:

| Mode | Command | Description |
|------|---------|-------------|
| Calibration | `--mode calibration` | Default mode for swing calibration and review |
| Market Structure | `--mode dag` | View market structure as it forms with leg visualization |

**Market Structure View** is useful for observing how the hierarchical detector creates and manages candidate legs before they form into swings. See [Market Structure View](#market-structure-view) for details.

### Layout

- **Header**: Navigation menu (switch between Replay View and Market Structure View), timestamp display, calibration status badge
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

### Chart Controls

Each chart has a maximize/minimize button in the top-right corner:

| Icon | Action |
|------|--------|
| ⤢ (expand) | Maximize chart to full area, hiding the other chart |
| ⤡ (shrink) | Restore both charts side by side |

Zoom levels and scroll position are preserved through maximize/minimize.

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
| Linger | toggle | Toggle pause-on-event behavior (ON/OFF) |

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

**Linger Toggle:**
The "Linger" button next to speed controls toggles pause-on-event behavior:
- **ON (default, orange):** Events trigger auto-pause with timer wheel
- **OFF (gray):** Events are processed and logged but playback continues without pause
Use OFF mode for continuous observation without interruptions. Events are still accumulated for navigation even when linger is disabled.

**Event Filters (Sidebar):**

| Event Type | Default | Notes |
|------------|---------|-------|
| SWING_FORMED | ON | New swing detected at scale |
| COMPLETION | ON | Ratio reached 2.0 |
| INVALIDATION | ON | Ratio crossed below threshold |
| LEVEL_CROSS | OFF | Too frequent for practical use |
| SWING_TERMINATED | OFF | Redundant with completion/invalidation |

**Show Stats Toggle (Sidebar):**

During playback, a "Show Stats" toggle appears in the sidebar. When enabled, it displays the calibration stats panel (thresholds, swing counts by depth) instead of the swing explanation panel. This is useful for referencing calibration data while observing playback events.

**Current Structure Panel Toggle:**

During playback, tab buttons appear above the bottom panel allowing you to switch between:
- **Swings**: The default swing explanation panel showing formed swings and details
- **Current Structure**: Algorithm state visualization showing:
  - **Bull Legs**: Active bull legs with pivot/origin prices and retracement percentages
  - **Bear Legs**: Active bear legs with pivot/origin prices and retracement percentages
  - **Pending Pivots**: Potential pivots awaiting confirmation for each direction
  - **Recent Events**: Log of leg lifecycle events (created, pruned, invalidated)

This is useful for understanding how the algorithm detects swings and why certain swings form or fail to form.

**Multiple Events:**
When multiple events occur at the same bar, they are queued and shown sequentially. The indicator displays queue position (e.g., "1/3"). Use ◀/▶ buttons or arrow keys to navigate between events.

### Swing Explanation Panel

When lingering on a SWING_FORMED event, the explanation panel displays:

| Field | Description |
|-------|-------------|
| Depth Badge | Tree depth level (Root, Depth 2, Depth 3, etc.) |
| Direction Badge | BULL (green) or BEAR (red) |
| High Endpoint | Price, bar index, timestamp |
| Low Endpoint | Price, bar index, timestamp |
| Size | Points and percentage |
| Size Reason | Why this swing is significant based on threshold |
| Parent | Reference to containing parent swing in hierarchy |

**Root Swings:** For swings with no parent (root level), no parent reference is shown.

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
- Type observations at any time (e.g., "Calibration found only 1 root swing but I see several obvious ones")
- Submit with `Ctrl+Enter` or click Save
- **Auto-pause:** Clicking in the box or typing automatically pauses playback
- During linger events, timer pauses when input is focused

**Rich Context Snapshot:** Each observation captures complete state:
- Current state (calibrating, calibration_complete, playing, paused)
- Window offset used for session
- Bars elapsed since calibration
- Current bar index
- Swings found (count by depth: root, depth 2, depth 3, deeper)
- Swings invalidated count
- Swings completed count
- Optional event context (if during linger event)
- Mode-specific context (Replay View or Market Structure View)

**Auto-Screenshot:** A screenshot of the chart area is automatically captured with each observation for visual reference.

**Status Indicator:** Shows "paused" badge when playback was auto-paused for typing.

**Storage:**
- Observations persist to `ground_truth/playback_feedback.json` grouped by session
- Screenshots saved to `ground_truth/screenshots/{timestamp}_{mode}_{source}_{id}.png`

### Observation Attachments

When using Market Structure View or the Current Structure Panel, you can attach specific items to your observation for precise feedback:

**How to attach:**
1. Click on any item in the Current Structure Panel (leg or pending origin)
2. A purple ring highlights the attached item
3. The item appears in the Observation panel with a paperclip icon
4. Up to 5 items can be attached per observation

**Attached items show:**
- In the panel item: Purple ring border and paperclip icon
- In the Observation section: Badge showing "X/5" count
- Listed below the header with direction (BULL/BEAR), type (Leg/Pending), and bar index

**To detach:**
- Click the X button next to the attachment in the Observation section
- Or click the item again in the Current Structure Panel

**In saved feedback:**
Attachments are stored in the snapshot with full context (leg_id, prices, bar indices) for later debugging.

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

### Market Structure View

| Key | Context | Action |
|-----|---------|--------|
| `Space` | Ready | Start playback |
| `Enter` | Ready | Start playback |
| `Space` | Playing | Play/Pause |
| `[` or `←` | Playing | Step back one bar |
| `]` or `→` | Playing | Step forward one bar |
| `←` | Linger (multi-event) | Previous event in queue |
| `→` | Linger (multi-event) | Next event in queue |
| `Escape` | Linger | Dismiss linger and resume playback |

---

## Market Structure View

Market Structure View provides a specialized view for observing how the hierarchical detector creates and manages candidate legs before they form into swings. Unlike Calibration mode, Market Structure View starts with zero bars and builds incrementally as you watch.

### Quick Start

```bash
# Launch in Market Structure View
source venv/bin/activate
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --window 10000 --mode dag
```

### Layout

Market Structure View has a simplified layout compared to Calibration mode:

- **Header**: Timestamp display, bar count indicator
- **Top Chart**: Overview chart (macro) with leg overlays
- **Bottom Chart**: Detail chart (micro) with leg overlays
- **Playback Controls**: Transport buttons, speed control, linger toggle
- **Current Structure Panel**: Always-visible algorithm state display

### Incremental Build (Fixes #179)

Market Structure View now starts with **zero bars processed** and builds the structure incrementally:

1. **Press Play** to start processing bars from bar 0
2. **Watch legs form** as each bar is processed through the detector
3. **See the structure grow** as legs appear, get pruned, and eventually form swings

This matches the spec requirement: "Watch the structure build in real-time as bars load."

### Leg Visualization

Active legs are drawn as **diagonal lines** connecting origin to pivot on both charts:

| Leg Status | Appearance |
|------------|------------|
| Active | Solid line, blue (bull) / red (bear), 70% opacity |
| Stale | Dashed line, yellow, 50% opacity |
| Invalidated | Not shown (removed immediately) |

Each leg shows a single line connecting:
- **Origin point**: The swing origin extremum (where the move started)
- **Pivot point**: The defended pivot price (where the retracement reversed)

### Current Structure Panel

The Current Structure Panel is always visible in this mode (no toggle needed). It shows:

| Column | Description |
|--------|-------------|
| Bull Legs | Active bull legs with pivot/origin prices, retracement %, bar count, impulsiveness, spikiness |
| Bear Legs | Active bear legs with pivot/origin prices, retracement %, bar count, impulsiveness, spikiness |
| Pending Origins | Potential origins awaiting confirmation for bull and bear directions |
| Recent Events | Log of leg lifecycle events (LEG_CREATED, LEG_PRUNED, LEG_INVALIDATED) |

**Leg Metrics:**
| Metric | Range | Description |
|--------|-------|-------------|
| Impls (Impulsiveness) | 0-100% | Percentile rank of move intensity vs all formed legs. 90%+ = very impulsive, 10%- = gradual |
| Spiky (Spikiness) | 0-100% | Distribution of move contribution. 50% = neutral, 90%+ = spike-driven, 10%- = evenly distributed |

**Expandable Lists:** When lists have more items than can display, a clickable "+N more" button appears. Click to load 10 additional items.

**Attachments:** Click any leg or pending origin to "attach" it to your current observation. This is useful for referencing specific items when capturing feedback. See [Observation Attachments](#observation-attachments) below.

### Hover Highlighting

Hover over any item in the Current Structure Panel to highlight it on the charts:

| Item Type | Hover Effect |
|-----------|--------------|
| Active Leg | Leg line becomes thicker (4px) with full opacity; panel item shows blue ring |
| Pending Pivot | Horizontal dashed price line appears at pivot price; panel item shows colored ring |

This provides immediate visual feedback for reasoning about the algorithm's internal state.

### Chart Leg Interaction

You can interact with legs directly on the chart (not just in the panel):

| Action | Effect |
|--------|--------|
| **Hover** near a leg line | Leg highlights (same effect as panel hover) - shows it's "pickable" |
| **Single-click** on a leg | Scrolls the Current Structure Panel to that leg and highlights it with a blue focus ring |
| **Double-click** on a leg | Attaches the leg to your current observation (same as clicking in panel) |

**Why this is useful:** When a leg is visually prominent on the chart but buried in a long list in the panel, you can click it directly on the chart to find it. The panel auto-expands if needed to show the focused leg.

**Pick threshold:** Legs are pickable when your cursor is within 15 pixels of the leg line.

### Leg Event Types

| Event | Description |
|-------|-------------|
| LEG_CREATED | New candidate leg created from pivot + origin pair |
| LEG_PRUNED | Leg removed (turn pruning, inner structure pruning, proximity consolidation, or staleness) |
| LEG_INVALIDATED | Leg fell below 0.382 threshold (decisive invalidation) |

### Playback Controls

In Market Structure View, all playback controls are functional:

| Control | Icon | Description |
|---------|------|-------------|
| Play/Pause | ▶/⏸ | Start/stop incremental bar processing |
| Step Forward | ▶ | Process one bar (when paused) |
| Step Back | ◀ | Not functional (forward-only) |
| Jump to Start | \|◀ | Reset to bar 0 (restart incremental build) |
| Speed | dropdown | 1x, 2x, 5x, 10x, 20x playback speed |
| Linger | toggle | Toggle pause-on-event behavior (OFF by default in Market Structure View) |

**Linger Toggle:** In Market Structure View, linger is OFF by default for continuous observation. Enable it to pause and examine events as they occur.

### Differences from Calibration Mode

| Feature | Calibration Mode | Market Structure View |
|---------|------------------|----------------------|
| Initial state | Pre-calibrated (10K bars) | Empty (0 bars) |
| Build process | Instant (pre-computed) | Incremental (watch it build) |
| Sidebar | Event filters, feedback | Current structure, linger toggles, feedback |
| Swing overlay | Fib levels for formed swings | Diagonal leg lines for candidates |
| Linger default | ON | OFF (continuous observation) |
| Event navigation | Jump between swing events | Not available |
| Current Structure Panel | Toggle (Swings/Current Structure tabs) | Always visible |

### Hierarchy Exploration Mode

Hierarchy exploration mode lets you visualize parent-child relationships between legs, showing structural nesting and containment.

**How to enter:**
1. Click on any leg line on the chart
2. The leg highlights in the panel and a tree icon appears near the pivot point
3. Click the tree icon to enter hierarchy mode

**What you see:**
- **Focused leg**: Highlighted with full opacity and thick line (4px)
- **Related legs**: Ancestors and descendants shown at 80% opacity with 3px lines
- **Other legs**: Faded to 15% opacity with thin lines
- **Connection lines**: Dashed lines connect parent-child leg pivots
- **Status indicator**: Shows leg ID, depth, and lineage counts (top-left)
- **Exit button**: X button in top-right corner

**Navigation within hierarchy mode:**
- Click on any highlighted (related) leg to recenter the view on that leg
- The lineage is recalculated from the new focused leg
- Non-related legs remain faded

**How to exit:**
- Press `ESC` key
- Click the X button in the top-right corner

**What hierarchy shows:**
| Concept | Description |
|---------|-------------|
| Ancestors | Parent → grandparent → ... → root leg chain |
| Descendants | All legs whose parent chain includes this leg |
| Depth | How many ancestors this leg has (0 = root) |

**Use cases:**
- **Structure debugging**: See which smaller legs are nested within larger ones
- **Origin tracking**: Follow how legs spawn from each other
- **Zoom levels**: Understand the fractal containment of price structures

### Use Cases

- **Algorithm debugging**: Watch how legs form, get pruned, and eventually become swings
- **Understanding swing formation**: See why certain price patterns form swings and others don't
- **Pruning behavior**: Observe how proximity and breach pruning keep the leg count manageable
- **Hierarchy exploration**: Visualize parent-child relationships and structural nesting
