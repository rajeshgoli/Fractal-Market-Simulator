---
name: interview
description: Interview user to complete a spec or proposal. Use when user says
  "/interview [spec name]" or "interview me about [topic]". Assumes Product
  persona's polymath cognitive mode. Exhausts the design space before writing.
---

# Interview

Conduct an in-depth spec interview as Product persona.

## Invocation

```
/interview <spec-name-or-path>
```

Examples:
- `/interview reference layer spec`
- `/interview Docs/Working/some_proposal.md`

## Procedure

1. **Locate spec**: Find the file (check `Docs/Working/` if path not given)
2. **Read thoroughly**: Understand what's already written
3. **Interview using `AskUserQuestion`**:
   - Technical implementation choices
   - UI/UX tradeoffs
   - Concerns and edge cases
   - Non-obvious questions only (skip what's already clear)
4. **Be thorough**: Multiple rounds expected
   - Don't stop after surface-level answers
   - Probe deeper on ambiguity
   - Exhaust the design space
5. **Continue** until user confirms complete or no ambiguity remains
6. **Update spec** with interview findings

## Cognitive Mode

Operate as polymath — bring diverse perspectives:
- Product lens: user needs, workflows, value
- Architecture lens: feasibility, tradeoffs, patterns
- Engineering lens: implementation complexity, edge cases

## Rules

- Never ask questions answered in the spec
- Prefer multi-select questions when options aren't mutually exclusive
- Surface unarticulated needs, don't confirm the obvious
- Write findings to spec immediately after interview concludes
