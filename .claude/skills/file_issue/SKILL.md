---
name: file_issue
description: Create a GitHub issue with proper structure. Use when discovering
  bugs, proposing features, or creating epics. Handles issue templates,
  labeling, and epic subissue structure.
---

# File Issue

## Procedure

1. Check for duplicates: `gh issue list --search "<keywords>" --limit 5`
2. Create issue with appropriate template below
3. For epics, create subissues first, then reference them in epic body

---

## Bug Template

```markdown
## Problem

[One paragraph: what's broken and why it matters]

## Root Cause

[Technical explanation of why this happens]

## Reproduction

**Data file:** `test_data/es-5m.csv`
**Starting offset:** CSV index NNNN
**Observation bar:** NNN

1. Step one
2. Step two
3. Observe: [what goes wrong]

## Solution

[What to change and why]

## Files to Change

- `path/to/file.py` — [what to modify]
- `path/to/other.py` — [what to modify]
```

---

## Feature Template

Focus on WHAT (behavior/capability), not HOW (implementation).

```markdown
## Summary

[One paragraph: what capability and why it matters]

## Behavior

[Describe what the user sees/experiences]

### Flow
1. User does X
2. System responds with Y
3. Result is Z

### UI (if applicable)
- Where it appears
- What controls exist
- What feedback user gets

## Acceptance Criteria

- [ ] [Observable behavior]
- [ ] [Observable behavior]
- [ ] [Edge case handled]
```

**Note:** Implementation details (files, code) belong in sub-issues or are left to Engineer discretion. The feature issue defines the WHAT; Engineer determines HOW.

---

## Epic Template

```markdown
## Summary

[High-level goal in one paragraph]

## Context

[Why this matters, what problem it solves]

## Sub-Issues

Complete in order unless parallelism noted:

- [ ] #NNN — [description]
- [ ] #NNN — [description]
- [ ] #NNN — Update documentation (DAG.md, developer_guide.md, user_guide.md)

## Instructions for Engineer

- Complete sub-issues sequentially, test and verify each
- Do NOT update pending_review per subissue — one increment for whole epic
- Push all changes in one atomic commit at the end
- Close all subissues before closing epic

## Acceptance Criteria

- [ ] All tests pass
- [ ] No TypeScript/Python errors
- [ ] Documentation updated
```

---

## Cleanup/Refactor Template

```markdown
## Summary

[What to clean up and why]

## Changes

| File | Change |
|------|--------|
| `path/file.py` | Remove X, rename Y |
| `path/other.py` | Delete unused Z |

## Verification

- [ ] Tests pass
- [ ] No behavioral changes
```

---

## Style Notes (from codebase patterns)

- **Be specific**: Include file paths, line numbers, config field names
- **Show code**: Use fenced code blocks for before/after examples
- **Use tables**: For comparisons, file lists, option analysis
- **Root cause matters**: For bugs, explain WHY not just WHAT
- **Acceptance criteria**: Testable, checkbox format
