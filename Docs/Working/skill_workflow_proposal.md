# Skill-Based Workflow Proposal

**Status:** Ready for Implementation
**Author:** Director
**Date:** 2025-12-31
**Updated:** 2025-12-31 (aligned with official Anthropic Skills spec)

## Overview

This proposal migrates from ad-hoc `.claude/commands/` files to the **official Anthropic Skills format**, and adds persona-level enforcement to solve the trigger problem.

**Reference:** [github.com/anthropics/skills](https://github.com/anthropics/skills)

## Problem Statement

Analysis of 2,947 prompts from `~/.claude/history.jsonl` revealed:

| Friction Pattern | Frequency | Root Cause |
|------------------|-----------|------------|
| Push changes requests | 244 | Skill exists but not auto-invoked |
| Doc update reminders | 145 | Skill exists but not auto-invoked |
| Handoff corrections | 69 | Output format not enforced |
| Issue filing requests | 82 | No streamlined skill |
| Role invocation verbosity | 521 | No shortcuts |
| Feedback investigation | 45 | No dedicated skill |

**Key insight:** Skills exist (`.claude/commands/`) but agents don't use them automatically. The problem is **trigger enforcement**, not skill definition.

## Current State vs Official Spec

| Aspect | Current `.claude/commands/` | Official Skills Spec |
|--------|----------------------------|---------------------|
| Structure | Flat `.md` files | Folders with `SKILL.md` |
| Frontmatter | None | Required YAML (`name`, `description`) |
| Installation | None (just exists) | Plugin system or local |
| Invocation | `/command` slash | "Use the X skill..." |
| Discovery | Manual | Description-based |

## Solution: Two-Part Fix

### Part 1: Adopt Official Skills Format

Migrate to proper skills structure:

```
.claude/skills/
├── handoff/
│   └── SKILL.md
├── doc_update/
│   └── SKILL.md
├── push_changes/
│   └── SKILL.md
├── file_issue/
│   └── SKILL.md
└── diagnose_feedback/
    └── SKILL.md
```

### Part 2: Persona-Level Enforcement

Add mandatory skill invocation to personas. Skills only work if agents know WHEN to use them.

---

## Skill Specifications (Official Format)

### Skill 1: handoff

```
.claude/skills/handoff/
└── SKILL.md
```

**SKILL.md:**
```markdown
---
name: handoff
description: Execute structured handoff between roles. Use after completing ANY
  task to transfer work to the next persona. Outputs exactly ONE sentence in
  format "As [role], read [artifact] and [action]." No preamble. No explanation.
---

# Handoff

Output EXACTLY ONE LINE. Zero preamble. Zero explanation.

## Format

```
As [role], read [artifact] and [action].
```

## Rules

1. **One sentence only.** If you have more to say, write it to docs first.
2. **[role]** = engineer | architect | product | director
3. **[artifact]** = the doc you just updated OR the GitHub issue you just created
4. **[action]** = specific verb (implement, review, assess, diagnose)

## Examples

```
As engineer, read GitHub issue #31 and implement the CSV export feature.
```

```
As architect, read Docs/State/pending_review.md and review the 10 accumulated changes.
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
```

---

### Skill 2: doc_update

```
.claude/skills/doc_update/
└── SKILL.md
```

**SKILL.md:**
```markdown
---
name: doc_update
description: Update reference documentation after code changes. Use after
  completing implementation. Determines which docs need updates based on what
  code changed. Respects role ownership boundaries.
---

# Doc Update

## Role Ownership

Only update docs you own:

| Role | Can Update |
|------|------------|
| Engineer | user_guide.md, developer_guide.md, DAG.md, pending_review.md |
| Architect | architect_notes.md, pending_review.md (reset only) |
| Product | product_direction.md, interview_notes.md |
| Director | .claude/personas/*, .claude/skills/* |

## Doc Routing Rules

| Code Changed | Doc to Update |
|--------------|---------------|
| `src/swing_analysis/dag/*` | Docs/Reference/DAG.md |
| API endpoints | Docs/Reference/developer_guide.md |
| Architecture/implementation | Docs/Reference/developer_guide.md |
| User-facing behavior | Docs/Reference/user_guide.md |
| CLI arguments/options | Docs/Reference/user_guide.md |

## Content Rules

### user_guide.md
- How to USE the product
- CLI commands and options
- User workflows
- **NEVER include:** API endpoints, implementation details

### developer_guide.md
- API documentation
- Architecture overview
- Implementation details
- Setup instructions

### DAG.md
- DAG node types and relationships
- Pruning algorithms
- Formation/extension logic

## Cross-Role Requests

If another role's docs need updating, add to `Docs/Comms/questions.md`:

```markdown
### YYYY-MM-DD - Doc Update Request
- **From:** [your role]
- **To:** [target role]
- **Request:** [doc] needs update to reflect [change]
```
```

---

### Skill 3: push_changes

```
.claude/skills/push_changes/
└── SKILL.md
```

**SKILL.md:**
```markdown
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

## Epic Rules

For epics with multiple subissues:
- **ONE commit for entire epic** — not per subissue
- Close all subissues before closing epic
- Reference epic number in commit message

## Exclusions

Never commit:
- `.DS_Store`, `__pycache__/`, `*.pyc`
- `cache/` directory
- Credentials or secrets
- `.claude/settings.local.json`
```

---

### Skill 4: file_issue

```
.claude/skills/file_issue/
└── SKILL.md
```

**SKILL.md:**
```markdown
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
```

---

### Skill 5: diagnose_feedback

```
.claude/skills/diagnose_feedback/
└── SKILL.md
```

**SKILL.md:**
```markdown
---
name: diagnose_feedback
description: Investigate user observations from playback feedback. Use when
  user says "look at my feedback", "check my latest observation", or "diagnose
  why". Reads feedback JSON, loads actual data, traces code execution. Never
  speculates — always executes against real data.
---

# Diagnose Feedback

## CRITICAL: No Speculation

**Never theorize by reading code alone.** Execute against real data and observe.

## Feedback Location

`ground_truth/playback_feedback.json`

## Observation Structure

```json
{
  "observation_id": "uuid",
  "text": "user's question",
  "playback_bar": 12345,
  "snapshot": {
    "dag_context": {
      "active_legs": [...],
      "pending_origins": {...}
    },
    "attachments": [...],
    "detection_config": {...}
  }
}
```

## Procedure

1. Read latest observation (or specific ID if provided)
2. Parse user's question from `text` field
3. Extract context: attached legs, config parameters, bar indices
4. Load price data from CSV (semicolon-delimited, no header)
5. Run investigation harness with actual data:
   ```bash
   python scripts/investigate_leg.py --file test_data/es-5m.csv \
       --offset <csv_index> --origin-price <price> ...
   ```
6. Report findings based on EXECUTION, not assumption

## Common Patterns

| User Question | Investigation |
|---------------|---------------|
| "Why was this leg created?" | Check branch ratio, formation fib, origin conditions |
| "Why was this leg pruned?" | Check proximity, turn ratio, engulfed conditions |
| "Why no bear leg here?" | Check pending origins, counter-trend requirements |

## Trigger Phrases

- "Look at my last feedback"
- "Diagnose my latest observation"
- "Check my latest observation in feedback json"
- "Why did this happen?" (with feedback context)
```

---

## Persona Updates Required

### Engineer Persona Addition

Add to `engineer.md`:

```markdown
## Task Completion Protocol (MANDATORY)

After ANY code change, execute this sequence without stopping:

1. **Test**: `python -m pytest tests/ -v`
2. **Docs**: Use the doc_update skill
3. **Push**: Use the push_changes skill
4. **Close**: Comment on and close GitHub issue with summary
5. **Handoff**: Use the handoff skill

This sequence is ATOMIC. Do not stop between steps.
```

### Architect Persona Addition

Add to `architect.md`:

```markdown
## Review Completion Protocol

After completing review:

1. **Update**: architect_notes.md (forward-looking)
2. **Reset**: pending_review.md count to 0
3. **Create**: GitHub issues for Engineer OR questions for Product
4. **Handoff**: Use the handoff skill with parallelism specified
```

---

## Quick Invocations (CLAUDE.md Addition)

Add to reduce the 521 verbose role invocations:

```markdown
## Quick Role Invocations

| You Say | Agent Understands |
|---------|-------------------|
| `eng #N` | As engineer, implement GitHub issue #N |
| `arch review` | As architect, review pending_review.md |
| `prod chat` | As product, discuss current direction |
| `investigate` | Diagnose latest feedback observation |
```

---

## Migration Plan

### Phase 1: Create Skills (Day 1)

1. Create `.claude/skills/` directory
2. Create all 5 SKILL.md files per specs above
3. Test skill invocation manually

### Phase 2: Update Personas (Day 1)

1. Add Task Completion Protocol to engineer.md
2. Add Review Completion Protocol to architect.md
3. Add skill references to other personas

### Phase 3: Add Quick Invocations (Day 1)

1. Add quick invocations section to CLAUDE.md
2. Test shorthand recognition

### Phase 4: Deprecate Old Commands (Day 2)

1. Delete `.claude/commands/` directory
2. Verify no references remain
3. Test full workflow

### Phase 5: Monitor (Ongoing)

1. Track repeated corrections in future sessions
2. Extract new patterns into skills
3. Refine existing skills based on feedback

---

## Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| Skill location? | `.claude/skills/` with official format |
| Skill triggering? | Persona-level enforcement ("Use the X skill") |
| Slash commands? | Deprecated in favor of "Use the X skill" |
| Persona↔Skill boundary? | Personas define WHEN, skills define HOW |

---

## Expected Impact

| Friction | Before | After |
|----------|--------|-------|
| Push changes requests | 244 | ~0 (persona enforced) |
| Doc update reminders | 145 | ~0 (persona enforced) |
| Handoff corrections | 69 | ~5 (stricter skill) |
| Issue filing requests | 82 | ~10 (new skill) |
| Role invocation | 521 | ~100 (quick invocations) |
| Investigation requests | 45 | ~5 (dedicated skill) |

**Estimated reduction: ~85% fewer repeated instructions.**

---

## Appendix: Analysis Commands

```bash
# Count prompts for this project
grep "fractal-market-simulator" ~/.claude/history.jsonl | wc -l

# Extract prompts
grep "fractal-market-simulator" ~/.claude/history.jsonl | python3 -c "
import json, sys
for line in sys.stdin:
    data = json.loads(line)
    if 'display' in data:
        print(data['display'][:200])
"

# Find correction patterns
grep "fractal-market-simulator" ~/.claude/history.jsonl | python3 -c "
import json, sys
for line in sys.stdin:
    data = json.loads(line)
    p = data.get('display', '').lower()
    if any(kw in p for kw in ['don\\'t', 'do not', 'should be', 'supposed to']):
        print(data['display'][:150])
"
```
