# Shared Protocols

Essential rules all roles follow. Full system details in `director.md`.

## Ownership

Every task has exactly one owner. Ownership transfers explicitly with **Instruction**.

## Handoff Checklist

- [ ] Work documented
- [ ] Next step is concrete
- [ ] Owner artifact updated
- [ ] Instruction provided (actionable, self-contained)

## Escalation

| Blocker | Escalate To |
|---------|-------------|
| Technical ambiguity | Architect |
| Product intent unclear | Product |
| Scope/priority conflict | User (via Product) |
| **Process friction** | **Director** |

### Process Issue Format
```markdown
## Process Issue for Director

**Role:** [Engineer/Architect/Product]
**Issue:** [Specific friction]
**Suggested Fix:** [Optional]
```

## pending_review.md Ownership

**Only Engineer increments the count. Only Architect resets it to 0.**

- Engineer: Increment after code changes
- Architect: Reset to 0 after review
- Product/Director: Do NOT modify pending_review.md
- Filing issues (no code): Do NOT increment count
- See `engineer.md` for full rules

## Anti-Patterns

❌ Ambiguous ownership
❌ Archaeology required to understand state
❌ Review debt (`Docs/State/pending_review.md` count >= 10)
❌ User over-query (explore with Architect first)
❌ Product/Director modifying pending_review.md
