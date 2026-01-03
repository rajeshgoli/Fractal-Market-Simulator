# Frontend Sanity Tests

Manual test workflows to verify core frontend functionality after changes.

---

## Prerequisites

```bash
# Terminal 1: Start backend
source venv/bin/activate
python -m src.replay_server.main

# Terminal 2: Start frontend
cd frontend
npm run dev -- --port 8001
```

Open http://localhost:8001 in browser.

---

## Test 1: Initial Load & Data Selection

**Purpose:** Verify app initializes and data file selection works.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open app in browser | Settings panel opens automatically |
| 2 | Select data file (e.g., `es-30m.csv`) | File appears in dropdown |
| 3 | Click "Apply & Restart" | App loads, header shows file name |
| 4 | Check header | Shows `---` date, `0 bars` initially |

**Pass criteria:** App loads without console errors, data file is selectable.

---

## Test 2: Market Structure View - Warmup & Playback

**Purpose:** Verify basic playback and warmup process.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Ensure "Structural Logs" tab selected | Market Structure View active |
| 2 | Click Play button | Warmup progress bar appears |
| 3 | Wait for warmup | "Warming up... X/50 swings collected" |
| 4 | Warmup completes | Progress bar disappears, playback continues |
| 5 | Observe header | Date/time updates, bar count increases |
| 6 | Click Pause | Playback stops |
| 7 | Check Current Structure panel | Shows Bull Legs, Bear Legs counts |

**Pass criteria:** Warmup completes, legs appear in panel, timestamp updates.

---

## Test 3: Levels at Play View - Basic Function

**Purpose:** Verify Levels at Play view loads and displays references.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Click "Levels at Play" tab | View switches |
| 2 | If not warmed up, play until warmed | Warmup completes |
| 3 | Check Reference Stats panel | Shows Bull/Bear counts, Total References |
| 4 | Check TOP REFERENCES panel | Lists reference entries with prices |
| 5 | Check ON DECK panel | Shows upcoming levels |
| 6 | Observe chart | Reference lines (diagonals) visible |

**Pass criteria:** References display in panels, lines visible on chart.

---

## Test 4: Process Till - Large Advance

**Purpose:** Verify Process Till advances correctly and updates UI state.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Note current state | Record: bar count, Total References, Bull/Bear counts |
| 2 | Click "+10K" button | Target input shows date ~10K bars ahead |
| 3 | Click "Process till target" (>>) | Processing begins |
| 4 | Wait for completion (~3-5s) | Bar count jumps by ~10K |
| 5 | Check header timestamp | Shows new date (not `---`) |
| 6 | Check Reference Stats | Counts updated (different from step 1) |
| 7 | Check TOP REFERENCES | Entries updated |
| 8 | Play 1-2 bars | Reference counts stable (no large jump) |

**Pass criteria:**
- Timestamp shows valid date after advance (not `---`)
- Reference counts update immediately after Process Till
- Playing additional bars causes only minor changes (not 50%+ jump)

**Known issue (if failing):** Issue #474 - stale UI state after Process Till.

---

## Test 5: Jump to Start - Reset

**Purpose:** Verify reset functionality clears state properly.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Advance to 1000+ bars | Bar count > 1000 |
| 2 | Click "Jump to Start" (\|<) | App resets |
| 3 | Check bar count | Shows 0 or minimal bars |
| 4 | Check timestamp | Shows `---` or initial date |
| 5 | Play to warm up again | Warmup process starts fresh |

**Pass criteria:** State resets to beginning, warmup required again.

---

## Test 6: Reference Config Changes

**Purpose:** Verify reference configuration updates affect display.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open Reference Config panel | Panel visible in sidebar |
| 2 | Change "Show top" slider | Value updates |
| 3 | Click "Apply" | Chart updates reference count |
| 4 | Adjust salience weight (e.g., Range) | Value changes |
| 5 | Click "Apply" | Reference ordering may change |
| 6 | Click "Reset to Defaults" | All values return to defaults |

**Pass criteria:** Config changes apply and visibly affect display.

---

## Test 7: Playback Speed Control

**Purpose:** Verify speed controls work.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Start playback at 1x | Normal speed |
| 2 | Change to 10x | Bars advance faster |
| 3 | Change to 20x | Bars advance much faster |
| 4 | Change back to 1x | Speed returns to normal |

**Pass criteria:** Speed changes are noticeable.

---

## Test 8: Chart Interaction

**Purpose:** Verify chart hover and click interactions.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Have some legs visible on chart | Diagonal lines visible |
| 2 | Hover over a leg line | Line thickens, panel item highlights |
| 3 | Click on a leg line | Panel scrolls to that leg |
| 4 | Hover over item in panel | Corresponding chart leg highlights |

**Pass criteria:** Bidirectional hover/click highlighting works.

---

## Test 9: View Switching

**Purpose:** Verify switching between views preserves state.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Play to ~500 bars in Market Structure | Bar count ~500 |
| 2 | Switch to "Levels at Play" | View changes, bar count same |
| 3 | Play a few more bars | Bar count increases |
| 4 | Switch back to "Structural Logs" | View changes, bar count preserved |

**Pass criteria:** Bar position maintained across view switches.

---

## Quick Smoke Test (2 min)

For rapid verification after changes:

1. **Load app** - Opens without errors
2. **Play** - Warmup completes, bars advance
3. **+10K advance** - Timestamp updates (not `---`), refs update
4. **Check refs** - Play 1 bar, no major count jump
5. **Reset** - Jump to Start works

If all 5 pass, core functionality is working.

---

## Console Error Check

After any test, open browser DevTools (F12) and check Console tab:

- **Red errors:** Investigate immediately
- **Yellow warnings:** Note but usually OK
- **Network errors:** Check backend is running

---

## Test Data Files

| File | Use Case |
|------|----------|
| `es-30m.csv` | Standard testing, 30-min bars |
| `es-5m.csv` | Higher resolution testing |

---

## Reporting Issues

If a test fails:

1. Note the exact step that failed
2. Screenshot the current state
3. Check browser console for errors
4. Check backend terminal for errors
5. File issue with reproduction steps

Use `/file_issue` skill or `gh issue create`.
