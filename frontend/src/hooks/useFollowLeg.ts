/**
 * Follow Leg Hook - Issue #267
 *
 * Manages the Follow Leg feature state including:
 * - Color palette and assignment
 * - Followed legs tracking
 * - Lifecycle events
 */

import { useState, useCallback, useMemo } from 'react';
import { DagLeg, LifecycleEvent, fetchFollowedLegsEvents } from '../lib/api';

// ============================================================================
// Color Palette Constants
// ============================================================================

/**
 * Bull leg colors (green/blue family)
 * Used for bull legs when followed
 */
export const BULL_COLORS = [
  { slot: 'B1', name: 'Forest', hex: '#228B22' },
  { slot: 'B2', name: 'Teal', hex: '#008080' },
  { slot: 'B3', name: 'Cyan', hex: '#00CED1' },
  { slot: 'B4', name: 'Sky', hex: '#4169E1' },
  { slot: 'B5', name: 'Mint', hex: '#3CB371' },
] as const;

/**
 * Bear leg colors (red/orange family)
 * Used for bear legs when followed
 */
export const BEAR_COLORS = [
  { slot: 'R1', name: 'Crimson', hex: '#DC143C' },
  { slot: 'R2', name: 'Coral', hex: '#FF6347' },
  { slot: 'R3', name: 'Orange', hex: '#FF8C00' },
  { slot: 'R4', name: 'Salmon', hex: '#FA8072' },
  { slot: 'R5', name: 'Brick', hex: '#B22222' },
] as const;

// Maximum number of legs that can be followed
export const MAX_FOLLOWED_LEGS = 5;

// ============================================================================
// Types
// ============================================================================

export interface FollowedLeg {
  leg_id: string;
  direction: 'bull' | 'bear';
  color: string;
  colorSlot: string;
  followedAtBar: number;  // Bar index when started following
  state: 'active' | 'pruned' | 'invalidated';  // #408: 'forming'/'formed' → 'active'
  lastEvent?: string;  // Most recent event type
  pivot_price: number;
  origin_price: number;
  pivot_index: number;
  origin_index: number;
}

export interface LifecycleEventWithLegInfo extends LifecycleEvent {
  legColor: string;
  legDirection: 'bull' | 'bear';
}

export interface UseFollowLegReturn {
  // State
  followedLegs: FollowedLeg[];
  eventsByBar: Map<number, LifecycleEventWithLegInfo[]>;

  // Actions
  followLeg: (leg: DagLeg, currentBarIndex: number) => { success: boolean; error?: string };
  unfollowLeg: (legId: string) => void;
  isFollowed: (legId: string) => boolean;
  getFollowColor: (legId: string) => string | null;

  // Constraints
  canFollowLeg: (direction: 'bull' | 'bear') => { can: boolean; reason?: string };

