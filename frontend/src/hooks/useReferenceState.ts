import { useState, useCallback, useRef } from 'react';
import {
  fetchReferenceState as fetchReferenceStateApi,
  ReferenceStateResponseExtended,
  trackLegForCrossing,
  untrackLegForCrossing,
} from '../lib/api';

interface UseReferenceStateReturn {
  referenceState: ReferenceStateResponseExtended | null;
  isLoading: boolean;
  error: string | null;
  fetchReferenceState: (barIndex: number) => void;
  fadingRefs: Set<string>;
  // Sticky leg tracking (Phase 2)
  stickyLegIds: Set<string>;
  toggleStickyLeg: (legId: string) => Promise<void>;
  isStickyLeg: (legId: string) => boolean;
}

export function useReferenceState(): UseReferenceStateReturn {
  const [referenceState, setReferenceState] = useState<ReferenceStateResponseExtended | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fadingRefs, setFadingRefs] = useState<Set<string>>(new Set());
  const [stickyLegIds, setStickyLegIds] = useState<Set<string>>(new Set());

  // Track previous reference IDs for fade-out detection
  const prevRefIdsRef = useRef<Set<string>>(new Set());

  // Fade-out animation duration
  const FADE_DURATION_MS = 300;

  const fetchReferenceState = useCallback(async (barIndex: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const state = await fetchReferenceStateApi(barIndex);

      // Detect removed references for fade-out animation
      const currentIds = new Set(state.references.map(r => r.leg_id));
      const prevIds = prevRefIdsRef.current;

      // Find removed refs
      const removed = new Set<string>();
      prevIds.forEach(id => {
        if (!currentIds.has(id)) {
          removed.add(id);
        }
      });

      if (removed.size > 0) {
        // Set fading refs
        setFadingRefs(removed);

        // Clear fading refs after animation completes
        setTimeout(() => {
          setFadingRefs(new Set());
        }, FADE_DURATION_MS);
      }

      // Update previous refs
      prevRefIdsRef.current = currentIds;

      // Sync sticky legs from backend
      if (state.tracked_leg_ids) {
        setStickyLegIds(new Set(state.tracked_leg_ids));
      }

      setReferenceState(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch reference state');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const toggleStickyLeg = useCallback(async (legId: string) => {
    try {
      if (stickyLegIds.has(legId)) {
        await untrackLegForCrossing(legId);
        setStickyLegIds(prev => {
          const next = new Set(prev);
          next.delete(legId);
          return next;
        });
      } else {
        await trackLegForCrossing(legId);
        setStickyLegIds(prev => new Set([...prev, legId]));
      }
    } catch (err) {
      console.error('Failed to toggle sticky leg:', err);
    }
  }, [stickyLegIds]);

  const isStickyLeg = useCallback((legId: string) => {
    return stickyLegIds.has(legId);
  }, [stickyLegIds]);

  return {
    referenceState,
    isLoading,
    error,
    fetchReferenceState,
    fadingRefs,
    stickyLegIds,
    toggleStickyLeg,
    isStickyLeg,
  };
}
