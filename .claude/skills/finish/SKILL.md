---
name: finish
description: Complete current task by running doc_update, file_issue, push_changes,
  and handoff as needed. Reports which steps were executed vs skipped.
---

# Finish

End-of-task orchestrator. Runs completion steps in order, skipping those not needed.

---

## Step 1: Doc Update

**Check**: Were code changes made that affect docs?

| Code Changed | Doc to Update |
|--------------|---------------|
| `src/swing_analysis/dag/*` | Docs/Reference/DAG.md |
| API endpoints / architecture | Docs/Reference/developer_guide.md |
| User-facing behavior / CLI | Docs/Reference/user_guide.md |

**If needed**: Update the appropriate doc(s).
**If not**: Report "Doc update: Not needed (no doc-affecting changes)"

---

## Step 2: File Issue

**Check**: Is there already a GitHub issue for this work?

- Run `gh issue list --search "<keywords>" --limit 5` if unsure
- **If no issue exists**: Create issue using templates from `.claude/skills/file_issue/SKILL.md` (even for user requests — tracking matters)
- **If issue exists**: Report "File issue: Not needed (working on #NNN)"

Only skip for truly trivial changes (typo fixes, comment edits). When in doubt, file.

---

## Step 3: Push Changes

**Check**: Run `git status`

- **If uncommitted changes**: Stage relevant files (exclude `.DS_Store`, `cache/`, `__pycache__/`, `.claude/settings.local.json`), commit with descriptive message
- **If unpushed commits**: Run `git push`
- **If clean and pushed**: Report "Push changes: Not needed (already pushed)"

Commit message format:
```
Brief summary in imperative mood (fixes #NNN)

- What changed
- Why it changed
```

---

## Step 4: Handoff

**Check**: Is there a next step requiring another persona?

- **If yes**: Output ONE sentence: `As [role], read [artifact] and [action].`
- **If no**: Report "Handoff: Not needed (task complete)"

---

## Output Format

After completing, summarize:

```
## Finish Summary

- Doc update: [Done / Not needed (reason)]
- File issue: [Done #NNN / Not needed (reason)]
- Push changes: [Done (commit hash) / Not needed (reason)]
- Handoff: [Done / Not needed (reason)]
```
