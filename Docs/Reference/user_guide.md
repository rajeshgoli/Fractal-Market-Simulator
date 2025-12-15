# Ground Truth Annotator - User Guide

The Ground Truth Annotator is a web-based tool for expert annotation of swing references. It provides a two-click workflow for marking swings on aggregated OHLC charts, with automatic direction inference.

## Quick Start

### Prerequisites
- Python 3.8+ with virtual environment
- OHLC data in CSV format (test data included in `test_data/`)

### Installation

```bash
# Create virtual environment (if not exists)
python3 -m venv venv

# Activate and install dependencies
source venv/bin/activate
pip install -r requirements.txt
```

### Launch the Annotator

```bash
source venv/bin/activate
python -m src.ground_truth_annotator.main --data test_data/test.csv --scale S
```

Open http://127.0.0.1:8000 in your browser.

### Command Line Options

| Option | Description |
|--------|-------------|
| `--data FILE` | Path to OHLC CSV data file (required) |
| `--port PORT` | Server port (default: 8000) |
| `--host HOST` | Server host (default: 127.0.0.1) |
| `--storage-dir DIR` | Directory for annotation sessions |
| `--resolution RES` | Source data resolution (default: 1m) |
| `--window N` | Total bars to work with (default: 50000) |
| `--scale SCALE` | Scale to annotate: S, M, L, XL (default: S) |
| `--target-bars N` | Target bars to display in chart (default: 200) |
| `--cascade` | Enable XL → L → M → S cascade workflow |
| `--offset N` | Start offset in bars. Use 'random' for random position (default: 0) |

### Examples

```bash
# Annotate small-scale swings on 1m data
python -m src.ground_truth_annotator.main --data test_data/es-1m.csv --scale S

# Annotate medium-scale swings with more bars displayed
python -m src.ground_truth_annotator.main --data test_data/es-1m.csv --scale M --target-bars 300

# Annotate on 5m data with custom port
python -m src.ground_truth_annotator.main --data data/es-5m.csv --resolution 5m --scale L --port 8001

# Cascade mode (XL → L → M → S) with automatic Review Mode transition
python -m src.ground_truth_annotator.main --data test_data/es-1m.csv --cascade

# Random window selection for sampling different market regions
python -m src.ground_truth_annotator.main --data test_data/es-1m.csv --cascade --offset random

# Fixed offset to start at specific bar
python -m src.ground_truth_annotator.main --data test_data/es-1m.csv --cascade --offset 100000
```

## The Two-Click Annotation Workflow

1. **Click Start**: Click on the price level of the swing start. The system uses your click's Y-position to determine intent (high vs low) and **automatically snaps** to the bar with the closest matching extremum within a tolerance radius. A "Start" marker appears on the snapped candle.
2. **Click End**: Click on the price level of the swing end. The system snaps to the bar with the closest matching extremum. A confirmation panel appears in the sidebar.
3. **Confirm Direction**: The system infers the direction automatically:
   - If start.high > end.high → **Bull Reference** (downswing)
   - If start.low < end.low → **Bear Reference** (upswing)
4. **Accept or Reject**: Press `A` (or click Accept) to save, or press `R` (or click Reject) to cancel. Charts remain fully visible during confirmation.

### Snap-to-Extrema

Clicks automatically snap to the best matching extremum based on where you click:

- **Click above candle midpoint**: System looks for HIGHs, finds the bar with high closest to your click price
- **Click below candle midpoint**: System looks for LOWs, finds the bar with low closest to your click price

This allows precise selection of **intermediate structure** (e.g., lower highs, higher lows) without forcing snaps to the most extreme values in range. Click on what you see—the system finds it.

| Scale | Snap Radius (bars) |
|-------|-------------------|
| XL | 5 |
| L | 10 |
| M | 20 |
| S | 30 |

Larger scales use tighter tolerances because fewer aggregated bars are visible.

### Direction Inference

The annotator automatically determines swing direction based on price movement:

| Price Movement | Direction | Meaning |
|---------------|-----------|---------|
| Start high > End high | Bull Reference | Downswing completed, now bullish |
| Start high ≤ End high | Bear Reference | Upswing completed, now bearish |

## User Interface

### Chart Area
- **OHLC Candlesticks**: Green (bullish) and red (bearish) candles
- **Selection Markers**: Blue arrows show selected start/end points
- **Annotation Markers**: Numbered circles show saved annotations
- **Fibonacci Preview Lines**: When confirming an annotation, purple dashed lines appear at key Fibonacci levels (0, 0.382, 1.0, 2.0) to help assess swing proportions. Lines auto-clear on confirm or cancel.

