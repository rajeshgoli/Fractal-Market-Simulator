# The Fractal Market Simulator Story

> **Last refreshed:** January 1, 2026
> **Refresh guide:** `Docs/Pitch/refresh.md`

---

## THE CORE STORY

Twelve years building products at companies you'd recognize. Good at solving other people's problems. Tired of it.

So you build something for yourself. A trading system. An edge. Something where the quality bar is absolute—one edge case mishandled, one flinch in execution, and the edge disappears.

---

## THE NUMBERS

<!-- REFRESH: See pitch_refresh.md -->

| Metric | Value |
|--------|-------|
| Project start | December 9, 2025 |
| Days elapsed | 23 |
| Total commits | 747 |
| Python backend | 11,050 lines |
| TypeScript frontend | 12,612 lines |
| Test code | 13,221 lines |
| **Total production code** | **~37,000 lines** |

| Claude Code Stats | Value |
|-------------------|-------|
| Total prompts | 3,546 |
| Sessions | 715 |
| Persona invocations | 456 |
| Handoffs | 87 |

---

## PITCH 1: FOR TECHNICAL PEOPLE

*"This is the new way of working."*

---

Dude, you know what I've been doing for the last three weeks?

I shipped a production system. 37,000 lines. 600+ tests. Full frontend, backend, real-time visualization. Hierarchical swing detection with O(n log k) complexity.

Not vibe coding. *Architected.*

Here's the thing—everyone's talking about AI-assisted development like it's autocomplete on steroids. That's not what this is.

I built a workflow. Four personas: Engineer, Architect, Product, Director. They hand off to each other. Explicit artifacts. Forced review gates. The Architect role has a deletion bias—if it's not essential, it dies.

*[pull up .claude/personas/]*

Look at this. The Engineer can't continue if pending reviews hit 10. The Architect doesn't write code—only reviews and simplifies. Product owns direction. Director evolves the workflow itself.

3,546 prompts. 456 persona invocations. 87 structured handoffs.

The meta thing? On New Year's Eve, I prompted Claude to help me improve the workflow. The system building the system that builds the system.

But here's the real proof—the one-way-door decisions.

We started looking at all candles to find swing extremas. Brute force. Then I realized: if you structure it as a DAG with no lookahead, you get O(N) equivalent. Each bar comes in, you update the graph, done. No rescanning.

*[show the DAG view]*

That's not AI writing code. That's architectural judgment, executed at 10x speed.

The deletion culture is the other tell. This whole thing runs in a container. No cruft. When we removed a feature, we deleted 142 lines in one commit. No tombstones, no "# removed in #XXX" comments. Git has history—the codebase stays clean.

This is what a technical VP does at FAANG. Except I'm one person, and I did it in three weeks.

*That's* the new way of working.

---

## PITCH 2: FOR PRODUCT PEOPLE

*"Lean at 20-50x speed."*

---

Dude, you know what lean startup looks like when you can actually move?

Build, ship, refine. Everyone says it. But there's always friction—sprint planning, code review bottlenecks, deployment queues. By the time you learn something, the context is gone.

I've been shipping every day. Sometimes 50+ commits in a day. 78 on December 19th. 104 on New Year's Eve.

*[show git log --format="%ad" --date=short | sort | uniq -c]*

That's not chaos. That's structured iteration.

The vision is uncompromising: hierarchical market structure, Fibonacci levels as decision coordinates, recursive swings from monthly down to minute bars. I know exactly what I'm building.

But *how* I get there? Totally compromising.

Started with a matplotlib visualization. Threw it away, built a web UI. Started with discrete scale buckets (S/M/L/XL). Replaced it with a continuous DAG. Had a whole "Replay Mode"—deleted it when it became redundant.

*[show architect_notes.md system state table]*

See all those "Removed" entries? Inner Structure Pruning—removed. SwingNode class—removed. Replay View—removed. That's not failure. That's learning fast enough to kill your darlings.

"But it can't scale," people say. That's wrong.

