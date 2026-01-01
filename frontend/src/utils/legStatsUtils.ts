/**
 * Leg statistics calculation utilities.
 * Shared logic for computing leg breakdown from events and active legs.
 */

import { LegEvent, ActiveLeg } from '../types';
import { DagLeg } from '../lib/api';

/**
 * Statistics breakdown for legs.
 */
export interface LegStats {
  engulfed: number;       // Engulfed prune count
  staleExtension: number; // Stale/extension prune count
  proximity: number;      // Proximity prune count
  maxLegs: number;        // Max legs at pivot prune count
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
    maxLegs: 0,
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
      } else if (reason.includes('max_legs') || reason.includes('heft') || reason.includes('turn_ratio')) {
        stats.maxLegs++;
      }
    }
  }

  return stats;
}
