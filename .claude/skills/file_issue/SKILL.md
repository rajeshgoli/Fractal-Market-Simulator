---
name: file_issue
description: Create a GitHub issue with proper structure. Use when discovering
  bugs, proposing features, or creating epics. Handles issue templates,
  labeling, and epic subissue structure.
---

# File Issue

## Issue Types

- **Bug**: Unexpected behavior (include repro steps)
- **Feature**: New capability (include acceptance criteria)
- **Epic**: Multi-issue feature (include subissues)

## Procedure

1. Check for duplicates: `gh issue list --search "<keywords>" --limit 5`
2. Create issue with appropriate template
3. For epics, create subissues and link in epic body

## Epic Structure

```markdown
## Overview
[High-level goal]

## Sub-Issues
- [ ] #NNN - [description]
- [ ] #NNN - [description]
- [ ] #NNN - Update documentation (DAG.md, developer_guide.md, user_guide.md)

## Instructions for Engineer
- Fix sub issues sequentially, test and verify each
- Do NOT update pending_review per subissue — one increment for whole epic
- Push all changes in one atomic commit
- Close all subissues before closing epic
```

## Bug Template

```markdown
## Description
[What's broken]

## Repro Steps
1. ...

## Expected vs Actual
- Expected: ...
- Actual: ...
```
