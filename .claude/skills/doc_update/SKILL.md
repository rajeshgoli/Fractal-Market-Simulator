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