  // Events
  fetchEventsForFollowedLegs: (currentBarIndex: number) => Promise<void>;
  clearEventsForLeg: (legId: string) => void;
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useFollowLeg(): UseFollowLegReturn {
  // State
  const [followedLegs, setFollowedLegs] = useState<FollowedLeg[]>([]);
  const [eventsByBar, setEventsByBar] = useState<Map<number, LifecycleEventWithLegInfo[]>>(new Map());

  // Track which legs have had their events fetched (fixes #315)
  const [fetchedLegIds, setFetchedLegIds] = useState<Set<string>>(new Set());

  // Calculate available colors
  const availableColors = useMemo(() => {
    const usedBullSlots = new Set(
      followedLegs.filter(l => l.direction === 'bull').map(l => l.colorSlot)
    );
    const usedBearSlots = new Set(
      followedLegs.filter(l => l.direction === 'bear').map(l => l.colorSlot)
    );

    return {
      bull: BULL_COLORS.filter(c => !usedBullSlots.has(c.slot)),
      bear: BEAR_COLORS.filter(c => !usedBearSlots.has(c.slot)),
    };
  }, [followedLegs]);

  // Check if we can follow a leg of given direction
  const canFollowLeg = useCallback((direction: 'bull' | 'bear') => {
    if (followedLegs.length >= MAX_FOLLOWED_LEGS) {
      return { can: false, reason: 'Unfollow a leg to follow this one.' };
    }

    const availableForDirection = direction === 'bull'
      ? availableColors.bull
      : availableColors.bear;

    if (availableForDirection.length === 0) {
      return {
        can: false,
        reason: `All ${direction} follow slots in use. Unfollow a ${direction} leg first.`
      };
    }

    return { can: true };
  }, [followedLegs.length, availableColors]);

  // Check if a leg is followed
  const isFollowed = useCallback((legId: string) => {
    return followedLegs.some(l => l.leg_id === legId);
  }, [followedLegs]);

  // Get follow color for a leg (null if not followed)
  const getFollowColor = useCallback((legId: string) => {
    const followed = followedLegs.find(l => l.leg_id === legId);
    return followed?.color ?? null;
  }, [followedLegs]);

  // Follow a leg
  const followLeg = useCallback((leg: DagLeg, currentBarIndex: number) => {
    // Check constraints
    const canFollow = canFollowLeg(leg.direction);
    if (!canFollow.can) {
      return { success: false, error: canFollow.reason };
    }

    // Check if already followed
    if (isFollowed(leg.leg_id)) {
      return { success: false, error: 'Leg is already followed.' };
    }

    // Assign color
    const colors = leg.direction === 'bull' ? availableColors.bull : availableColors.bear;
    const colorInfo = colors[0]; // First available

    // Determine initial state (#408: simplified to 'active' vs terminal states)
    let state: FollowedLeg['state'] = 'active';
    // #345: Use origin_breached instead of status === 'invalidated'
    if (leg.origin_breached) {
      state = 'invalidated';
    }

    // Create followed leg entry
    const followedLeg: FollowedLeg = {
      leg_id: leg.leg_id,
      direction: leg.direction,
      color: colorInfo.hex,
      colorSlot: colorInfo.slot,
      followedAtBar: currentBarIndex,
      state,
      pivot_price: leg.pivot_price,
      origin_price: leg.origin_price,
      pivot_index: leg.pivot_index,
      origin_index: leg.origin_index,
    };

    setFollowedLegs(prev => [...prev, followedLeg]);

    return { success: true };
  }, [canFollowLeg, isFollowed, availableColors]);

  // Unfollow a leg
  const unfollowLeg = useCallback((legId: string) => {
    setFollowedLegs(prev => prev.filter(l => l.leg_id !== legId));

    // Remove from fetched set so re-following will fetch again
    setFetchedLegIds(prev => {
      const updated = new Set(prev);
      updated.delete(legId);
      return updated;
    });

    // Clear events for this leg
    setEventsByBar(prev => {
      const updated = new Map(prev);
      for (const [barIdx, events] of updated) {
        const filtered = events.filter(e => e.leg_id !== legId);
        if (filtered.length === 0) {
          updated.delete(barIdx);
        } else {
          updated.set(barIdx, filtered);
        }
      }
      return updated;
    });
  }, []);

  // Fetch events for followed legs (fixes #315 - fetch once per leg, not per bar)
  const fetchEventsForFollowedLegs = useCallback(async (_currentBarIndex: number) => {
    if (followedLegs.length === 0) {
      return;
    }

    // Only fetch for legs that haven't been fetched yet
    const unfetchedLegs = followedLegs.filter(l => !fetchedLegIds.has(l.leg_id));
    if (unfetchedLegs.length === 0) {
      return; // All legs already fetched - no API call needed
    }

    // Fetch all events from the earliest followedAtBar onwards
    const sinceBar = Math.min(...unfetchedLegs.map(l => l.followedAtBar));

    try {
      const legIds = unfetchedLegs.map(l => l.leg_id);
      const response = await fetchFollowedLegsEvents(legIds, sinceBar);

      // Mark these legs as fetched
      setFetchedLegIds(prev => {
        const updated = new Set(prev);
        for (const leg of unfetchedLegs) {
          updated.add(leg.leg_id);
        }
        return updated;
      });

      // Process new events
      if (response.events.length > 0) {
        setEventsByBar(prev => {
          const updated = new Map(prev);

          for (const event of response.events) {
            // Find the followed leg for color info
            const followedLeg = followedLegs.find(l => l.leg_id === event.leg_id);
            if (!followedLeg) continue;

            const eventWithLegInfo: LifecycleEventWithLegInfo = {
              ...event,
              legColor: followedLeg.color,
              legDirection: followedLeg.direction,
            };

            const barEvents = updated.get(event.bar_index) || [];
            // Avoid duplicates
            if (!barEvents.some(e => e.leg_id === event.leg_id && e.event_type === event.event_type)) {
              updated.set(event.bar_index, [...barEvents, eventWithLegInfo]);
            }
          }

          return updated;
        });

        // Update followed leg states and last events
        setFollowedLegs(prev => prev.map(leg => {
          const legEvents = response.events.filter(e => e.leg_id === leg.leg_id);
          if (legEvents.length === 0) return leg;

          // Get the most recent event
          const lastEvent = legEvents[legEvents.length - 1];

          // Determine new state based on event type (#408: 'created' keeps 'active')
          let newState = leg.state;
          if (lastEvent.event_type === 'created') {
            // Leg creation doesn't change state from 'active'
            newState = 'active';
          } else if (lastEvent.event_type === 'pruned' || lastEvent.event_type === 'engulfed') {
            newState = 'pruned';
          } else if (lastEvent.event_type === 'invalidated') {
            newState = 'invalidated';
          }

          return {
            ...leg,
            state: newState,
            lastEvent: lastEvent.event_type,
          };
        }));
      }
    } catch (error) {
      console.error('Failed to fetch lifecycle events:', error);
    }
  }, [followedLegs, fetchedLegIds]);

  // Clear events for a specific leg
  const clearEventsForLeg = useCallback((legId: string) => {
    setEventsByBar(prev => {
      const updated = new Map(prev);
      for (const [barIdx, events] of updated) {
        const filtered = events.filter(e => e.leg_id !== legId);
        if (filtered.length === 0) {
          updated.delete(barIdx);
        } else {
          updated.set(barIdx, filtered);
        }
      }
      return updated;
    });
  }, []);

  return {
    followedLegs,
    eventsByBar,
    followLeg,
    unfollowLeg,
    isFollowed,
    getFollowColor,
    canFollowLeg,
    fetchEventsForFollowedLegs,
    clearEventsForLeg,
  };
}
