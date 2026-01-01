---
name: handoff
description: Execute structured handoff between roles. Use after completing ANY
  task to transfer work to the next persona. Outputs 1-4 sentences starting with
  "As [role]" followed by ordered actions. No preamble. No explanation.
---

# Handoff

Output 1-4 SENTENCES. Zero preamble. Zero explanation.

## Format

```
As [role], [action sequence].
```

## Rules

1. **1-4 sentences max.** Start with "As [role]". List actions in order.
2. **[role]** = engineer | architect | product | director
3. **Actions** = specific verbs with artifacts (read, merge, update, create, implement)
4. **Order matters** — list prerequisite actions before dependent ones.

## Examples

Simple (1 sentence):
```
As engineer, read GitHub issue #31 and implement the CSV export feature.
```

Complex (multi-sentence):
```
As architect, read Docs/Working/reference_layer_spec.md and reference_layer_spec_addendum.md. Review Docs/State/architect_notes.md and completed work in #360. Merge the spec and addendum, update architect notes, then create the next epic for engineer.
```

```
As product, read Docs/Comms/questions.md and answer the open design questions. Update product_direction.md with decisions, then handoff to architect.
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
