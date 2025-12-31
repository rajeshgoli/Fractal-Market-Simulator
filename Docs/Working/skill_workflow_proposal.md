# Skill-Based Workflow Decomposition Proposal

**Status:** Draft
**Author:** Director
**Date:** 2025-12-31

## Overview

This proposal outlines a transition from monolithic persona definitions to a **persona + skills** model, where personas define role identity and skills encode repeatable procedures.

## Motivation

Analysis of user prompt history (`~/.claude/history.jsonl`) revealed:
- 2,928 prompts for this project
- Repeated corrections for the same workflow rules (10-30 times each)
- Clear patterns that can be encoded as skills

The same instructions are being repeated because they're embedded in ad-hoc prompts rather than encoded in reusable procedures.

## Evidence: Repeated Correction Patterns

### Source Data

User prompts are stored in `~/.claude/history.jsonl` with format:
```json
{
  "display": "prompt text",
  "timestamp": 1765388570619,
  "project": "/Users/rajesh/Desktop/fractal-market-simulator",
  "sessionId": "..."
}
```

### Pattern Analysis

Extract prompts for analysis:
```bash
cat ~/.claude/history.jsonl | python3 -c "
import json, sys
for line in sys.stdin:
    entry = json.loads(line)
    if 'fractal-market-simulator' in entry.get('project', ''):
        print(entry['display'])
"
```

### Top Patterns Identified

| Pattern | Frequency | Example |
|---------|-----------|---------|
| Role invocation | 516 (17.6%) | "assume engineer role" |
| Run tests | 394 (13.5%) | "run tests" |
| Commit/push | 295 (10.1%) | "push changes" |
| Issue work | 141 (4.8%) | "implement #357" |
| Doc updates | 89 (3.0%) | "update user_guide" |
| Feedback diagnosis | 67 (2.3%) | "look at my last feedback", "diagnose why" |

### Repeated Corrections (High-Value Skill Candidates)

#### 1. pending_review Rules (Corrected 10+ times)

User prompts showing repeated corrections:
```
"do not update pending_review for each subissue, only one increment for the whole" (×8)
"Pending review is updated after implementation not before"
"Since this has no code change, do not update pending_review"
"this is still issue 111" (exception for continuation)
```

**Extracted rules:**
- Increment ONLY after implementation completes
- For epics: ONE increment for entire epic, not per subissue
- Skip if: doc-only change, continuation of existing issue, no code change

#### 2. Doc Update Rules (Corrected 20+ times)

User prompts showing repeated corrections:
```
"API documentation should not go into user_guide... should go to developer_guide"
"Docs/reference/DAG.md for updates to how DAG behavior changes"
"Be sure to update user_guide or developer_guide if needed" (×30+)
```

**Extracted rules:**
- `DAG.md` — when touching `src/swing_analysis/dag/*`
- `developer_guide.md` — APIs, architecture, implementation details
- `user_guide.md` — user-facing behavior (NOT APIs)

#### 3. Epic/Commit Rules (Corrected 15+ times)

User prompts showing repeated corrections:
```
"push all changes in one atomic commit" (×12)
"Close all subissues before closing the epic"
"Engineer should fix sub issues sequentially, test, and verify"
"there should be a subissue to update user_guide and developer_guide"
```

**Extracted rules:**
- All changes in one atomic commit at end
- Close subissues before closing epic
- Sequential execution with testing
- Doc update subissue required

## Proposed Architecture

### Current Model
```
Personas (full workflow embedded)
├── engineer.md      ← Contains all procedures inline
├── architect.md     ← Contains all procedures inline
├── product.md
└── director.md
```

### Proposed Model
```
Personas (identity + skill references)    Skills (procedures)
├── engineer.md                           ├── handoff/
├── architect.md                          ├── doc_update/
├── product.md                            ├── push_changes/
└── director.md                           ├── file_issue/
                                          ├── work_issue/
                                          └── process_feedback/
```

