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

Every task ends with explicit handoff. Two-phase process:

**Phase 1: Document everything** (before handoff)
- Write all context, decisions, and details to the appropriate artifact
- If Engineer: update GitHub issue with implementation notes
- If Architect: update `architect_notes.md` or create GitHub issue
- If Product: update `product_direction.md` or `questions.md`

**Phase 2: Output handoff sentence** (use `/handoff` command)

## /handoff

Outputs ONE sentence. No paragraphs. No explanations.

**Format:**
```
As [role], read [artifact] and [action].
```

**Examples:**
```
As engineer, read GitHub issue #31 and implement the two-click annotation.
As architect, read Docs/State/pending_review.md and review accumulated changes.
As product, read Docs/Comms/questions.md and clarify the scope question.
```

**Rule:** If you need to explain something, you haven't finished Phase 1. Write it to a doc first.

## Change Tracking

Engineer maintains `Docs/State/pending_review.md`:
- Tracks changes since last architect review
- Lists GitHub issue numbers
- **If count reaches 10 → Architect review is FORCED**
- Only Architect resets count to 0
