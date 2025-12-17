# Replay View Design Prompt

> **What this is:** A prompt for a designer agent to create a polished, professional UI design for the Replay View feature.
>
> **When to use:** When you need a visual design mockup or detailed CSS/layout recommendations for the Replay View page.
>
> **Output:** A design specification with layout, spacing, typography, color, and component styling recommendations. May include HTML/CSS snippets or Figma-style specifications.

---

You are a senior UI/UX designer specializing in financial trading applications and data visualization tools. You have deep experience with charting platforms like TradingView, Thinkorswim, and Bloomberg Terminal. You understand that traders need information-dense, glanceable interfaces that don't sacrifice clarity for density.

---

## Context

You are designing the **Replay View** for a market structure visualization tool. This view allows users to:

1. **Watch price action unfold temporally** across two synchronized charts at different timeframes
2. **Understand why the system detected swings** through an explanation panel
3. **Control playback** with play/pause, step, speed controls
4. **Filter events** that trigger auto-pause behavior

The tool is used by:
- **Discretionary traders** validating their mental model against algorithmic detection
- **Quant researchers** debugging detection logic and building intuition
- **Power users** who will spend extended sessions (30-60 min) watching replays

---

## Current State (Problems to Solve)

The current implementation is functional but has UX issues:

### Layout Issues

1. **Sidebar checkboxes look ugly** - Plain HTML checkboxes with basic styling. No visual hierarchy, no grouping, no polish.

2. **Event filters feel disconnected** - The sidebar floats without clear purpose. The relationship between filters and chart behavior isn't visually communicated.

3. **Explanation panel is dense** - Grid layout works but feels clinical. Hard to scan quickly during playback.

### Typography Issues

4. **Timestamp jumps horizontally** - The "Current Position" timestamp in the header changes width as digits change (e.g., "9:05" vs "10:30"). This causes visual jitter. Should use fixed-width/tabular numerals or right-justify.

5. **Information hierarchy is flat** - Scale badges, prices, timestamps all compete for attention. Need clear visual hierarchy.

### Interaction Issues

6. **Aggregation selector is confusing** - Currently shows `S/M/L/XL` instead of familiar `5m/15m/1H/4H/1D` labels (this is being fixed in code, but design should assume correct labels).

7. **Timer wheel during linger** - Currently uses CSS conic-gradient around pause button. Works but could be more prominent/polished.

---

## Design Requirements

