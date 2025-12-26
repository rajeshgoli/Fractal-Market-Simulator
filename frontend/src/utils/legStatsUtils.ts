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
  minCtr: number;         // Min counter-trend ratio prune count
  turnRatio: number;      // Turn ratio prune count
  formed: number;         // Currently formed legs
}

/**
 * Calculate leg statistics from events and active legs.
 *
 * @param legEvents - Array of leg events (LEG_CREATED, LEG_PRUNED, ORIGIN_BREACHED)
 * @param activeLegs - Array of active legs (ActiveLeg or DagLeg)
 */
export function calculateLegStats(
  legEvents: LegEvent[],
  activeLegs: (ActiveLeg | DagLeg)[]
): LegStats {
  const stats: LegStats = {
    engulfed: 0,
    staleExtension: 0,
    proximity: 0,
    minCtr: 0,
    turnRatio: 0,
    formed: 0,
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
      } else if (reason.includes('counter_trend') || reason.includes('counter-trend')) {
        stats.minCtr++;  // Min counter-trend ratio prune
      } else if (reason.includes('turn_ratio')) {
        stats.turnRatio++;  // Turn ratio prune (threshold, top-k, or raw modes)
      }
    }
  }

  // Count formed from active legs
  for (const leg of activeLegs) {
    if (leg.formed) {
      stats.formed++;
    }
  }

  return stats;
}
