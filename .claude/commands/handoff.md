# Handoff Command

You have completed work in a role and need to hand off to the next agent.

**CRITICAL:** Output ONLY a single sentence. No explanations. No context. No preamble.

## Required Format

```
As [role], read [artifact] and [action].
```

## Rules

1. **One sentence only.** If you have more to say, you haven't finished writing to the docs.
2. **[role]** = engineer | architect | product | director
3. **[artifact]** = the doc you just updated OR the GitHub issue you just created/updated
4. **[action]** = specific verb phrase (implement, review, assess, diagnose, etc.)

## Examples

```
As engineer, read GitHub issue #31 and implement the CSV export feature.
```

```
As architect, read Docs/State/pending_review.md and review the 5 accumulated changes.
```

```
As product, read Docs/Comms/questions.md and clarify the scope question from Architect.
```

```
As architect, read Docs/State/product_direction.md and decompose Phase 2 into issues.
```

## Pre-flight Check

Before outputting, verify:
- [ ] You wrote all context to the appropriate artifact (doc or issue)
- [ ] The next agent can start immediately with ONLY this sentence
- [ ] No additional explanation is needed

If any check fails, finish your documentation work first. Then call /handoff again.
