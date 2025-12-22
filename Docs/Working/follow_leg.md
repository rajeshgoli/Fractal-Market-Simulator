# Follow Leg Feature Spec

**Status:** Draft
**Author:** Product
**Date:** December 22, 2025

---

## Overview

Follow Leg enables users to track lifecycle events for specific legs over time during playback. When a followed leg experiences a lifecycle event, the candle where that event occurred is marked with a colored icon. Users can inspect events and attach them to feedback for precise issue reporting.

**Primary use case:** Understanding what happens to a leg over time — when it formed, when it was breached, when/why it was pruned — without manual tracking.

---

## User Experience

### Entry: Following a Leg

1. User hovers over a leg for 1 second
2. Two icons appear near the leg:
   - **Tree icon** (existing #250) — enter hierarchy exploration
   - **Eye icon** — follow this leg
3. User clicks eye icon
4. Leg changes color to assigned follow color
5. Leg appears in Followed Legs panel

**Constraint:** Maximum 5 legs followed simultaneously. If user attempts to follow a 6th leg, show tooltip: "Unfollow a leg to follow this one."

**Constraint:** Cannot follow pruned legs (they disappear from chart). Invalidated legs remain visible and can be followed.

### Panel: Followed Legs

Replaces the Pending Origins panel (low user value).

**Layout per row:**
```
[color swatch] [direction] [leg ID] [state] [last event] [×]
```

| Element | Description |
|---------|-------------|
| Color swatch | 16×16 filled circle in leg's follow color |
| Direction | "▲" (bull) or "▼" (bear) |
| Leg ID | e.g., "leg_1734567890_5200" (truncated if needed) |
| State | "forming" / "formed" / "pruned" / "invalidated" |
| Last event | Most recent event type, or "—" if none since follow |
| × | Unfollow button |

**Panel header:** "Followed Legs (3/5)" showing count and limit.

**Empty state:** "Hover a leg and click 👁 to follow"

### During Playback: Event Markers

As user advances through candles:

1. System detects lifecycle events for followed legs
2. Candles with events display 💡 icon in the leg's follow color
3. Icons stack vertically if multiple events on same candle (max visible: 3, then "+N" indicator)
4. Markers persist as user continues playback

**Stack order:** Most recent follow at top.

### Event Inspection

**Single event on candle:**
1. User clicks 💡 icon
2. Popup appears with:
   - Leg identifier (colored)
   - Event type (e.g., "Pivot Breached")
   - Explanation (same detail level as existing linger hover)
   - Bar index and CSV index
   - **[Attach]** button

**Multiple events on candle:**
1. User clicks 💡 stack
2. Popup shows list of events, each expandable
3. Each event has its own [Attach] button

### Attaching Events to Feedback

Uses existing attachment semantics (up to 5 attachments per feedback item).

**Attach payload:**
```json
{
  "type": "lifecycle_event",
  "leg_id": "leg_1734567890_5200",
  "leg_direction": "bull",
  "event_type": "engulfed",
  "bar_index": 4523,
  "csv_index": 4523,
  "timestamp": "2025-12-22T10:30:00Z",
  "explanation": "Leg was engulfed: origin breached by 12 points, pivot breached by 8 points"
}
```

**User adds note:** "This leg wasn't actually engulfed — the origin breach was from a wick, not a close."

### Unfollowing

**Methods:**
- Click × in Followed Legs panel
- Click eye icon on leg again (toggle)

**Behavior on unfollow:**
- Leg returns to standard color (red/green based on direction)
- All 💡 markers for that leg disappear
- Slot freed for following another leg

**Note:** If user wants to preserve event info, attach it before unfollowing.

---

## Lifecycle Events Tracked

| Event | Trigger | Explanation Content |
|-------|---------|---------------------|
| **Formed** | Leg transitions from forming → formed | "Leg formed with pivot at {price}, range {range}" |
| **Origin Breached** | Price crosses origin beyond threshold | "Origin breached by {amount} ({percent}% of range)" |
| **Pivot Breached** | Price crosses pivot beyond threshold | "Pivot breached by {amount} ({percent}% of range)" |
| **Engulfed** | Both origin and pivot breached | "Leg engulfed: origin breached {origin_amt}, pivot breached {pivot_amt}" |
| **Pruned** | Leg removed from active set | "Pruned: {reason}" (e.g., "inner structure invalidated", "engulfed") |
| **Invalidated** | Parent structure invalidated | "Invalidated: parent leg {parent_id} was invalidated" |

**Explicitly excluded:** Pivot extended (too noisy — would mark every candle during growth).

---

## Color System

### Palette

**Bull legs (green/blue family):**
| Slot | Name | Hex | Usage |
|------|------|-----|-------|
| B1 | Forest | #228B22 | First bull leg followed |
| B2 | Teal | #008080 | Second bull leg |
| B3 | Cyan | #00CED1 | Third bull leg |
| B4 | Sky | #4169E1 | Fourth bull leg |
| B5 | Mint | #3CB371 | Fifth bull leg |

**Bear legs (red/orange family):**
| Slot | Name | Hex | Usage |
|------|------|-----|-------|
| R1 | Crimson | #DC143C | First bear leg followed |
| R2 | Coral | #FF6347 | Second bear leg |
| R3 | Orange | #FF8C00 | Third bear leg |
| R4 | Salmon | #FA8072 | Fourth bear leg |
| R5 | Brick | #B22222 | Fifth bear leg |

### Assignment Logic

1. When user follows a leg, determine direction (bull/bear)
2. Find first unused slot in that direction's palette
3. Assign that color to the leg
4. When unfollowed, return color to pool

**Edge case:** If all 5 slots for a direction are used, user cannot follow another leg of that direction until one is unfollowed. Show tooltip: "All bull follow slots in use. Unfollow a bull leg first."

### Leg Rendering

Followed legs render entirely in their assigned follow color:
- Leg line/body
- Origin marker
- Pivot marker
- Any associated UI elements

This makes followed legs visually distinct and easy to track across the chart.

---

## CSV Index Requirement

**Scope:** All attachments (not just this feature).

**Problem:** Frontend bar offset doesn't directly map to source CSV row, requiring index math for engineers investigating issues.

**Solution:** Add `csv_index` field to all attachment types:

```json
{
  "type": "leg",
  "leg_id": "...",
  "csv_index": 4523,
  ...
}
```

```json
{
  "type": "lifecycle_event",
  "csv_index": 4523,
  ...
}
```

```json
{
  "type": "screenshot",
  "csv_index": 4523,
  ...
}
```

**Backend requirement:** Maintain mapping from internal bar index to source CSV row index. Expose via API so frontend can include in attachments.

**Engineer benefit:** Direct lookup in `test_data/es-5m.csv` row 4523 without offset calculations.

---

## Implementation Notes

### Backend

1. **Event tracking:** LegDetector/LegPruner already emit these events internally. Expose via API endpoint for followed legs.

2. **API endpoint:** `GET /api/followed-legs/events?leg_ids=...&since_bar=...`
   - Returns events for specified legs since given bar
   - Frontend polls on each candle advance

3. **CSV index mapping:** Add lookup table populated during data load. Expose via existing bar data response.

### Frontend

1. **State:** Track followed leg IDs, assigned colors, events per candle

2. **Panel component:** New `FollowedLegsPanel` replacing `PendingOriginsPanel`

3. **Candle markers:** Render 💡 icons as overlay layer on chart

4. **Event popup:** Extend existing linger popup component

### Data Flow

```
User clicks follow → Add to followed set → Assign color → Update leg rendering
                                                       → Show in panel

Candle advance → Fetch events for followed legs → Store events by candle
                                                → Render markers

User clicks marker → Show event popup → User clicks Attach → Add to feedback JSON
```

---

## Out of Scope

- **Retroactive events:** Only events from follow-start onward. Historical events before following are not shown.
- **Cross-session persistence:** Followed legs reset on page refresh. (Could be future enhancement.)
- **Event filtering:** All event types shown. No toggle to hide specific types.

---

## Open Questions

None currently. Ready for engineering breakdown.

---

## Related

- **#250 Hierarchy Exploration Mode** — Shares hover-icon entry pattern
- **Existing linger/hover** — Event popup mirrors this UX
- **playback_feedback.json** — Attachment destination
