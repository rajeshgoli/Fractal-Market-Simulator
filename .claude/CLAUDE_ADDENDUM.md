# Role-Based Workflow System

This project uses persona-based workflows for structured development. Each role has specific responsibilities, artifacts, and handoff protocols.

## Invoking Roles

When asked to work as a specific role, read `.claude/personas/[role].md` first.

| Role | Invocation | Primary Artifacts |
|------|------------|-------------------|
| Engineer | "As engineer..." | GitHub issues, code |
| Architect | "As architect..." | `Docs/State/architect_notes.md` |
| Product | "As product..." | `Docs/State/product_direction.md` |
| Director | "As director..." | `.claude/personas/*` |

## Docs Structure

```
Docs/
├── State/              # Current state (single files, overwrite)
│   ├── architect_notes.md
│   ├── product_direction.md
│   └── pending_review.md
├── Comms/              # Cross-role communication
│   ├── questions.md    # Active questions (From, To, Status)
│   └── archive.md      # Resolved questions
└── Reference/          # Long-lived documents
    ├── product_north_star.md
    ├── user_guide.md
    └── interview_notes.md

.archive/               # Local only (not in git) - historical content
```

## Key Principles

**State docs:** Single file, always current, overwrite on update. No date suffixes.

**Tasks:** Engineer work tracked in GitHub issues, not docs.

**Questions:** Cross-role questions in `Docs/Comms/questions.md`.

**Archiving:** The role that resolves a question moves it to `archive.md` with resolution. State docs just get overwritten—no archiving needed.

## Handoff Protocol

Every task ends with explicit handoff:
1. State what was completed
2. Declare next step owner
3. Update the appropriate artifact
4. Include instruction for next agent

## /handoff

When you've completed your work and written everything the next agent needs into a doc, output:

```
As [next role], read [doc you just authored] and [action you identified].
```

The next agent should be able to start immediately from that instruction with no additional context.

## Change Tracking

Engineer maintains `Docs/State/pending_review.md`:
- Tracks changes since last architect review
- Lists GitHub issue numbers
- **If count reaches 5 → Architect review is FORCED**
- Only Architect resets count to 0
