# Landing Pages Expansion Spec

> **Status:** Draft
> **Author:** Engineer
> **Date:** January 3, 2026

---

## Overview

Expand the landing page into a multi-page marketing site with distinct pages for different audiences. Each page tells part of the story, all driving toward signup/demo.

### Pages to Build

| Route | Audience | Core Message |
|-------|----------|--------------|
| `/` | General | "See the structure" (existing) |
| `/developers` | Technical | "The new way of working" |
| `/traders` | Traders | "The algo works" |
| `/story` | Everyone | "Why this exists" |

### Shared Components

- **Navigation**: Add nav links to header (Developers, Traders, Story)
- **Stats Banner**: Live stats component, reusable across pages
- **CTA Block**: Consistent "Get Started" / "Try Demo" component
- **Footer**: Expand with links to all pages

---

## Page 1: `/developers`

### Hero Section

**Headline:** "37,000 Lines in 23 Days"

**Subhead:** "This is the new way of working. Four personas. Structured handoffs. Deletion discipline. One person shipping at team velocity."

**Visual:** Animated workflow diagram showing the cycle:
```
Director → Product → Architect → Engineer
    ↑                              ↓
    └──────── Handoff ─────────────┘
```

### Section: The Workflow

**Layout:** 4-column grid (or stacked on mobile), one card per persona

| Persona | Role | Key Artifact |
|---------|------|--------------|
| Director | Evolves the workflow itself | `.claude/personas/*` |
| Product | Owns direction and priorities | `product_direction.md` |
| Architect | Reviews, simplifies, deletes | `architect_notes.md` |
| Engineer | Ships code against issues | GitHub Issues |

**Interactive element:** Click a persona card to see example artifacts/prompts

### Section: The Numbers

**Layout:** Stats grid with large numbers

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│    747      │   37,000    │    600+     │     23      │
│   commits   │    lines    │    tests    │    days     │
├─────────────┼─────────────┼─────────────┼─────────────┤
│   3,546     │    456      │     87      │     10      │
│   prompts   │  personas   │  handoffs   │ max pending │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

**Note:** Consider fetching some of these live from GitHub API

### Section: The Deletion Discipline

**Headline:** "What We Removed"

**Visual:** Timeline or list showing deleted features with line counts

| Feature | Lines Deleted | Why |
|---------|---------------|-----|
| S/M/L/XL discrete scales | ~400 | Replaced with continuous DAG |
| Inner Structure Pruning | ~200 | Unnecessary complexity |
| SwingNode class | ~150 | Merged into simpler model |
| Replay View | ~300 | Redundant with new architecture |

**Quote callout:**
> "When we removed a feature, we deleted 142 lines in one commit. No tombstones, no '# removed' comments. Git has history—the codebase stays clean."

### Section: Architecture Highlights

**Layout:** 2-3 feature cards with code/diagram snippets

1. **O(n log k) Swing Detection**
   - "Each bar comes in, update the graph, done. No rescanning."
   - Mini diagram of DAG structure

2. **No Lookahead Guarantee**
   - "Levels appear before price gets there"
   - Explanation of causal constraint

3. **Container-Ready**
   - "Runs in one box? Make it run in many."
   - Show Dockerfile simplicity

### CTA Section

**Headline:** "See It In Action"

**Buttons:** "Try the Demo" | "View on GitHub" (if public)

---

## Page 2: `/traders`

### Hero Section

**Headline:** "Find Structure Before Price Does"

**Subhead:** "Hierarchical swing detection with Fibonacci levels. No lookahead. No curve fitting. The system identifies decision points before price arrives."

**Visual:** The interactive chart preview (reuse from landing page, or larger version)

### Section: How It Works

**Layout:** 3-step visual flow

```
1. DETECT SWINGS          2. PROJECT LEVELS         3. WATCH PRICE
   ┌───────────┐             ┌───────────┐            ┌───────────┐
   │  ╱╲       │             │ ── 1.618  │            │  ╱╲ ✓     │
   │ ╱  ╲  ╱╲  │     →       │ ── 1.000  │     →      │ ╱  ╲──────│
   │╱    ╲╱  ╲ │             │ ── 0.618  │            │╱    ╲╱    │
   └───────────┘             │ ── 0.382  │            └───────────┘
   Identify structure        Project fibs             Levels respected
```

### Section: The 2022 Proof

**Headline:** "ES Futures, Bear Market"

**Layout:** Full-width chart screenshot with annotations

**Key points:**
- System processed 20,000 bars
- Found 37 XL-scale reference swings
- 0.618 retracement at 4336
- Price rallied, hit 4336, reversed

**Quote callout:**
> "The system knew that level mattered—before price got there. That's not backtesting. That's not lookahead."

### Section: Fibonacci Levels

**Headline:** "Decision Coordinates"

**Visual:** Interactive fib level explainer

| Level | Meaning | Typical Use |
|-------|---------|-------------|
| 0.382 | Shallow retracement | Strong trend continuation |
| 0.618 | Golden ratio | Key reversal zone |
| 1.000 | Full retracement | Trend exhaustion |
| 1.618 | Extension | Profit targets |