Horizontal scaling is a solved problem. If it runs in one box, you make it run in many boxes. That's why the deletion discipline matters—this thing is container-ready. No hidden state, no local file dependencies, no cruft.

The workflow itself scales too. It's documented. The personas, the handoffs, the artifacts—it's a playbook. I could onboard an engineer tomorrow.

This is lean at the speed it was always supposed to be. 20x? 50x? I don't know the multiplier. But I know I've learned more in three weeks than most teams learn in a quarter.

---

## PITCH 3: FOR MONEY PEOPLE

*"The algo works. Let me show you."*

---

Here's what I've been working on.

A trading system that finds market structure—the skeleton underneath price action. No lookahead. No curve fitting. The system identifies levels *before* price gets there, then we watch what happens.

Let me show you.

*[pull up Levels at Play view, ES 2022 data]*

This is ES futures, the 2022 bear market. The system processed 20,000 bars. Found 37 XL-scale reference swings. See that red leg from 4900 down to 3500? That's the major structure.

Now look at the Fibonacci levels. 0.618 retracement is at 4336.

*[point to where price stalled]*

Price rallied, hit 4336, reversed. The system knew that level mattered—*before* price got there.

That's not backtesting. That's not lookahead. The algo found the skeleton, found the levels, and price respected them.

*[pause]*

I've been building for 12 years. Products at companies you'd recognize. I've been studying markets longer than that.

Six months ago, I went full-time on this. The tooling finally exists to build at the speed I can think. 37,000 lines of code in three weeks. 747 commits. Working product.

*[show the UI running]*

This is pre-seed. I'm not showing you results—I'm showing you I have everything needed to *get* results. The thesis. The system. The velocity. The discipline.

There is no moat. There's only tempo. The same thing that's true for Anthropic and OpenAI is true here—whoever compounds learning fastest wins.

This workflow is how I compound.

*[stop talking]*

---

## THE MONEY SHOT

When you have the demo ready:

*"This is ES futures, 2022 bear market. The system found the structure with no lookahead. Price respected the levels. That's the edge."*

Then stop.

---

## KEY VISUALS

**For technical audience:**
- `.claude/personas/` directory structure
- `architect_notes.md` review checklist
- Git log showing commit velocity
- DAG view with legs forming

**For product audience:**
- Git commits per day histogram
- System state table (all the "Removed" entries)
- The workflow diagram (Director → Product → Architect → Engineer)

**For money audience:**
- Levels at Play screenshot (the 2022 bear market)
- The 0.618 level and price respecting it
- The telemetry panel (37 XL refs, 54% pass rate)
- The UI running live

---

## DELIVERY NOTES

**Pacing:**
- Technical: can go longer, they want details
- Product: medium length, they want the method
- Money: tight, they want the proof

**What each audience is really asking:**

| Audience | Real Question |
|----------|---------------|
| Technical | "Is this rigorous or just hype?" |
| Product | "Can this method be repeated/scaled?" |
| Money | "Does the thing actually work?" |

**The universal close:**

All three pitches end the same way—you showing something real:
- Technical: the workflow artifacts, the architectural decisions
- Product: the velocity stats, the deletion discipline
- Money: the chart, the levels, price respecting them

Show, then stop talking. Let them ask questions.

---

## THE FRACTAL STACK

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

---

## MEMORABLE LINES

**On moat:**
> "There is no moat. There's only tempo. Whoever compounds learning fastest wins. This workflow is how I compound."

**On the method:**
> "This is what a technical VP does at FAANG. Except I'm one person, and I did it in three weeks."

**On lean:**
> "The vision is uncompromising. How I get there? Totally compromising."

**On why now:**
> "The tooling finally exists to build at the speed I can think."

**On why you (markets):**
> "I've been a builder for 12 years. I've been studying markets longer. Now I'm applying one to the other at a velocity that wasn't possible until this year."

**The close:**
> "This is ES futures, 2022 bear market. The system found the structure with no lookahead. Price respected the levels. That's the edge."
