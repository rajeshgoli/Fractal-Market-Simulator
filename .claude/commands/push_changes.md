# Push Changes Command

Push all committed changes to the remote GitHub repository.

## Pre-flight Checks

Before pushing, verify:

1. **Staged changes committed**: Run `git status` to ensure no uncommitted work
2. **On correct branch**: Confirm you're on the intended branch
3. **Remote exists**: Verify the remote is configured

## Workflow

1. **Check status**: `git status` to see current state
2. **Review commits**: `git log origin/HEAD..HEAD --oneline` to see what will be pushed
3. **Push**: `git push` (or `git push -u origin <branch>` if new branch)
4. **Confirm**: Verify push succeeded

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
