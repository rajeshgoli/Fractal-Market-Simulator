# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## To Architect: P1 UX Fixes for Ground Truth Annotator

**From:** Product
**Date:** December 12, 2025

First real annotation session surfaced 4 issues blocking quality data collection:

1. **Reference level labels inverted** — Bull reference shows 0 at top, 2 below low. Should be 0 at bottom, 2 at `L + 2*(H-L)` (above high). Same fix inverted for bear.

2. **FN explanation too slow** — Currently requires explaining every FN. Add preset options ("Biggest swing I see", "Most impulsive", etc.) and make free-text optional.

3. **Unclear export/save workflow** — User doesn't know if data is auto-saved or requires manual export. Clarify UX: show confirmation on save, make export button prominent if needed.

4. **Session quality control** — No way to mark session as "keep" vs "discard" (practice). Add button at session end.

**Ask:** Can you assess implementation scope and create GitHub issues for these? I'd like to fix before running more annotation sessions.

---