Personas become lighter — they define **which skills to invoke when** rather than embedding full procedures.

## Skill Specifications

### Skill 1: `/handoff`

**Purpose:** Execute structured handoff between roles with proper artifact updates.

```
.claude/skills/handoff/
└── SKILL.md
```

**SKILL.md:**
```yaml
---
name: handoff
description: Execute structured handoff between roles. Use when completing work and transferring to another persona. Handles pending_review updates, artifact updates, and handoff instructions.
---

# Handoff

## Procedure

1. Identify handoff type:
   - **Engineer → Architect**: Work ready for review
   - **Architect → Engineer**: Issue filed, ready for implementation
   - **Architect → Product**: Question requiring product input
   - **Product → Architect**: Direction updated, ready for technical breakdown

2. Execute checklist for handoff type:

### Engineer → Architect
- [ ] Tests passing
- [ ] GitHub issue commented with implementation notes
- [ ] `Docs/State/pending_review.md` incremented (see rules below)
- [ ] User guide updated (if user-facing, non-API changes)
- [ ] Developer guide updated (if API/implementation changes)
- [ ] DAG.md updated (if touching dag/* code)

### Architect → Engineer
- [ ] GitHub issue created with clear requirements
- [ ] `Docs/State/architect_notes.md` current
- [ ] Parallelism specified (if multiple issues)

### Architect → Product
- [ ] Question added to `Docs/Comms/questions.md`
- [ ] Context provided (what decision is blocked)

### Product → Architect
- [ ] `Docs/State/product_direction.md` updated
- [ ] Question in `Docs/Comms/questions.md` marked resolved
- [ ] Moved to `Docs/Comms/archive.md`

## pending_review Rules

**When to increment:**
- After implementation completes (not before)
- Only for code changes (skip doc-only changes)

**When NOT to increment:**
- Per subissue — only ONE increment for entire epic
- Continuation of existing issue already in pending_review
- Doc-only or config-only changes

3. Output handoff summary:
   ```
   Handoff: Engineer → Architect
   Completed: #357 (pivot breach pruning)
   Pending review count: 3
   Next action: Review pending changes
   ```

## Blocking Conditions

Do NOT handoff if:
- Tests failing (Engineer)
- pending_review >= 10 (Engineer — Architect must review first)
- Question unanswered (Architect → Engineer on blocked issue)
```

---

### Skill 2: `/doc_update`

**Purpose:** Update reference documentation based on code changes.

```
.claude/skills/doc_update/
└── SKILL.md
```