### Section: Multi-Timeframe

**Headline:** "Structure Nests Inside Structure"

**Visual:** Nested rectangles showing timeframe hierarchy

```
┌─────────────────────────────────────┐
│ MONTHLY                             │
│  ┌────────────────────────────┐     │
│  │ WEEKLY                     │     │
│  │  ┌───────────────────┐     │     │
│  │  │ DAILY             │     │     │
│  │  │  ┌──────────┐     │     │     │
│  │  │  │ HOURLY   │     │     │     │
│  │  │  └──────────┘     │     │     │
│  │  └───────────────────┘     │     │
│  └────────────────────────────┘     │
└─────────────────────────────────────┘
```

**Copy:** "Trade with the larger structure, not against it."

### CTA Section

**Headline:** "See Your Markets"

**Buttons:** "Start Free Trial" | "Watch Demo Video"

---

## Page 3: `/story`

### Hero Section

**Headline:** "Why This Exists"

**Subhead:** "Twelve years building products. Tired of solving other people's problems. So I built something for myself."

**Visual:** Minimal, maybe a single striking image or the fractal stack diagram

### Section: The Builder

**Layout:** Narrative text, conversational tone

> I've been building products at companies you'd recognize for over a decade. I know how to ship. I know how to scale. I know how to manage teams.
>
> But I was always building someone else's vision.
>
> Markets have fascinated me longer than software has. The fractal nature of price action—swings within swings within swings. The way Fibonacci levels appear in natural systems. The idea that there's a skeleton underneath the chaos.
>
> Six months ago, I went full-time on this.

### Section: The Moment

**Headline:** "The Tooling Finally Exists"

> 2024 changed everything. AI-assisted development isn't autocomplete on steroids. It's a fundamental shift in what one person can build.
>
> I designed a workflow: four personas, structured handoffs, forced review gates. The system building the system that builds the system.
>
> 37,000 lines in 23 days. Not vibe coding. Architected.

### Section: The Philosophy

**Layout:** 3 quote cards

**Card 1:**
> "There is no moat. There's only tempo. Whoever compounds learning fastest wins."

**Card 2:**
> "The vision is uncompromising. How I get there? Totally compromising."

**Card 3:**
> "This is what a technical VP does at FAANG. Except I'm one person."

### Section: The Fractal Stack

**Visual:** The ASCII diagram from pitch.md, rendered nicely

```
┌─────────────────────────────────────────────────────────────┐
│                    THE FRACTAL STACK                        │
├─────────────────────────────────────────────────────────────┤
│  MARKET STRUCTURE                                           │
│    Monthly → Daily → Hourly → Minute                        │
│    (Hierarchical DAG, Fibonacci levels)                     │
├─────────────────────────────────────────────────────────────┤
│  CODEBASE                                                   │
│    ~37k lines, 747 commits, 23 days                         │
│    (LegDetector → ReferenceLayer → UI)                      │
├─────────────────────────────────────────────────────────────┤
│  WORKFLOW                                                   │
│    3,546 prompts, 456 persona invocations, 87 handoffs      │
│    (Director → Product → Architect → Engineer)              │
└─────────────────────────────────────────────────────────────┘
```

### CTA Section

**Headline:** "See What I Built"

**Buttons:** "Try the Demo" | "Read the Technical Deep-Dive" (links to /developers)

---

## Shared Component: Stats Banner

**Usage:** Can appear on any page, pulls live data where possible

**Layout:** Horizontal bar, dark background, monospace numbers

```
┌────────────────────────────────────────────────────────────────────┐
│  747 commits  •  37k lines  •  600+ tests  •  23 days  •  1 person │
└────────────────────────────────────────────────────────────────────┘
```

**Implementation notes:**
- Static for now, could fetch from GitHub API later
- Appears above footer or as section divider

---

## Shared Component: Enhanced Footer

**Layout:** 4-column grid

| Product | Developers | Company | Legal |
|---------|------------|---------|-------|
| Features | How It's Built | Story | Privacy |
| Pricing | GitHub | Contact | Terms |
| Demo | Docs | Twitter | |

---

## Navigation Updates

**Current:** `GitHub | Features | Login | Get Started`

**Proposed:** `Developers | Traders | Story | GitHub | Login | Get Started`

---

## Implementation Order

1. **Phase 1:** Navigation + Footer updates, Stats Banner component
2. **Phase 2:** `/developers` page (strongest content, clearest audience)
3. **Phase 3:** `/story` page (supports /developers narrative)
4. **Phase 4:** `/traders` page (needs more demo polish first)

---

## Open Questions

1. **GitHub link:** Public repo or private? Affects /developers content
2. **Demo video:** Do we want one for /traders? What would it show?
3. **Stats freshness:** Static in code vs. fetched from API?
4. **Mobile:** How do the workflow diagrams adapt?

---

## Success Metrics

- Time on page (especially /developers, /traders)
- Click-through to signup from each page
- Bounce rate by page
- Which page converts best?
