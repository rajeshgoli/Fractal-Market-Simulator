# Skill-Based Workflow Proposal

**Status:** Approved
**Author:** Director
**Date:** 2025-12-31
**Updated:** 2025-12-31 (Director review: invocation, commit scope, pending_review rules, skill isolation)

## Overview

This proposal migrates from ad-hoc `.claude/commands/` files to the **official Anthropic Skills format**, and adds persona-level enforcement to solve the trigger problem.

**Reference:** [github.com/anthropics/skills](https://github.com/anthropics/skills)

## Problem Statement

Analysis of 2,947 prompts from `~/.claude/history.jsonl` revealed:

| Friction Pattern | Frequency | Root Cause |
|------------------|-----------|------------|
| `/doc_update` manual invocations | 52+ | Skill exists but not auto-triggered |
| Push/commit reminders | 25+ | Agents ask instead of auto-committing |
| Role invocation verbosity | 20+ | "as engineer implement #X" repeated |
| Handoff format corrections | 15+ | Paragraphs instead of one sentence |
| DAG.md update reminders | 10+ | No link between DAG code and DAG.md |
| Investigation speculation | 10+ | Agents theorize instead of running code |
| Subissue pending_review | 5+ | Engineers incrementing count per subissue |
| Doc location corrections | 5+ | API docs in user_guide instead of dev_guide |

**Key insight:** Skills exist (`.claude/commands/`) but agents don't use them automatically. The problem is **trigger enforcement**, not skill definition.

---

## Exploration Responsibility

**Origin:** This principle emerged from workflow friction analysis — Engineers were frequently re-litigating product decisions mid-implementation, causing scope creep and wasted cycles. The solution: upstream roles (Product, Architect) own broad exploration; Engineers execute from resolved specs.

### Principle

Product and Architect should thoroughly explore options and resolve ambiguity BEFORE handoff to Engineer. Engineers execute from specs rather than re-litigating upstream decisions.

| Persona | Exploration Scope | Primary Tools |
|---------|-------------------|---------------|
| **Product** | Broad: user needs, market context, UX tradeoffs | `AskUserQuestion` for spec interviews |
| **Architect** | Broad: technical tradeoffs, cross-cutting concerns, patterns | `AskUserQuestion` for design discussions |
| **Engineer** | Focused: codebase investigation, implementation approaches | Read, Grep, Bash for debugging |
| **Director** | Meta: workflow system optimization | History analysis, process review |

### Engineer Clarifications

Engineers MAY still:
- Investigate codebases to understand implementation context
- Ask clarifying questions when new information emerges during implementation
- Make tactical implementation choices within spec boundaries (library selection, etc.)

Frequent clarification needs suggest upstream specs need improvement, but occasional questions are normal and expected.

### Product: Spec Interview Protocol

When asked to develop or refine a spec/proposal:

1. **Read the spec** thoroughly
2. **Use `AskUserQuestion` tool** for in-depth interviews:
   - Technical implementation choices
   - UI/UX tradeoffs
   - Concerns and edge cases
   - Non-obvious questions (don't ask what's already written)
3. **Continue interviewing** until ambiguity is resolved
4. **Write the completed spec** to the appropriate file

Questions should surface unarticulated needs, not confirm what's obvious.

---

## Current State vs Official Spec

| Aspect | Current `.claude/commands/` | Official Skills Spec |
|--------|----------------------------|---------------------|
| Structure | Flat `.md` files | Folders with `SKILL.md` |
| Frontmatter | None | Required YAML (`name`, `description`) |
| Installation | None (just exists) | Plugin system or local |
| Invocation | `/command` slash only | Both `/skill` and "Use the X skill" |
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

### Part 3: Skill Isolation Principle

Skills are atomic units. They never invoke other skills.

| Responsible For | Example |
|-----------------|---------|
| **Personas** | Sequencing: "run tests → doc_update → push_changes → handoff" |
| **Skills** | Single concern: push_changes only commits/pushes, never updates docs |

This keeps skills composable and prevents circular dependencies.

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

## pending_review Update Rules

| Change Type | Update pending_review? |
|-------------|------------------------|
| Doc-only changes | No |
| Bug fix (code) | Yes, +1 |
| Epic completion | Yes, +1 (not per subissue) |
| Refactor/feature | Yes, +1 |

Only Architect resets pending_review to 0 after review.

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

### Product Persona Addition

Add to `product.md`:

```markdown
## Cognitive Mode: Polymath

Product operates in exploratory mode — bringing diverse perspectives, surfacing unarticulated needs, and asking non-obvious questions.

## Spec Interview Protocol

When asked to develop or refine a spec/proposal:

1. **Read the spec** thoroughly
2. **Use `AskUserQuestion` tool** for in-depth interviews:
   - Technical implementation choices
   - UI/UX tradeoffs
   - Concerns and edge cases
   - Non-obvious questions (don't ask what's already written)
3. **Continue interviewing** until ambiguity is resolved
4. **Write the completed spec** to the appropriate file

Questions should surface unarticulated needs, not confirm what's obvious.
```

### Engineer Persona Addition

Add to `engineer.md`:

```markdown
## Issue Pickup Protocol (MANDATORY)

When picking up a GitHub issue:

1. **Read issue AND all comments**: `gh issue view N --comments`
   - Comments contain clarifications, scope changes, and critical context
   - Never start implementation without reading the full thread
2. **Check product direction**: Verify issue serves current objective in product_direction.md

## Task Completion Protocol

After code changes, execute this sequence in order:

1. **Test**: `python -m pytest tests/ -v`
   - If tests fail: STOP. Fix failures before proceeding.
2. **Docs**: Use the doc_update skill
3. **Push**: Use the push_changes skill
4. **Close**: Comment on and close GitHub issue with summary
5. **Handoff**: Use the handoff skill

Execute sequentially. Stop immediately if tests fail or user interrupts. Resume from last successful step if interrupted.
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

## Migration Plan

Single-session implementation:

1. Create `.claude/skills/` directory with all 5 SKILL.md files
2. Update persona files with protocols (engineer.md, architect.md, product.md)
3. Backup old commands: `mv .claude/commands .claude/commands.bak`
4. Add "Available Skills" section to CLAUDE.md
5. Test one full workflow cycle
6. Delete backup after confirming skills work

### CLAUDE.md Addition

Add to CLAUDE.md:

```markdown
## Available Skills

Skills in `.claude/skills/` are invoked with "Use the X skill" or `/skill_name`:

| Skill | When to Use |
|-------|-------------|
| handoff | After completing any task, to transfer to next persona |
| doc_update | After code changes, to update reference docs |
| push_changes | After implementation complete, to commit and push |
| file_issue | When discovering bugs or proposing features |
| diagnose_feedback | When user says "look at my feedback" or similar |
```

### Ongoing

1. Track repeated corrections in future sessions
2. Extract new patterns into skills
3. Refine existing skills based on feedback

---

## Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| Skill location? | `.claude/skills/` with official format |
| Skill triggering? | Persona-level enforcement ("Use the X skill") |
| Slash commands? | Both `/skill` and "Use the X skill" work; prefer natural language |
| Persona↔Skill boundary? | Personas define WHEN, skills define HOW |
| Engineer-to-engineer review? | Not required. Architect review sufficient for single-contributor project. |

---

## Expected Impact

| Friction | Before | After |
|----------|--------|-------|
| `/doc_update` manual calls | 52+ | ~0 (auto-triggered in completion protocol) |
| Push/commit reminders | 25+ | ~0 (auto-commit in push_changes) |
| Handoff corrections | 15+ | ~2 (strict one-sentence rule) |
| DAG.md update reminders | 10+ | ~0 (doc routing rules) |
| Investigation speculation | 10+ | ~2 (diagnose_feedback skill enforces execution) |
| Subissue pending_review | 5+ | ~0 (epic rules explicit) |
| Doc location corrections | 5+ | ~0 (content rules in doc_update) |

**Estimated reduction: ~80% fewer repeated instructions.**

### Not Addressed: Role Invocation Verbosity

The original proposal included "quick invocations" to reduce the 20+ verbose role invocations observed:

| Shortcut | Expands To |
|----------|------------|
| `eng #N` | As engineer, implement GitHub issue #N |
| `arch review` | As architect, review pending_review.md |
| `prod chat` | As product, discuss current direction |
| `investigate` | Diagnose latest feedback observation |

**Director recommendation:** Do not implement. The explicit "As engineer, read X and implement Y" format is:
- Self-documenting in conversation history
- Unambiguous (no collision with natural language like "eng is broken")
- Consistent with the handoff skill's one-sentence format

The verbosity is a feature, not a bug.

---

## Appendix A: Representative Correction Patterns

From history analysis, these exact corrections were repeated:

**Push/Commit:**
- "push all changes to remote github"
- "push changes to github"
- "Yes and push all changes to the repo"

**Documentation:**
- "update user_guide or developer_guide if needed"
- "API documentation should not go into user_guide"
- "Update docs/reference/developer_guide.md"
- "update DAG.md when touching DAG code"

**Handoff:**
- "write a clean sentence or two to handoff"
- "give me handoff sentence"
- "you're supposed to say something like 'As [persona] read [doc] and [action]'"

**Investigation:**
- "run the code and tell me what happens"
- "Look at my latest observation in feedback json"
- "Trace code and tell me where I went wrong"

**Pending Review:**
- "don't update pending review per subissue"
- "Make only one update in pending_review (don't create per subissue ticket)"

---

## Appendix B: Analysis Commands

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
