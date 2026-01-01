import { useState, useCallback, useRef } from 'react';
import {
  fetchReferenceState as fetchReferenceStateApi,
  ReferenceStateResponseExtended,
  LevelCrossEvent,
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
  toggleStickyLeg: (legId: string) => Promise<{ success: boolean; error?: string }>;
  isStickyLeg: (legId: string) => boolean;
  // Level crossing (Issue #416)
  crossingEvents: LevelCrossEvent[];
  trackError: string | null;
  clearTrackError: () => void;
}

export function useReferenceState(): UseReferenceStateReturn {
  const [referenceState, setReferenceState] = useState<ReferenceStateResponseExtended | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fadingRefs, setFadingRefs] = useState<Set<string>>(new Set());
  const [stickyLegIds, setStickyLegIds] = useState<Set<string>>(new Set());
  const [crossingEvents, setCrossingEvents] = useState<LevelCrossEvent[]>([]);
  const [trackError, setTrackError] = useState<string | null>(null);

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

      // Capture crossing events from this update
      if (state.crossing_events && state.crossing_events.length > 0) {
        setCrossingEvents(state.crossing_events);
      }

      setReferenceState(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch reference state');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const toggleStickyLeg = useCallback(async (legId: string): Promise<{ success: boolean; error?: string }> => {
    try {
      if (stickyLegIds.has(legId)) {
        const result = await untrackLegForCrossing(legId);
        if (result.success) {
          setStickyLegIds(prev => {
            const next = new Set(prev);
            next.delete(legId);
            return next;
          });
        }
        return { success: result.success, error: result.error || undefined };
      } else {
        const result = await trackLegForCrossing(legId);
        if (result.success) {
          setStickyLegIds(prev => new Set([...prev, legId]));
        } else if (result.error) {
          // Max limit reached
          setTrackError(result.error);
          // Auto-clear after 3 seconds
          setTimeout(() => setTrackError(null), 3000);
        }
        return { success: result.success, error: result.error || undefined };
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to toggle sticky leg';
      console.error('Failed to toggle sticky leg:', err);
      setTrackError(errorMsg);
      setTimeout(() => setTrackError(null), 3000);
      return { success: false, error: errorMsg };
    }
  }, [stickyLegIds]);

  const clearTrackError = useCallback(() => {
    setTrackError(null);
  }, []);

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
    crossingEvents,
    trackError,
    clearTrackError,
  };
}
