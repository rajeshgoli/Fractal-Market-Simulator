# Pitch Refresh

Read this doc, then refresh `Docs/Pitch/pitch.md`.

---

## The Task

Step outside the workflow. Think like a Hollywood script writer. Tell the story of the project.

The story should evoke strong emotions. Drama, suspense, cadence. Short sentences followed by long ones. Grace where it's needed.

Show the working UI, show a thing or two from the repo, tell the story. Use git history for temporal perspective if useful.

This can help recruit people, sell to investors, impress employers. Don't take it lightly.

---

## The Audiences

Three pitches, three stories they want to hear:

| Audience | Their Question | Give Them |
|----------|----------------|-----------|
| Technical | "Is this rigorous or just hype?" | The workflow, architectural decisions, O(N) DAG insight |
| Product | "Can this method scale?" | The velocity, deletion discipline, documented playbook |
| Money | "Does the thing work?" | The chart, the levels, price respecting them |

Each pitch should be what *they* want to hear, not what you want to tell.

---

## Key Sources

**Pull fresh stats from:**
- Git history (commits, velocity, peak days)
- Codebase lines (src/, frontend/src/, tests/)
- Claude history (~/.claude/history.jsonl for this project)
- Persona invocations, handoffs, session count

**Check for story updates:**
- `Docs/State/product_direction.md` — current phase
- `Docs/State/architect_notes.md` — what's been built
- Recent prompts — evolution of the workflow

**Do NOT include:**
- Personal motivation (cushion, contemplative practice, etc.)
- The pitch is for the reader, not for the founder

---

## Output

Update `Docs/Pitch/pitch.md`:
- Refresh all numbers tables
- Update narrative if phase changed or major milestones hit
- Maintain three audience versions (Technical, Product, Money)
- Keep "Dude, you know what..." energy for Technical and Product
- Keep "Here's what I've been working on" tightness for Money
- Update "Last refreshed" date

---

## When to Run

- Weekly (numbers only)
- After major milestone (numbers + narrative)
- Before a pitch meeting (full refresh)
