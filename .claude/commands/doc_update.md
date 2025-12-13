# Doc Update Command

Review and update documentation to reflect changes just completed.

## Role Ownership (CRITICAL)

Only update docs you own. Respect role boundaries:

| Role | Can Update |
|------|------------|
| **Engineer** | `user_guide.md`, `developer_guide.md`, `pending_review.md` |
| **Architect** | `architect_notes.md`, `pending_review.md` (reset only) |
| **Product** | `product_direction.md`, `interview_notes.md` |
| **Director** | `.claude/personas/*`, `.claude/CLAUDE_ADDENDUM.md` |

**If another role's docs need updating:** Add a request to `Docs/Comms/questions.md` for that role to address. Do NOT modify their docs directly.

## What to Check (By Role)

### As Engineer
- **user_guide.md** - User-facing features, CLI options, usage examples
- **developer_guide.md** - Architecture, implementation details, development workflows
- **pending_review.md** - Increment count, add your changes

### As Architect
- **architect_notes.md** - Current system state, technical decisions, next steps
- **pending_review.md** - Reset to 0 after review

### As Product
- **product_direction.md** - Current phase, objectives, acceptance criteria
- **interview_notes.md** - User feedback and insights

### As Director
- `.claude/personas/*.md` - Role definitions
- `.claude/CLAUDE_ADDENDUM.md` - Role system overview

## Workflow

1. **List changes**: What files did you just modify? What behavior changed?
2. **Assess impact by ownership**:
   - Docs you own → Update directly
   - Docs owned by others → Add request to `Docs/Comms/questions.md`
3. **Update your docs**: Make the necessary changes
4. **Queue cross-role requests**: Add to questions.md with format below
5. **Report**: List what was updated and what was queued

## Cross-Role Request Format (questions.md)

```markdown
### YYYY-MM-DD - Doc Update Request
- **From:** [your role]
- **To:** [target role]
- **Status:** Open
- **Request:** [doc] needs update to reflect [change]
- **Context:** [brief explanation of what changed]
```

## Output Format

```
## Documentation Updates

**Role:** [your current role]
**Changes reviewed:** [brief description of work completed]

**Updates made (owned docs):**
- [doc path]: [what was added/changed]

**Requests queued (other roles):**
- To [role]: [doc] needs [update] (added to questions.md)

**No updates needed:**
- [doc path]: [reason still current]

**Handoff needed:** [Yes/No - if critical request queued for another role]
```