### 1. Overall Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HEADER: Title, current position, navigation                                  │
├──────────────┬──────────────────────────────────────────────────────────────┤
│              │                                                               │
│   SIDEBAR    │                    CHART 1 (larger timeframe)                 │
│              │                    [Aggregation: 1H ▼]                        │
│  - Filters   │                                                               │
│  - Controls  ├──────────────────────────────────────────────────────────────┤
│              │                                                               │
│              │                    CHART 2 (smaller timeframe)                │
│              │                    [Aggregation: 5m ▼]                        │
│              │                                                               │
│              ├──────────────────────────────────────────────────────────────┤
│              │                    PLAYBACK CONTROLS                          │
│              │        |◄  ◄  [▶/⏸]  ►  ►|     Bar: 1234/50000              │
│              ├──────────────────────────────────────────────────────────────┤
│              │                    EXPLANATION PANEL                          │
│              │   SWING FORMED: XL BULL                                      │
│              │   High: 5862.50  Low: 5750.00  Size: 112.50 pts              │
└──────────────┴──────────────────────────────────────────────────────────────┘
```

**Key constraints:**
- Charts should maximize vertical space (these are the primary content)
- Sidebar should be narrow but usable (~200-240px)
- Playback controls should be compact but finger-friendly
- Explanation panel should be scannable at a glance

### 2. Color Palette

Current palette (dark theme, can be refined):
```css
--bg-primary: #1a1a2e;      /* Page background */
--bg-secondary: #16213e;    /* Card/panel background */
--bg-card: #0f3460;         /* Nested card background */
--text-primary: #eaeaea;    /* Primary text */
--text-secondary: #a0a0a0;  /* Secondary/muted text */
--accent-bull: #26a69a;     /* Bullish/green */
--accent-bear: #ef5350;     /* Bearish/red */
--accent-blue: #2196f3;     /* Interactive/highlight */
--accent-purple: #9c27b0;   /* Swing markers */
--accent-orange: #ff9800;   /* Warnings/attention */
--border-color: #333;       /* Borders */
```

Feel free to refine these while maintaining:
- Dark theme (easier on eyes for extended use)
- Clear bull/bear color distinction
- Sufficient contrast for accessibility

### 3. Sidebar Design

**Event Filters section needs:**
- Toggle switches instead of checkboxes (more modern, easier to tap)
- Visual grouping with subtle dividers
- Event type icons or color coding
- Brief descriptions that don't dominate
- "Default" vs "enabled" state should be clear

**Current event types:**
| Event | Default | Description |
|-------|---------|-------------|
| SWING_FORMED | ON | New swing detected |
| COMPLETION | ON | Ratio reached 2.0 |
| INVALIDATION | ON | Ratio below threshold |
| LEVEL_CROSS | OFF | Price crossed Fib level (frequent) |
| SWING_TERMINATED | OFF | Swing ended (redundant) |

### 4. Playback Controls

**Requirements:**
- Transport buttons: `|◄` `◄` `▶/⏸` `►` `►|`
- Speed selector: `0.5x`, `1x`, `2x`, `5x`, `10x`
- Bar position indicator: `Bar: 1234 / 50000`
- Linger indicator (during auto-pause): event type, timer, queue position

**Timer wheel behavior:**
- During linger, a 30-second countdown timer appears
- Currently rendered as conic-gradient around pause button
- Should be prominent but not distracting
- Clicking Play skips ahead, clicking Pause freezes timer

**Design the timer wheel to be:**
- Visually clear (user should see at a glance how much time remains)
- Integrated with pause button (not floating separately)
- Smooth animation (requestAnimationFrame-based)

### 5. Explanation Panel

**Content structure:**
```
┌─────────────────────────────────────────────────────────────────┐
│ SWING FORMED                                                    │
│ ┌──────┐ ┌──────┐                                               │
│ │  XL  │ │ BULL │   ← Scale and direction badges               │
│ └──────┘ └──────┘                                               │
├─────────────────────────────────────────────────────────────────┤
│ ENDPOINTS                          SIZE & SCALE                 │
│ ────────────                       ─────────────                │
│ High: 5862.50                      112.50 pts (1.92%)           │
│   Bar 1234 · Mar 15, 14:30                                      │
│                                    Why XL:                      │
│ Low: 5750.00                       Size >= 100 threshold        │
│   Bar 1200 · Mar 14, 09:15                                      │
├─────────────────────────────────────────────────────────────────┤
│ SEPARATION FROM PREVIOUS                                        │
│ ─────────────────────────                                       │
│ Distance: 0.42 FIB levels (min: 0.236)                          │
│ Reference: Previous XL swing (abc123...)                        │
│                                                                 │
│ [Previous swing shown dimmed on chart ↑]                        │
└─────────────────────────────────────────────────────────────────┘
```

**Empty state (when not on SWING_FORMED event):**
- Show helpful guidance
- Icon + brief text
- Not too prominent (charts are primary)

**Previous swing callout:**
- Dimmed section showing previous swing for context
- Should feel secondary to current swing

### 6. Typography

**Font stack:** System fonts for performance
```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

**Numeric displays (prices, bars, timestamps):**
- Use `font-variant-numeric: tabular-nums` for fixed-width digits
- Prevents layout jitter when values change
- Monospace for bar indices: `font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace`

**Hierarchy:**
- Panel titles: 1rem, medium weight, uppercase tracking
- Values: 0.9-1rem, regular weight
- Labels: 0.85rem, secondary color
- Badges: 0.85rem, bold, colored background

### 7. Responsive Behavior

**Breakpoints:**
- `>1400px`: Full layout as shown
- `1000-1400px`: Narrower sidebar, smaller fonts
- `<1000px`: Sidebar collapses to icons or moves to bottom

The tool is primarily desktop-focused but should gracefully degrade.

---

## Deliverables

Please provide:

1. **Visual mockup or detailed specification** for the redesigned Replay View
2. **CSS recommendations** for the problem areas (sidebar, timestamp, explanation panel)
3. **Component specifications** for:
   - Toggle switch (replacing checkboxes)
   - Timer wheel animation
   - Explanation panel layout
4. **Interaction notes** for any non-obvious behaviors

---

## Reference: Current Implementation

The current implementation is in:
- `src/ground_truth_annotator/static/replay.html` (single-file HTML/CSS/JS)

Key CSS classes:
- `.sidebar`, `.event-filters`, `.filter-item` - Sidebar/filters
- `.playback-controls`, `.timer-wheel`, `.linger-indicator` - Playback
- `.explanation-panel`, `.explanation-content`, `.swing-badge` - Explanation
- `.chart-panel`, `.chart-controls` - Chart containers

---

## Success Criteria

The redesigned Replay View should:

1. **Look professional** - On par with TradingView or similar tools
2. **Be scannable** - Key information visible at a glance during playback
3. **Feel cohesive** - Consistent spacing, typography, color usage
4. **Handle state well** - Clear visual distinction between playing/paused/lingering
5. **Scale gracefully** - Work at different viewport sizes

---

If this is clear, begin your design work.
