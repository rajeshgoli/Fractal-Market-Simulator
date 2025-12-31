# Process Updates

Revision history for workflow system changes.

---

## 2025-12-31: Migrated to Official Skills Format

**Triggered by:** Analysis of 2,947 prompts revealed 80%+ of repeated user corrections could be eliminated by proper skill triggering.

**Root Cause:** Skills existed (`.claude/commands/`) but agents didn't use them automatically. The problem was trigger enforcement, not skill definition.

**Changes Made:**

1. **Created `.claude/skills/` with 5 official-format skills:**
   - `handoff/SKILL.md` — One-sentence role transfer
   - `doc_update/SKILL.md` — Reference doc updates with routing rules
   - `push_changes/SKILL.md` — Commit and push with scope rules
   - `file_issue/SKILL.md` — GitHub issue creation with templates
   - `diagnose_feedback/SKILL.md` — Investigation protocol with no-speculation rule

2. **Updated persona files with mandatory skill invocation:**
   - `engineer.md` — Added Issue Pickup Protocol and Task Completion Protocol (test → doc_update → push_changes → close → handoff)
   - `architect.md` — Added Review Completion Protocol
   - `product.md` — Added Cognitive Mode: Polymath and Spec Interview Protocol

3. **Backed up old commands:** `.claude/commands` → `.claude/commands.bak`

4. **Updated CLAUDE.md:** Added "Available Skills" section with trigger guidance

5. **Archived proposal:** `Docs/Working/skill_workflow_proposal.md` → `Docs/Archive/workflow/`

**Key Design Decisions:**
- Skills are atomic — they never invoke other skills
- Personas define WHEN, skills define HOW
- pending_review updates: +1 per epic, not per subissue
- Subissues commit independently (assume parallelism)

**Expected Impact:** ~80% reduction in repeated user corrections for push/commit, doc updates, handoff format, and investigation speculation.

---

## 2025-12-18: Reinforced pending_review.md Rule in Product Persona

**Triggered by:** Product role again updated `pending_review.md` when filing GitHub issues #131 and #132 (no code changes).

**Root Cause:** The Dec 17 update added rules to `engineer.md` and `_protocols.md`, but `product.md` only had implicit guidance. Product's "What You Do NOT Do" list didn't explicitly forbid touching `pending_review.md`.

**Changes Made:**

1. **`product.md`**: Added to "What You Do NOT Do" section:
   - `Update pending_review.md — this tracks *completed work* awaiting review, not filed issues. Only Engineer updates it after fixing issues.`

**Rationale:** Explicit negative guidance in the same file Product reads. The rule was documented elsewhere but not where Product persona would see it during workflow.

**Impact:** Product role now has explicit "do not" rule in its own persona file.

---

## 2025-12-17: pending_review.md Ownership Rules

**Triggered by:** Product role incorrectly incremented pending_review.md count after filing a GitHub issue (no code change).

**Root Cause:** The rule for when to update pending_review.md count was implicit, not explicit. Product assumed filing an issue counted as a trackable change.

**Changes Made:**

1. **`engineer.md`**: Added "pending_review.md Rules (CRITICAL)" section with explicit table:
   - Engineer: Code change for NEW issue → Increment count, add to list
   - Engineer: Code change for issue ALREADY in list → Add explanation only, NO count change
   - Architect: After review → Reset count to 0, move issues to review history
   - Filing issues (no code) → Do NOT touch
   - Product/Director work → Do NOT touch

2. **`_protocols.md`**: Added "pending_review.md Ownership" section:
   - Only Engineer increments the count
   - Only Architect resets it to 0
   - Added anti-pattern: Non-Engineer/Architect roles modifying pending_review.md

**Rationale:** pending_review.md tracks implemented changes awaiting architect review. Only two roles touch it: Engineer (increment after code) and Architect (reset after review). Filing issues or doing product/director work doesn't create reviewable code changes.

**Impact:** All roles now have explicit guidance. Product/Director know not to touch pending_review.md. Architect knows they only reset to 0 after review.

---

## 2025-12-11: Major Docs Restructure

**Triggered by:** User feedback on doc proliferation. `engineer_notes/` had 17 files, `product_next_steps*.md` had 4 versions.

