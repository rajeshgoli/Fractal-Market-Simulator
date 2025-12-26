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
  invalidated: number;    // Origin breach count
  engulfed: number;       // Engulfed prune count
  staleExtension: number; // Stale/extension prune count
  proximity: number;      // Proximity prune count
  minCtr: number;         // Branch ratio domination count
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
    invalidated: 0,
    engulfed: 0,
    staleExtension: 0,
    proximity: 0,
    minCtr: 0,
    formed: 0,
  };

  // Count from events
  for (const event of legEvents) {
    if (event.type === 'ORIGIN_BREACHED') {
      stats.invalidated++;  // Count origin breaches as "invalidated" for stats
    } else if (event.type === 'LEG_PRUNED' && event.reason) {
      const reason = event.reason.toLowerCase();
      if (reason.includes('engulfed')) {
        stats.engulfed++;
      } else if (reason.includes('stale') || reason.includes('extension')) {
        stats.staleExtension++;
      } else if (reason.includes('proximity')) {
        stats.proximity++;
      } else if (reason.includes('branch_ratio') || reason.includes('dominated')) {
        stats.minCtr++;  // Repurposed for branch ratio domination
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
