import { useState, useCallback, useRef } from 'react';
import { fetchReferenceState as fetchReferenceStateApi, ReferenceStateResponse } from '../lib/api';

interface UseReferenceStateReturn {
  referenceState: ReferenceStateResponse | null;
  isLoading: boolean;
  error: string | null;
  fetchReferenceState: (barIndex: number) => void;
  fadingRefs: Set<string>;
}

export function useReferenceState(): UseReferenceStateReturn {
  const [referenceState, setReferenceState] = useState<ReferenceStateResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fadingRefs, setFadingRefs] = useState<Set<string>>(new Set());

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

      setReferenceState(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch reference state');
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    referenceState,
    isLoading,
    error,
    fetchReferenceState,
    fadingRefs,
  };
}
