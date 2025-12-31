---
name: diagnose_feedback
description: Investigate user observations from playback feedback. Use when
  user says "look at my feedback", "check my latest observation", or "diagnose
  why". Reads feedback JSON, loads actual data, traces code execution. Never
  speculates — always executes against real data.
---

# Diagnose Feedback

## CRITICAL: No Speculation

**Never theorize by reading code alone.** Execute against real data and observe.

## Feedback Location

`ground_truth/playback_feedback.json`

## Observation Structure

```json
{
  "observation_id": "uuid",
  "text": "user's question",
  "playback_bar": 12345,
  "snapshot": {
    "dag_context": {
      "active_legs": [...],
      "pending_origins": {...}
    },
    "attachments": [...],
    "detection_config": {...}
  }
}
```

## Procedure

1. Read latest observation (or specific ID if provided)
2. Parse user's question from `text` field
3. Extract context: attached legs, config parameters, bar indices
4. Load price data from CSV (semicolon-delimited, no header)
5. Run investigation harness with actual data:
   ```bash
   python scripts/investigate_leg.py --file test_data/es-5m.csv \
       --offset <csv_index> --origin-price <price> ...
   ```
6. Report findings based on EXECUTION, not assumption

## Common Patterns

| User Question | Investigation |
|---------------|---------------|
| "Why was this leg created?" | Check branch ratio, formation fib, origin conditions |
| "Why was this leg pruned?" | Check proximity, turn ratio, engulfed conditions |
| "Why no bear leg here?" | Check pending origins, counter-trend requirements |

## Cleanup (After Resolution)

Once investigation is complete and user confirms resolution:

1. Move observation from `ground_truth/playback_feedback.json` to `ground_truth/resolved_feedback.json`
2. If observation has screenshot attachments:
   - Move from `screenshots/` to `screenshots/archive/`
3. Confirm cleanup: "Observation [id] archived."

## Trigger Phrases

- "Look at my last feedback"
- "Diagnose my latest observation"
- "Check my latest observation in feedback json"
- "Why did this happen?" (with feedback context)