**SKILL.md:**
```yaml
---
name: doc_update
description: Update reference documentation after code changes. Use after completing implementation to ensure docs are current. Determines which docs need updates based on what code changed.
---

# Doc Update

## Procedure

1. Analyze changes to determine which docs need updates:

| Code Changed | Doc to Update |
|--------------|---------------|
| `src/swing_analysis/dag/*` | `Docs/Reference/DAG.md` |
| Any API endpoints | `Docs/Reference/developer_guide.md` |
| Architecture/implementation | `Docs/Reference/developer_guide.md` |
| User-facing behavior | `Docs/Reference/user_guide.md` |
| CLI arguments/options | `Docs/Reference/user_guide.md` |

2. Doc content rules:

### user_guide.md
- How to USE the product
- CLI commands and options
- User workflows
- **NEVER include:** API endpoints, implementation details

### developer_guide.md
- API documentation
- Architecture overview
- Implementation details
- Setup instructions for developers

### DAG.md
- DAG node types and relationships
- Pruning algorithms
- Formation/extension logic
- Hierarchy rules

3. Update each applicable doc:
   - Read current content
   - Identify outdated sections
   - Update to reflect current behavior
   - Remove deprecated content

4. Verify no stale references remain.
```

---

### Skill 3: `/push_changes`

**Purpose:** Commit and push changes with proper attribution and structure.

```
.claude/skills/push_changes/
└── SKILL.md
```

**SKILL.md:**
```yaml
---
name: push_changes
description: Commit and push changes to GitHub. Use after completing implementation and doc updates. Ensures atomic commits with proper messages. If there are uncommitted changes, commits them first.
---

# Push Changes

## Procedure

1. Check for uncommitted changes:
   ```bash
   git status
   ```

2. If uncommitted changes exist, stage and commit:
   ```bash
   git add -A
   git commit -m "$(cat <<'EOF'
   Brief summary (fixes #NNN)

   - Detail 1
   - Detail 2
   EOF
   )"
   ```

3. Push to remote:
   ```bash
   git push
   ```

## Commit Rules

### For Epics (multiple subissues)
- **ONE commit for entire epic** — not per subissue
- Close all subissues before closing epic
- Reference epic number in commit message

### Commit Message Format
```
Brief summary in imperative mood (fixes #NNN)

- What changed
- Why it changed
- Any notable decisions
```

### What NOT to commit
- `.DS_Store`, `__pycache__/`, `*.pyc`
- `cache/` directory
- Credentials or secrets

## Verification

After push, verify:
```bash
git status  # Should show "nothing to commit"
git log -1  # Verify commit message
```
```

---

### Skill 4: `/file_issue`

**Purpose:** Create GitHub issues with proper structure.

```
.claude/skills/file_issue/
├── SKILL.md
└── references/
    └── issue_templates.md
```

**SKILL.md:**
```yaml
---
name: file_issue
description: File a GitHub issue. Use when any persona needs to create a bug report, feature request, or epic. Handles issue structure, labeling, and cross-references.
---

# File Issue

## Procedure

1. Determine issue type:
   - **Bug**: Unexpected behavior
   - **Feature**: New capability
   - **Epic**: Multi-issue feature

2. For epics, structure as subissues:
   - Break into subissues for separate concerns
   - Each subissue self-contained and testable
   - Include doc subissue: "Update DAG.md, developer_guide.md, user_guide.md as needed"
   - Final instruction in epic: "Push all changes in one atomic commit"
   - Add to epic body: "Do not update pending_review per subissue — one increment for whole epic"

3. Check for duplicates:
   ```bash
   gh issue list --search "<keywords>" --limit 5
   ```

4. Create issue using template from `references/issue_templates.md`

5. For epics, link subissues in epic body.

## Epic Body Template

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
```

**references/issue_templates.md:**
```markdown
# Bug Template

## Description
[What's broken]

## Repro Steps
1. ...

## Expected vs Actual
- Expected: ...
- Actual: ...

---

# Feature Template

## Description
[What capability to add]

## Acceptance Criteria
- [ ] ...

---

# Epic Template

## Overview
[High-level goal]

## Sub-Issues
- [ ] #NNN - [description]
- [ ] #NNN - Update documentation

## Instructions for Engineer
- Fix sub issues sequentially, test and verify each
- Do NOT update pending_review per subissue
- Push all changes in one atomic commit
- Close all subissues before closing epic

## Completion Criteria
All sub-issues closed and verified.
```

---

### Skill 5: `/diagnose_feedback`

**Purpose:** Investigate user observations from playback feedback and diagnose issues.

```
.claude/skills/diagnose_feedback/
└── SKILL.md
```

**SKILL.md:**
```yaml
---
name: diagnose_feedback
description: Investigate user observations from playback feedback. Use when user says "look at my feedback", "check my latest observation", "diagnose why this happened". Reads feedback JSON, analyzes DAG state snapshot, traces through code to explain behavior.
---

# Diagnose Feedback

## Feedback File Structure

Location: `ground_truth/playback_feedback.json`

Each observation contains:
- `observation_id`: UUID for reference
- `text`: User's question/observation
- `playback_bar`: Bar index when observation was made
- `snapshot`: Full state at observation time
  - `dag_context.active_legs`: All active legs with origin/pivot prices and indices
  - `dag_context.pending_origins`: Pending bull/bear origins
  - `attachments`: Specific legs/items user attached to observation
  - `detection_config`: Algorithm parameters in effect
- `created_at`: Timestamp

## Procedure

1. Read latest observation (or specific one if observation_id provided):
   ```
   ground_truth/playback_feedback.json
   ```

2. Parse the user's question from `text` field

3. Extract relevant context from `snapshot`:
   - Attached leg(s) from `attachments`
   - Active legs from `dag_context.active_legs`
   - Config parameters from `detection_config`
   - Bar indices for data lookup

4. Load price data from data file (semicolon-delimited, no header):
   - Format: `date;time;open;high;low;close;volume`
   - Use `csv_index` or calculate from `offset + playback_bar`

5. Trace through code to explain:
   - Why a leg was created/preserved/pruned
   - What threshold was exceeded/not met
   - What the algorithm saw at that bar

6. Present diagnosis to user with:
   - Summary of what happened
   - Specific values (prices, ratios, thresholds)
   - Code path that led to behavior

## Resolution Actions

After diagnosis, user may request:
- **File issue**: Use `/file_issue` with diagnosis details
- **Archive**: Move observation to `ground_truth/resolved_feedback.json`
- **Move screenshot**: Archive corresponding screenshot from `ground_truth/screenshots/`

## Common Diagnosis Patterns

| User Question | Investigation |
|---------------|---------------|
| "Why was this leg created?" | Check branch ratio, formation fib, origin conditions |
| "Why was this leg pruned?" | Check proximity rules, turn ratio, engulfed conditions |
| "Why no bear leg at origin?" | Check pending origins, counter-trend requirements |
| "What was the counter trend?" | Calculate largest opposite-direction move within leg's range |

## Example Prompts That Trigger This Skill

- "Look at my last feedback item"
- "Can you check my latest feedback and diagnose why this problem occurred"
- "Diagnose my latest observation"
- "Look at my last feedback item and tell me why this happened"
- "Check my latest observation in feedback json"
```

---

## Implementation Plan

### Phase 1: Create Skills Directory
1. Create `.claude/skills/` directory structure
2. Implement `/handoff`, `/doc_update`, `/push_changes` (most frequently corrected)
3. Test with engineer workflow

### Phase 2: Update Personas
1. Remove embedded procedures from persona files
2. Add skill references: "Use `/handoff` skill when completing work"
3. Keep role identity and context in personas

### Phase 3: Add Remaining Skills
1. Implement `/file_issue`, `/diagnose_feedback`
2. Consider `/work_issue` for full issue implementation workflow

### Phase 4: Iterate
1. Monitor for new repeated corrections
2. Extract into skills as patterns emerge
3. Update existing skills based on feedback

## Open Questions

1. **Skill installation:** Should skills be in `.claude/skills/` or use Claude Code's plugin system?
2. **Skill triggering:** Auto-trigger based on context vs explicit `/skill` invocation?
3. **Persona↔Skill boundary:** How much context should skills assume vs require?

## Next Steps

1. User approval of this proposal
2. Director implements Phase 1
3. Test with real engineer workflow
4. Iterate based on feedback

---

## Appendix: Raw Prompt Analysis Commands

To reproduce the analysis:

```bash
# Count prompts for this project
cat ~/.claude/history.jsonl | python3 -c "
import json, sys
count = sum(1 for line in sys.stdin
            if 'fractal-market-simulator' in json.loads(line).get('project', ''))
print(f'Total prompts: {count}')
"

# Find repeated correction patterns
cat ~/.claude/history.jsonl | python3 -c "
import json, sys, re
prompts = [json.loads(line)['display'] for line in sys.stdin
           if 'fractal-market-simulator' in json.loads(line).get('project', '')]
# Search for correction keywords
for p in prompts:
    if any(kw in p.lower() for kw in ['don\\'t', 'do not', 'only', 'must']):
        print(p[:200])
"
```
