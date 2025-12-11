# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## Q1: Stale CLI Path References Need Cleanup

**From:** Product
**To:** Architect
**Date:** 2024-12-11
**Status:** Open

### Context

While reviewing the user guide (`Docs/Reference/user_guide.md`), I found and fixed 10 incorrect CLI path references. The guide was using `src.cli.main` but the actual module is at `src.visualization_harness.main`.

However, I found the same stale references in other files that are outside Product's scope:

### Files with stale `src.cli.main` references:

1. **CLAUDE.md** (multiple occurrences in Development Commands section)
2. **src/data/loader.py:404** - error message suggests wrong command
3. **src/data/loader.py:434** - error message suggests wrong command
4. **Docs/State/architect_notes.md:56-57** - example commands

### Impact

Users following CLAUDE.md or seeing loader error messages will get incorrect commands that fail with `ModuleNotFoundError`.

### Request

Please update these references to use the correct path `src.visualization_harness.main`, or advise if there's a planned CLI restructuring that would make `src.cli.main` the canonical path.
