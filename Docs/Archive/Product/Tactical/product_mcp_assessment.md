# Product MCP Assessment

**Date:** December 11, 2025
**From:** Product
**To:** Director
**Re:** Should Product have direct tool access via MCP server?

---

## Recommendation: DEFER

Building an MCP server for Product tool access is not the highest-leverage use of engineering time. The current bottleneck is well-defined, the user has already articulated clear requirements, and the MCP capability would solve a meta-problem rather than an actual product problem.

---

## Reasoning

### 1. The User Articulation Problem Doesn't Exist Here

The Director's framing assumes Product is limited by relying on "user articulation to understand fitness-for-purpose issues." But review the Dec 11 interview output:

- "To play out a month of data it takes me more than an hour" — Clear, measurable
- "XL-scale shows 1m bars... drowning in noise" — Clear, specific
- "S-scale shows 33 active swings" — Quantified
- "Bugs surface on zoom, pause/resume" — Observable pattern

This is high-quality, actionable feedback. The user isn't struggling to articulate—they're providing precise requirements with measurable success criteria.

### 2. Domain Expertise Is Irreplaceable

The core validation question is: **"Is this swing detected correctly?"**

Product cannot answer this question. Only the user—with 12 years of trading expertise—can judge whether the detection logic correctly identifies market structure. Product experiencing the tool would enable usability observations (buttons work, UI is responsive), but usability isn't the current bottleneck. The user already knows the UX issues.

### 3. Opportunity Cost Is High

The critical path is:
```
Validation Harness → Expert Validation → Generator
       ↓
   (we are here)
```

Engineering time spent on an MCP server is time NOT spent on:
- **Dynamic bar aggregation** (Critical)
- **Event-skip mode** (Critical)
- **S-scale swing cap** (High)
- **Stability audit** (High)

Each of these directly accelerates the user's ability to validate. The MCP server accelerates Product's ability to... observe what the user has already described.

### 4. Single-User Product Economics

The "expensive oracle" model optimizes for scenarios where user research is costly relative to the value of individual user feedback. Here:
- There is ONE user
- That user is the domain expert
- That user is highly articulate
- That user is available on demand

The economics don't favor building infrastructure to reduce user interaction.

### 5. The Goal Is Finite

The harness is not the product. The market data generator is the product. The harness exists to validate swing detection so we can trust the generator's output.

Product's job isn't to deeply experience the harness—it's to prioritize work that gets us to the generator fastest. That means: fix the harness usability issues the user already identified, enable efficient validation, and move on.

---

## Alternatives That Already Work

| Alternative | Cost | Effectiveness |
|-------------|------|---------------|
| User interviews (current) | Low | High (proven Dec 11) |
| Structured handoff checklists | Zero | Medium |
| Architect testing + observation | Low | Medium |
| Screen recordings on request | Low | Medium |

The Dec 11 interview took ~30 minutes and produced a complete, actionable product specification. This is working.

---

## When Would the Calculus Change?

Conditions that would make MCP worthwhile:

1. **Multiple users**: If we had testers beyond the primary user whose time is more expensive than engineering effort
2. **Ambiguous usability problems**: If user feedback was vague and Product needed to investigate independently
3. **Ongoing maintenance mode**: If the harness becomes a long-term product requiring continuous usability monitoring
4. **Blocked user**: If the user couldn't provide feedback (travel, unavailable)

None of these apply today.

---

## Recommendation for Current Priorities

Product's focus should remain on the Dec 11 requirements:

| Priority | Requirement | Why |
|----------|-------------|-----|
| 1 | Event-Skip Mode | Directly addresses "hour+ for a month" problem |
| 2 | Dynamic Bar Aggregation | Addresses noise/signal ratio issue |
| 3 | S-Scale Swing Cap | Reduces visual overload |
| 4 | Stability Audit | Builds confidence in tool reliability |

These four items unblock the user. The MCP server does not unblock anything—it optimizes a workflow that's already functioning.

---

## Summary

The MCP server idea comes from a genuine observation: Product operates with secondhand information. But secondhand information from an articulate domain expert is sufficient for this phase.

Build the MCP server when:
- User articulation becomes a bottleneck
- Engineering time is available beyond critical path work
- The tool becomes a long-term product rather than validation infrastructure

Until then, defer.

---

## Backlog Disposition

This item has been added to `Docs/Product/backlog.md` under "Deferred" with clear revisit triggers.

---

**Handoff:** To Director for review.
