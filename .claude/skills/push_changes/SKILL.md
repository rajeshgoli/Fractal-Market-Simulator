---
name: push_changes
description: Commit and push changes to GitHub. Use after completing
  implementation and doc updates. Commits uncommitted changes first if any
  exist. Ensures atomic commits with proper messages.
---

# Push Changes

## Procedure

1. Check status: `git status`
2. If uncommitted changes, stage and commit
3. Push: `git push`
4. Verify: `git status` shows clean

## Commit Message Format

```
Brief summary in imperative mood (fixes #NNN)

- What changed
- Why it changed
- Any notable decisions
```

Use HEREDOC for multi-line messages:
```bash
git commit -m "$(cat <<'EOF'
Brief summary (fixes #NNN)

- Detail 1
- Detail 2
EOF
)"
```

## Commit Scope

| Context | Commit Strategy |
|---------|-----------------|
| Working on subissue | Assume parallelism. Commit and push independently. |
| Working on epic directly | One atomic commit for entire epic. |
| Conflict detected | Only ask if same file modified by another in-progress subissue. |

For epics worked directly (not via subissues):
- Close all subissues before closing epic
- Reference epic number in commit message

## Exclusions

Never commit:
- `.DS_Store`, `__pycache__/`, `*.pyc`
- `cache/` directory
- Credentials or secrets
- `.claude/settings.local.json`
