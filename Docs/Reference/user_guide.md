# Fractal Market Simulator - User Guide

## Why Use This Tool?

Markets exhibit fractal structure: large moves are composed of smaller moves following the same rules. This project provides tools to visualize, validate, and eventually generate realistic OHLC price data based on these structural dynamics.

**Key insight:** Short-term price action is driven by liquidity and momentum at key structural levels (Fibonacci ratios), not random walks. Moves complete at 2x extensions, find support/resistance at 0.382/0.618 retracements, and exhibit predictable behavior at decision zones.

**Use cases:**
- **Debug structural events** with synchronized multi-timeframe replay
- **Visualize swing detection** to see how price action translates to structural swings
- **Build training data** for GAN-style market simulation models

---

## Table of Contents

1. [Market Structure View](#market-structure-view) - Watch the DAG build incrementally
2. [Keyboard Shortcuts Reference](#keyboard-shortcuts-reference)

---

## Market Structure View

Market Structure View provides the primary interface for observing how the hierarchical detector creates and manages candidate legs before they form into swings. This view starts with zero bars and builds incrementally as you watch.

### Quick Start

```bash
# Activate environment
source venv/bin/activate

# Start the server (no data file required)
python -m src.ground_truth_annotator.main

# Or start with a specific data file
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv

# Start at a specific date
python -m src.ground_truth_annotator.main --data test_data/es-5m.csv --start-date 2023-01-15
```

Then open http://127.0.0.1:8000/replay in your browser.

### First-Time Setup (No CLI Arguments)

When you start the server without a `--data` argument, the frontend prompts you to select a data file:

1. The Settings panel opens automatically
2. Select a CSV file from the dropdown
3. Optionally set a start date to jump to a specific point
4. Click "Apply & Restart" to load the data

Your selection is remembered in your browser (localStorage) for future sessions.

### Settings Panel

Click the **gear icon** in the header to access the Settings panel at any time. Use this to:

- **Change data file**: Switch to a different CSV source
- **Jump to a date**: Start analysis from a specific date in the data

Changes take effect immediately after restart. Session settings persist across browser sessions.

### Process Till

Use the "Till" input in the playback controls to quickly advance to a specific CSV index:

1. Enter a target CSV index (must be greater than current position)
2. Click the forward arrow or press Enter
3. The system processes all bars up to that index

This is useful for jumping to a known point of interest in the data.

### Layout

Market Structure View has a focused layout for observing leg formation:

- **Header**: Timestamp display, data file indicator, bar count, and settings gear icon
- **Top Chart**: Overview chart (macro) with leg overlays
- **Bottom Chart**: Detail chart (micro) with leg overlays
- **Playback Controls**: Transport buttons, speed control, linger toggle, Process Till input
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
| LEG_PRUNED | Leg removed (inner structure pruning, origin-proximity consolidation, or staleness) |
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

### Follow Leg Feature

The Follow Leg feature lets you track specific legs through their complete lifecycle, with visual markers showing state changes on the chart.

**How to follow a leg:**
1. Click on a leg line on the chart (or click a leg in the Current Structure Panel)
2. A tree icon and eye icon appear near the leg's pivot
3. Click the **eye icon** to follow the leg
4. The leg is recolored in your assigned tracking color

**What you see when following:**
- **Recolored leg**: The leg's line changes to your assigned tracking color (from the palette)
- **Followed Legs Panel**: The leg appears in Column 3 with state, last event, and unfollow button
- **Candle markers**: When lifecycle events occur, markers appear on the candles:
  - **F** (formed): Leg transitioned from forming to formed
  - **P** (pruned): Leg removed from active set
  - **E** (engulfed): Both origin and pivot breached
  - **X** (invalidated): Leg breaches invalidation threshold
  - **O!** / **P!**: Origin or pivot breached

**Following constraints:**
- Maximum 5 legs can be followed simultaneously
- 5 bull colors and 5 bear colors available
- Colors are recycled when you unfollow

**Color palette:**
| Direction | Slot | Name | Color |
|-----------|------|------|-------|
| Bull | B1 | Forest | Green (#228B22) |
| Bull | B2 | Teal | Teal (#008080) |
| Bull | B3 | Cyan | Cyan (#00CED1) |
| Bull | B4 | Sky | Blue (#4169E1) |
| Bull | B5 | Mint | Green (#3CB371) |
| Bear | R1 | Crimson | Red (#DC143C) |
| Bear | R2 | Coral | Orange (#FF6347) |
| Bear | R3 | Orange | Orange (#FF8C00) |
| Bear | R4 | Salmon | Pink (#FA8072) |
| Bear | R5 | Brick | Red (#B22222) |

**Event inspection:**
- Click on a candle with event markers to see event details
- Shows event type, explanation, timestamp, and leg color
- "Attach" button adds the event to your observation
- "Focus" button centers the chart on that leg

**To unfollow:**
- Click the X button next to the leg in the Followed Legs Panel
- Or click the eye icon on the leg again (when it's already followed)

### Recent Events Panel Interaction

The Recent Events panel (Column 4) displays leg lifecycle events and supports click-to-inspect:

**How to use:**
1. Click on any event in the Recent Events panel
2. A popup appears with event details (type, bar index, CSV index, reason)
3. A marker appears on both charts at the bar where the event occurred
4. If the leg still exists (for LEG_CREATED events), it highlights on the chart

**Event markers:**
| Marker | Event Type | Shape |
|--------|------------|-------|
| F | Formed | Arrow up |
| P | Pruned | Square |
| X | Invalidated | Arrow down |

**Popup actions:**
- **Attach**: Add the event to your current observation
- **Focus**: Highlight the leg on the chart and scroll the panel to it

**Marker behavior:**
- Markers appear in the leg's direction color (bull: green, bear: red)
- Markers disappear when you close the popup
- Size 2 (larger) for visibility

**Use cases:**
- **Event investigation**: Click to see exactly where and why a leg event occurred
- **Quick reference**: View event details without following the leg
- **Feedback capture**: Attach specific events to observations for debugging

### Use Cases

- **Algorithm debugging**: Watch how legs form, get pruned, and eventually become swings
- **Understanding swing formation**: See why certain price patterns form swings and others don't
- **Pruning behavior**: Observe how origin-proximity and breach pruning keep the leg count manageable
- **Hierarchy exploration**: Visualize parent-child relationships and structural nesting
- **Lifecycle tracking**: Follow specific legs to understand their complete lifecycle with visual event markers
- **Event investigation**: Click recent events to see details and chart markers for specific lifecycle events


---

## Keyboard Shortcuts Reference

| Key | Context | Action |
|-----|---------|--------|
| `Space` | Ready | Start playback |
| `Enter` | Ready | Start playback |
| `Space` | Playing | Play/Pause |
| `[` or `←` | Playing | Step back one bar |
| `]` or `→` | Playing | Step forward one bar |
| `←` | Linger (multi-event) | Previous event in queue |
| `→` | Linger (multi-event) | Next event in queue |
| `Space` | Linger | Exit linger and **pause** |
| `Escape` | Linger | Dismiss linger and resume playback |

