# Role-Based Workflow System

This project uses persona-based workflows for structured development. Each role has specific responsibilities, artifacts, and handoff protocols.

## Invoking Roles

When asked to work as a specific role, read `.claude/personas/[role].md` first.

| Role | Invocation | Primary Artifacts |
|------|------------|-------------------|
| Engineer | "As engineer..." | `engineer_notes/`, code |
| Architect | "As architect..." | `architect_notes.md`, `engineer_next_step.md` |
| Product | "As product..." | `product_next_steps.md`, interview notes |
| Director | "As director..." | `.claude/personas/*` (workflow system) |

## Workflow Artifact Ownership

**Only Director may modify workflow system files:**
- `.claude/CLAUDE_ADDENDUM.md`
- `.claude/personas/*.md`
- `.claude/personas/director/process_updates.md`

Other roles must escalate process issues to Director.

## Context is Precious

Persona files are kept lean. Full system details live in `director.md`.
Revision history tracked in `personas/director/process_updates.md`.

## Critical Context Rules

Context is a precious resource. All roles must:
1. Keep primary artifacts forward-looking and self-contained
2. Move historical content to appendix/archive files
3. Write for the next reader who has no prior context
4. Avoid duplication across artifacts

## Handoff Protocol

Every task ends with explicit handoff:
1. State what was completed
2. Declare next step owner (Engineer, Architect, or Product)
3. Update the appropriate artifact for that owner
4. **Include Instruction** - actionable directive ready to send to agent
5. Ensure receiving role can start immediately without archaeology

## /handoff

When you've completed your work and written everything the next agent needs into a doc, output:

```
As [next role], read [doc you just authored] and [action you identified].
```

The next agent should be able to start immediately from that instruction with no additional context.

## Change Tracking

Engineer maintains `Docs/engineer_notes/PENDING_REVIEW.md`:
- Tracks all changes since last architect review
- **If count reaches 5 → Architect review is FORCED**
- Only Architect can reset count to 0

## Artifact Locations

```
Docs/
├── Architect/
│   ├── architect_notes.md           # Forward-looking, comprehensive
│   ├── architect_notes_appendix.md  # Historical decisions
│   └── engineer_next_step.md        # Current engineering task (milestone work)
├── Product/
│   ├── Product North Star.md        # Immutable vision (read-only)
│   ├── Tactical/
│   │   └── product_next_steps.md    # Current product direction
│   ├── Interview notes/
│   └── user_guide.md                # User-facing documentation
├── engineer_notes/
│   ├── PENDING_REVIEW.md            # Change tracking (critical)
│   └── <task>_<date>.md             # Engineer deliverables
└── engineer_reports/                 # Detailed implementation reports
```
