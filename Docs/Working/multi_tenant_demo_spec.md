# Multi-tenant Demo Spec

**Status:** Architect reviewed — ready for epic filing
**Created:** January 3, 2026
**Owner:** Product

---

## Overview

Minimal multi-tenant capability to host the Market Simulator as a shareable demo. Portfolio piece — a live app to point to.

---

## Requirements

### Authentication

| Requirement | Details |
|-------------|---------|
| Login required | No guest/anonymous access |
| Primary provider | Google OAuth |
| Secondary provider | GitHub OAuth (if not expensive to add) |
| Fallback | Google-only is acceptable if GitHub adds significant complexity |

### Data

| Requirement | Details |
|-------------|---------|
| Instrument | ES (E-mini S&P 500) |
| Timeframe | 30-minute bars |
| Range | Maximum allowed by hosting constraints |
| Access | Read-only, fixed dataset (no user uploads) |

### Session & State

| Requirement | Details |
|-------------|---------|
| Isolation | Per-user session |
| Persistence | Config/position in localStorage, observations in SQLite |

### Hosting

| Requirement | Details |
|-------------|---------|
| Platform | Fly.io (free tier preferred) |
| Budget | $0-20/month (stay in free tier if possible) |
| Scale | 10-20 concurrent users |
| Database | SQLite (persistent volume) |

### Deployment

| Requirement | Details |
|-------------|---------|
| Trigger | Push to `main` branch |
| Action | Auto-deploy to production |
| Domain | `fractal.rajeshgo.li` (subdomain) |
| DNS | Needs configuration (main site is WordPress at rajeshgo.li) |

### MVP Scope

**Everything that works locally should work hosted.**

Core functionality required:
- Login with Google (+ GitHub if feasible)
- Load ES 30-min data
- Full playback (play/pause/scrub)
- DAG visualization with all current features
- Reference layer with all current features
- Config panels (DAG config, reference config)
- Structure panel
- Observation panel (per-user observations in SQLite)
- All display settings

---

## Architect Answers (Jan 3, 2026)

### 1. Fly.io Setup: FastAPI + React

**Approach:** Single container, single uvicorn worker.

- Multi-stage Dockerfile: Node builds React → Python serves static + API
- Free tier (256MB) is borderline for 222K bars (~50MB parsed) — monitor memory
- If tight, upgrade to 512MB ($3/month)

### 2. SQLite on Fly.io

**Gotchas:**
- Volumes attach to ONE machine only — no horizontal scaling
- Use single worker (no gunicorn with multiple processes)
- Enable WAL mode for better read concurrency

**Setup:**
```bash
fly volumes create fractal_data --size 1 --region sjc
```
Mount at `/data`. Store SQLite + CSV there.

### 3. OAuth Libraries

**Recommended:** `authlib` (mature, FastAPI-compatible)

```python
from authlib.integrations.starlette_client import OAuth
oauth = OAuth()
oauth.register("google", ...)
oauth.register("github", ...)  # +30 lines, same pattern
```

GitHub is cheap to add — include it.

### 4. Data Storage

- ES 30-min: 12MB, 222K bars (~18 years)
- Fly.io free tier: 3GB storage
- **Not a constraint.** Load CSV once, share in memory.

### 5. Session Management

**SQLite schema:**
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE observations (
    id INTEGER PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    bar_index INTEGER,
    event_context TEXT,  -- JSON
    text TEXT,
    screenshot BLOB,     -- PNG bytes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Legacy cleanup:** Delete `ground_truth/` directory (playback_feedback.json, screenshots/). File-based feedback replaced by SQLite in multi-tenant mode. Local mode should also use SQLite for consistency.

**Storage split:**
- **Auth:** JWT in httpOnly cookie (user identity)
- **Config/position:** localStorage (current behavior, no migration)
- **Observations:** SQLite (per-user, queryable for demo)

**Observation LRU:** Keep only latest 20 per user. Cleanup on insert (no background job). Prevents screenshot bloat.

Stateless requests — detector state created per-request from localStorage config.

### 6. CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

---

## Recommended Architecture

```
┌─────────────────────────────────────────┐
│            Fly.io (sjc region)          │
│  ┌────────────────────────────────────┐ │
│  │  Single Container (256-512MB)      │ │
│  │  uvicorn --workers 1               │ │
│  │  ├─ /api/* → FastAPI               │ │
│  │  └─ /*     → React static          │ │
│  │                                    │ │
│  │  Volume: /data                     │ │
│  │  ├─ fractal.db (SQLite)           │ │
│  │  └─ es-30m.csv (12MB)             │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

---

## Implementation Phases

| Phase | Scope | Deliverable |
|-------|-------|-------------|
| **P1** | Container + Serving | Dockerfile, fly.toml, static serving works |
| **P2** | Data + Volume | Persistent volume, CSV loads, API works |
| **P3** | Auth | Google OAuth (+ GitHub), SQLite users table |
| **P4** | Persistence | Observations to SQLite (per-user) |

Sequential execution required (each depends on prior).

**Note:** Config/position stay in localStorage (current behavior). Only observations move to SQLite.

---

## Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Memory pressure (256MB) | Medium | Monitor; upgrade to 512MB if needed ($3/mo) |
| SQLite write contention | Low | Single worker + WAL mode |
| Cold start latency | Low | Health check warmup |
| OAuth secret exposure | Low | `fly secrets set` |

---

## Gaps to Address

1. **Error pages** — OAuth failure, 404, 500
2. **Session expiry** — 7 days recommended
3. **Data upload** — Manual via `fly ssh sftp` or baked into image
4. **DNS** — CNAME `fractal.rajeshgo.li` → Fly.io app hostname

---

## Breaking Changes (Accepted)

### 1. `--data-dir` Required

**Before:** Server discovers data files via hardcoded paths or prompts.

**After:** `--data-dir` is mandatory. No fallback.

```bash
# Local development
python -m src.replay_server.main --data-dir ./test_data

# Production (Fly.io)
python -m src.replay_server.main --data-dir /data
```

**Rationale:** Clean separation. No magic paths. Explicit is better than implicit.

### 2. File Picker Conditional

**Local mode (`MULTI_TENANT=false` or unset):** File picker works as today.

**Multi-tenant mode (`MULTI_TENANT=true`):** No picker. Data file pre-configured from `--data-dir`.

**Both modes:** Start date selection within the loaded file.

**Rationale:** Local dev needs flexibility. Multi-tenant users get fixed dataset (ES 30-min).

---

## Out of Scope

- User uploads / custom data
- Multi-instrument support
- User management / admin panel
- Rate limiting (trust small audience)

---

## Success Criteria

- [ ] Can access `fractal.rajeshgo.li` from browser
- [ ] Login with Google works
- [ ] ES 30-min data loads and plays back
- [ ] All visualization features work as they do locally
- [ ] Config changes persist across sessions
- [ ] Push to main auto-deploys

---

## Next Steps

1. Architect reviews and answers open questions
2. Architect proposes implementation approach
3. Epic filed with sub-issues
4. Engineer implements
