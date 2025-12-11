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

## Anti-Patterns

❌ Ambiguous ownership
❌ Archaeology required to understand state
❌ Review debt (PENDING_REVIEW >= 5)
❌ User over-query (explore with Architect first)