**Changes Made:**

1. **New Docs structure:**
   ```
   Docs/
   ├── State/       # Single files, overwrite (no proliferation)
   ├── Comms/       # questions.md + archive.md
   ├── Reference/   # Long-lived docs
   └── Archive/     # All old files moved here
   ```

2. **State docs (single file, always current):**
   - `architect_notes.md` - architectural state
   - `product_direction.md` - product state (replaces product_next_steps)
   - `pending_review.md` - review tracking

3. **GitHub Issues replace engineer_notes/*.md:**
   - Tasks tracked as issues
   - Implementation notes as issue comments
   - No more doc proliferation

4. **Cross-role communication:**
   - `Comms/questions.md` - active questions with From/To/Status
   - `Comms/archive.md` - resolved questions
   - Resolver moves question to archive

5. **Reference docs consolidated:**
   - `interview_notes.md` - all interviews in one file (most recent first)
   - `product_north_star.md` - immutable vision
   - `user_guide.md` - user documentation

6. **Updated all personas** for new paths and archiving responsibilities

7. **Added `/handoff` command** to CLAUDE_ADDENDUM.md for consistent handoff format

**Rationale:** Prevent doc proliferation by using state docs (overwrite) and GitHub issues (external tracking) instead of accumulating files.

**Impact on Roles:**
- **Engineer**: Tasks from GitHub issues, notes as issue comments
- **Architect**: Reviews issues, maintains architect_notes.md state
- **Product**: Single product_direction.md, append to interview_notes.md
- **All**: Resolver archives questions, state docs just overwrite

---

## 2025-12-11: Added Role Recognition Guidance to CLAUDE.md

**Triggered by:** User feedback after Claude failed to recognize "As a product manager" as a Product persona invocation

**Changes Made:**
- `CLAUDE.md`: Added "Role Recognition" section under Role-Based Workflows table

**Rationale:** The invocation table showed exact phrases ("As product...") but Claude interpreted "As a product manager, where do you think we are?" as general framing rather than a persona invocation. New guidance:
1. Match role keywords liberally (variants like "product manager", "PM" → Product)
2. When ambiguous, assume the role and state it explicitly rather than proceeding without a persona
3. If uncertain which role fits, ask before proceeding

**Impact:** Future sessions should recognize variant phrasings and default to assuming a role when context suggests one.

---

## 2025-12-11: Added Director to CLAUDE.md

**Triggered by:** User confusion when invoking Director role

**Changes Made:**
- `CLAUDE.md`: Added Director row to Role-Based Workflows table

**Rationale:** CLAUDE.md was missing Director in the role table, causing confusion during invocation. Now aligned with CLAUDE_ADDENDUM.md.

**Impact:** None to existing roles. Director now visible as valid invocation option.

---

## 2025-12-11: Moved process_updates.md to director folder

**Triggered by:** User request to organize Director-specific files

**Changes Made:**
- Moved `.claude/process_updates.md` → `.claude/personas/director/process_updates.md`
- Updated references in `CLAUDE_ADDENDUM.md` (2 locations)
- Updated references in `director.md` (5 locations)
- Fixed file structure diagram in `director.md`

**Rationale:** Groups Director-owned artifacts together under a dedicated folder.

**Impact:** Director workflow unchanged. Path references updated throughout.

---

## 2025-12-11: Added Motivational Preamble to CLAUDE.md

**Triggered by:** Director consultation on project motivation

**Changes Made:**
- `CLAUDE.md`: Added "Why This Project Exists" section at top of file
- `CLAUDE.md`: Added "To Claude" section with invitation framing

**Rationale:** The project lacked a clear "why" that would orient all roles toward the real stakes. Technical documentation alone doesn't convey that precision matters because it's pointed at someone's freedom—not abstract quality standards.

**Design choice:** Used metta (loving-kindness) framing rather than threats or demands. The invitation assumes capacity for good work rather than coercing it.

**Impact:** Every Claude session now receives project motivation before technical details. Sets quality expectations through meaning rather than obligation.

---

## 2025-12-11: Checkpoint Triggers and Fitness-for-Purpose Protocol

**Triggered by:** Dec 11 interview feedback - user spent full day on validation, found tool unfit for purpose. Meta-feedback: "Engineer was reactive, Product was absent."

**Root Cause Analysis:**
- Product defined success criteria but not usability criteria
- Engineer pulled from GitHub issues without reference to product goal
- Architect reviewed for correctness but not fitness-for-purpose
- No checkpoint existed to catch fit-for-purpose issues early in usage

**Key Constraint Identified:** Agents are reactive by design. "Product should check back" is meaningless—only user can invoke roles. Solution must work within this constraint.

**Changes Made:**

1. `product.md`: Added to output template:
   - **Usability Criteria** section (speed, clarity, reliability)
   - **Checkpoint Trigger** section (when user should invoke Product for fit-for-purpose review)

2. `engineer.md`: Added workflow step 2:
   - **Filter by Product Goal**: Check product_direction.md, prioritize issues serving stated goal

3. `architect.md`: Added workflow step 3:
   - **Fitness Check**: Verify work serves stated Product objective and usability criteria

4. Added MCP server question to `Docs/Comms/questions.md`:
   - MCP server scoping question for Product to reason about
   - Could enable Product to directly experience the tool

**Rationale:** Since agents can't be proactive, artifacts must explicitly prompt coordination. Product now defines when to invoke Product. Engineer now filters by product direction. Architect now validates fitness, not just correctness.

**Impact on Roles:**
- **Product**: Must think about usability and checkpoint timing at handoff
- **Engineer**: Must consult product_direction.md before selecting issues
- **Architect**: Must verify fitness-for-purpose during review
- **User**: Sees explicit checkpoint triggers in product artifacts

**Open Thread:** MCP server for Product direct tool access—delegated to Product for assessment.

---

## 2025-12-12: Handoff Sentence Enforcement

**Triggered by:** User feedback that `/handoff` produces paragraphs instead of single sentences. Handoffs were verbose explanations rather than crisp commands.

**Root Cause:** No mechanism enforced the single-sentence format. Without explicit constraint, Claude defaults to helpful verbosity.

**Changes Made:**

1. **Created `.claude/commands/handoff.md`:**
   - Explicit instruction: "Output ONLY a single sentence"
   - Format template: `As [role], read [artifact] and [action].`
   - Pre-flight checklist: verify docs are complete before handoff
   - Rule: "If you need to explain something, you haven't finished writing to docs"

2. **Updated `CLAUDE_ADDENDUM.md` Handoff Protocol:**
   - Introduced two-phase model:
     - Phase 1: Document everything (before handoff)
     - Phase 2: Output handoff sentence (via `/handoff`)
   - Added concrete examples
   - Reinforced: no paragraphs, no explanations

**Design Principle:** All context belongs in docs/issues. The handoff is just a pointer. If the sentence isn't self-sufficient, the preceding documentation work is incomplete.

**Impact:** `/handoff` command now produces copy-pasteable single sentence that the user can paste directly to invoke the next role.

---

## 2025-12-22: Feedback Investigation Protocol for Engineer

**Triggered by:** User feedback that engineers were speculating about root causes by reading code instead of executing against real data.

**Root Cause:** No explicit guidance existed for investigating observations from `ground_truth/playback_feedback.json`. Engineers could theorize from code reading without verifying behavior through execution.

**Changes Made:**

1. **`engineer.md`**: Added "Feedback Investigation Protocol (CRITICAL)" section with 5-step process:
   - Never speculate — no theorizing from code reading alone
   - Execute against real data — use `csv_index` from feedback entry
   - Use investigation harnesses — reference to `scripts/investigate_leg.py` + guidance to build new ones
   - Inspect execution logs — only analyze after observing actual behavior
   - Report findings — provide analysis based on observation, not assumption

2. Added example command showing real usage of the investigation harness

**Rationale:** Speculation creates false confidence. The existing harness (`scripts/investigate_leg.py`) exists precisely to trace what actually happened. Engineers must use execution + logs to understand behavior, not guess from static code analysis.

**Impact:** Engineer role now has explicit protocol for feedback investigation. Must execute before analyzing.
