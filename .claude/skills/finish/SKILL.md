---
name: finish
description: Complete current task by running doc_update, file_issue, push_changes,
  and handoff as needed. Reports which steps were executed vs skipped.
---

# Finish

End-of-task orchestrator. Runs completion steps in order, skipping those not needed.

## Procedure

Execute each step, reporting status:

### 1. Doc Update
- **Check**: Were code changes made that affect user_guide.md, developer_guide.md, or DAG.md?
- **If yes**: Read `.claude/skills/doc_update/SKILL.md` and follow it
- **If no**: Report "Doc update: Not needed (no code changes affecting docs)"

### 2. File Issue
- **Check**: Is there already a GitHub issue for this work?
- **If no issue exists AND work warrants tracking**: Read `.claude/skills/file_issue/SKILL.md` and follow it
- **If issue exists**: Report "File issue: Not needed (working on #NNN)"
- **If trivial work**: Report "File issue: Not needed (trivial change)"

### 3. Push Changes
- **Check**: `git status` — are there uncommitted or unpushed changes?
- **If yes**: Read `.claude/skills/push_changes/SKILL.md` and follow it
- **If no changes**: Report "Push changes: Not needed (nothing to push)"
- **If already pushed**: Report "Push changes: Not needed (already pushed)"

### 4. Handoff
- **Check**: Is there a next step requiring another persona?
- **If yes**: Read `.claude/skills/handoff/SKILL.md` and follow it
- **If no**: Report "Handoff: Not needed (task complete, no next step)"

## Output Format

After completing, summarize:

```
## Finish Summary

- Doc update: [Done / Not needed (reason)]
- File issue: [Done #NNN / Not needed (reason)]
- Push changes: [Done (commit hash) / Not needed (reason)]
- Handoff: [Done / Not needed (reason)]
```

## Rules

- Execute steps in order (doc_update → file_issue → push_changes → handoff)
- Never skip a check — always evaluate need
- Be honest about what wasn't needed and why
