# Active Questions

Questions between roles. When resolved, move to `archive.md` with resolution.

---

## Q-2025-12-31-1: Dual Cache Technical Debt

**From:** Engineer
**To:** Architect
**Date:** 2025-12-31
**Context:** Issue #409 fix revealed cache architecture problem

### Problem

The backend has two parallel caches that aren't synchronized:

1. **Dict cache** (`_replay_cache` in `replay.py`)
   - Where events are actually stored: `_replay_cache["lifecycle_events"].append(...)`
   - Used by `replay.py` for all writes

2. **Dataclass cache** (`ReplayCache` in `cache.py`)
   - Intended as the "proper" typed cache
   - Has sync functions (`_sync_dict_to_cache`, `_sync_cache_to_dict`) but they're never called
   - `get_cache()` returns this, but it's always stale

### Evidence

From `cache.py:74-76`:
```python
# Legacy dict-style access for backward compatibility during migration
# Maps to the ReplayCache dataclass fields
_replay_cache: Dict[str, Any] = {}
```

The migration was started but never completed.

### Impact

- #409 was broken because the new endpoint used `get_cache()` (empty) instead of `_replay_cache` (has data)
- Any future code using `get_cache()` will hit the same issue
- Confusing for developers - two caches, unclear which to use

### Options

1. **Complete migration to dataclass**: Update `replay.py` to use `_cache` directly, remove dict
2. **Auto-sync**: Call sync functions after each modification (adds overhead)
3. **Remove dataclass**: Keep dict, delete unused dataclass code
4. **Status quo**: Document which cache to use where (not recommended)

### Question

Should we file an issue to clean this up? If so, which approach?

---
