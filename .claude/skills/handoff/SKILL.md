---
name: handoff
description: Execute structured handoff between roles. Use after completing ANY
  task to transfer work to the next persona. Outputs exactly ONE sentence in
  format "As [role], read [artifact] and [action]." No preamble. No explanation.
---

# Handoff

Output EXACTLY ONE LINE. Zero preamble. Zero explanation.

## Format

```
As [role], read [artifact] and [action].
```

## Rules

1. **One sentence only.** If you have more to say, write it to docs first.
2. **[role]** = engineer | architect | product | director
3. **[artifact]** = the doc you just updated OR the GitHub issue you just created
4. **[action]** = specific verb (implement, review, assess, diagnose)

## Examples

```
As engineer, read GitHub issue #31 and implement the CSV export feature.
```

```
As architect, read Docs/State/pending_review.md and review the 10 accumulated changes.
```

## Pre-flight Check

Before outputting, verify:
- [ ] All context written to appropriate artifact (doc or issue)
- [ ] Next agent can start immediately with ONLY this sentence
- [ ] No additional explanation needed

If any check fails, finish documentation work first.

## Blocking Conditions

Do NOT handoff if:
- Tests failing (Engineer)
- pending_review >= 10 (Engineer must wait for Architect review)
