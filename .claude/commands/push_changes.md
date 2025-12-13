# Push Changes Command

Commit any uncommitted work from this session, then push to the remote GitHub repository.

## Workflow

1. **Check status**: `git status` to see current state
2. **Commit uncommitted changes**: If there are modified/staged files from this session:
   - Stage relevant files (exclude `.DS_Store`, `__pycache__`, `.claude/settings.local.json`)
   - Commit with a descriptive message summarizing the changes
3. **Review commits**: `git log origin/main..HEAD --oneline` to see what will be pushed
4. **Push**: `git push` (or `git push -u origin <branch>` if new branch)
5. **Confirm**: Verify push succeeded

## Output Format

```
## Push Summary

**Branch:** [branch name]
**Commits pushed:** [count]
**Remote:** [remote URL or name]

**Commits:**
- [hash] [message]
- [hash] [message]

**Status:** [Success / Failed - reason]
```

## Safety Rules

- Never force push (`--force`) without explicit user request
- Never push to main/master without explicit user confirmation
- If push fails due to remote changes, report the conflict and ask for guidance
- Only commit files that were modified as part of the current session's work