### Sidebar
- **Annotation List**: All saved annotations with direction and bar range
- **Delete Button**: Click × to remove an annotation
- **Export Session**: Download current session as JSON file
- **Keyboard Hints**: Quick reference for shortcuts
- **Confirmation Panel**: Appears inline when confirming annotations (charts remain visible)

### Toast Notifications

Brief notifications appear at the bottom of the screen to confirm actions:
- "Annotation saved" - After accepting an annotation
- "Annotation deleted" - After removing an annotation
- "Session exported" - After downloading session JSON

Toasts auto-dismiss after 2 seconds.

### Header
- **Scale Badge**: Shows current scale being annotated
- **Bar Count**: Number of aggregated bars displayed
- **Annotation Count**: Total annotations for this session

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Esc` | Cancel current selection |
| `A` | Accept annotation (when confirming) |
| `R` | Reject annotation (when confirming) |
| `N` | Next scale (cascade mode only) |
| `Enter` | Confirm annotation (alternative to A) |
| `Del` / `Backspace` | Delete last annotation |

## API Endpoints

The annotator exposes a REST API:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve annotation UI |
| `/api/health` | GET | Health check |
| `/api/bars` | GET | Get aggregated bars for chart |
| `/api/annotations` | GET | List annotations for current scale |
| `/api/annotations` | POST | Create new annotation |
| `/api/annotations/{id}` | DELETE | Delete annotation |
| `/api/session` | GET | Get session state |
| `/api/session/finalize` | POST | Finalize session (keep with label or discard) |

## Session Files

### Filename Convention

Session files use timestamp-based naming for easy organization:

| Stage | Filename Pattern | Example |
|-------|-----------------|---------|
| In Progress | `inprogress-yyyy-mmm-dd-HHmm.json` | `inprogress-2025-dec-15-0830.json` |
| Kept (finalized) | `yyyy-mmm-dd-HHmm.json` | `2025-dec-15-0830.json` |
| Kept with label | `yyyy-mmm-dd-HHmm-label.json` | `2025-dec-15-0830-trending_market.json` |
| Discarded | *(deleted)* | - |

- **In Progress**: New sessions start with `inprogress-` prefix
- **Keep**: Finalized sessions get clean timestamp names
- **Discard**: Practice sessions are deleted entirely (no files remain)

This allows easy cleanup: `rm inprogress-*.json` removes abandoned sessions.

### Session Quality and Labeling

At the end of Review Mode, you can:

1. **Add a label** (optional): Enter a descriptive label like "trending_market" or "volatile_range"
2. **Keep Session**: Saves with clean timestamp filename (includes label if provided)
3. **Discard Session**: Deletes the session files entirely

Labels are sanitized for filesystem safety (spaces → underscores, special chars removed, lowercase).

### File Contents

Session files contain:
- Session metadata (data file, resolution, window size)
- All annotations with bar indices and prices
- Scale completion status
- Session status (keep/discard)

## Comparison Analysis

After annotating swings, compare your annotations against the system's automatic detection to identify:
- **False Negatives**: Swings you marked that the system missed
- **False Positives**: Swings the system detected that you didn't mark
- **Matches**: Swings both you and the system identified

### Running Comparison

Use the API endpoints to run comparison analysis:

```bash
# Run comparison (POST)
curl -X POST http://127.0.0.1:8000/api/compare

# Get detailed report (GET)
curl http://127.0.0.1:8000/api/compare/report

# Export as CSV (GET)
curl http://127.0.0.1:8000/api/compare/export?format=csv > report.csv
```

### Understanding the Report

The comparison report includes:

| Field | Description |
|-------|-------------|
| `overall_match_rate` | Percentage of swings that matched (0.0 to 1.0) |
| `total_false_negatives` | Swings you marked that system missed |
| `total_false_positives` | Swings system found that you didn't mark |
| `by_scale` | Per-scale breakdown (XL, L, M, S) |

### Matching Logic

A user annotation matches a system-detected swing when:
1. **Direction matches**: Both are bull or both are bear
2. **Start index within tolerance**: User's start is within 10% of swing duration from system's start
3. **End index within tolerance**: User's end is within 10% of swing duration from system's end
4. **Minimum tolerance**: At least 5 bars tolerance for short swings

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/compare` | POST | Run comparison, returns summary |
| `/api/compare/report` | GET | Get full report with FN/FP lists |
| `/api/compare/export` | GET | Export as JSON or CSV |

## Review Mode

After completing annotation (all 4 scales in cascade mode), use Review Mode to provide qualitative feedback on detection quality.

### Starting Review Mode

1. Complete all scales in the cascade workflow (XL → L → M → S)
2. Click "Start Review Mode →" button in the sidebar
3. Or navigate directly to `/review`

