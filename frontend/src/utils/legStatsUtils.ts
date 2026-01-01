/**
 * Leg statistics calculation utilities.
 * Shared logic for computing leg breakdown from events and active legs.
 *
 * #404: Simplified stats - removed CTR and Formed, renamed Turn to Heft
 */

import { LegEvent, ActiveLeg } from '../types';
import { DagLeg } from '../lib/api';

/**
 * Statistics breakdown for legs.
 * #404: Removed minCtr (counter-trend ratio) and formed counts.
 */
export interface LegStats {
  engulfed: number;       // Engulfed prune count
  staleExtension: number; // Stale/extension prune count
  proximity: number;      // Proximity prune count
  heft: number;           // Heft-based prune count (was turnRatio)
}

/**
 * Calculate leg statistics from events and active legs.
 *
 * @param legEvents - Array of leg events (LEG_CREATED, LEG_PRUNED, ORIGIN_BREACHED)
 * @param activeLegs - Array of active legs (unused, kept for API compatibility)
 */
export function calculateLegStats(
  legEvents: LegEvent[],
  activeLegs: (ActiveLeg | DagLeg)[]
): LegStats {
  // activeLegs parameter kept for API compatibility but no longer used
  void activeLegs;

  const stats: LegStats = {
    engulfed: 0,
    staleExtension: 0,
    proximity: 0,
    heft: 0,
  };

  // Count from events
  for (const event of legEvents) {
    if (event.type === 'LEG_PRUNED' && event.reason) {
      const reason = event.reason.toLowerCase();
      if (reason.includes('engulfed')) {
        stats.engulfed++;
      } else if (reason.includes('stale') || reason.includes('extension')) {
        stats.staleExtension++;
      } else if (reason.includes('proximity')) {
        stats.proximity++;
      } else if (reason.includes('heft') || reason.includes('turn_ratio')) {
        // Both new 'heft' reason and legacy 'turn_ratio' reasons map to heft
        stats.heft++;
      }
    }
  }

  return stats;
}