### Three-Phase Review Process

Review Mode guides you through three phases:

#### Phase 1: Matches Review

Review swings where your annotation matched system detection.

- **Purpose**: Confirm detections are actually correct
- **Actions**:
  - `G` or click "Looks Good" - Confirm match is correct
  - `W` or click "Actually Wrong" - Flag match as incorrect
  - `→` - Next swing
  - `S` - Skip all matches (advance to Phase 2)

#### Phase 2: FP Sample Review

Review a sample of false positives (system detected, you didn't mark).

- **Purpose**: Understand why system detects swings you didn't mark
- **Quick Dismiss** (one-click): Use preset buttons for common reasons:
  - `1` or click "Too small" - Detection insignificant at this scale
  - `2` or click "Too distant" - Isolated from surrounding structure
  - `3` or click "Something bigger" - Part of a larger swing
  - `4` or click "Counter trend" - Swing against prevailing trend direction
- **Other Actions**:
  - `N` or click "Dismiss (Other)" - Mark as noise with dropdown reason
  - `V` or click "Actually Valid" - Admit you missed this swing
  - Optional: Select reason from "Other" dropdown (wrong_direction, not_a_swing, other)
  - `S` - Skip remaining FPs (advance to Phase 3)

#### Phase 3: FN Feedback

Explain each false negative (you marked, system missed).

- **Purpose**: Capture qualitative signal for improving detection
- **Actions**:
  - Select a preset explanation using keyboard shortcuts `1`-`5`:
    - `1` - "Biggest swing I see at this scale"
    - `2` - "Most impulsive move"
    - `3` - "Reversal pattern"
    - `4` - "Structure break"
    - `5` - "Timeframe fit"
  - Or type a custom explanation in the text field
  - Optional: Select category (pattern, size, context, structure, other)
  - `Enter` or click "Submit Feedback" - Submit and advance
- **Note**: All FNs must have feedback before completing review

### Summary View

After all phases, see statistics:
- Matches: reviewed count, correct/incorrect
- False Positives: sampled count, noise/valid
- False Negatives: total count, explained count

### Session Quality Control

Before exporting or moving to the next window, mark the session quality:

- **Keep Session** - Include this session in ground truth analysis
- **Discard (Practice)** - Exclude from analysis (e.g., learning the tool, made mistakes)

This allows filtering analysis data to only include high-quality annotation sessions.

### Exporting Feedback

Click "Export Feedback (JSON)" to download structured feedback for rule iteration.

### Session Flow (Cascade Mode)

When using `--cascade` mode, the session follows this flow:

1. **Annotation Phase**: Progress through XL → L → M → S scales
2. **Completion**: After completing S scale, automatically redirect to Review Mode
3. **Review Phase**: Provide qualitative feedback on detection quality
4. **Next Window**: Click "Load Next Window (Random)" to start a new session at a random offset

This flow enables efficient sampling across different market regions, building a diverse ground truth dataset.

### Load Next Window

After completing review, click **"Load Next Window (Random)"** to:
- Create a new annotation session
- Select a random offset into the data file
- Preserve all current settings (cascade mode, resolution, window size)
- Start fresh annotation at a different market region

Alternatively, click **"← Back to Annotation"** to return to the current session's annotation view.

### Keyboard Shortcuts

| Phase | Key | Action |
|-------|-----|--------|
| Matches | `G` | Good (correct) |
| Matches | `W` | Wrong (incorrect) |
| Matches | `S` | Skip all |
| FP Sample | `1` | Quick dismiss: Too small |
| FP Sample | `2` | Quick dismiss: Too distant |
| FP Sample | `3` | Quick dismiss: Something bigger |
| FP Sample | `4` | Quick dismiss: Counter trend |
| FP Sample | `N` | Dismiss with other reason |
| FP Sample | `V` | Valid (I missed it) |
| FP Sample | `S` | Skip remaining |
| FN Feedback | `1`-`5` | Select preset explanation |
| FN Feedback | `Enter` | Submit (when comment filled) |
| All | `→` | Next swing |
| All | `←` | Previous swing |

### Review Mode API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/review/start` | POST | Initialize review session |
| `/api/review/state` | GET | Get current review state |
| `/api/review/matches` | GET | Get matched swings for Phase 1 |
| `/api/review/fp-sample` | GET | Get sampled FPs for Phase 2 |
| `/api/review/fn-list` | GET | Get all FNs for Phase 3 |
| `/api/review/feedback` | POST | Submit feedback on a swing |
| `/api/review/advance` | POST | Advance to next phase |
| `/api/review/summary` | GET | Get final review summary |
| `/api/review/export` | GET | Export feedback (JSON or CSV) |

