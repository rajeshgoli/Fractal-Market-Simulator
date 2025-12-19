import { useMemo } from 'react';
import {
  CalibrationSwing,
  CalibrationData,
  SwingDisplayConfig,
  SwingScaleKey,
  HierarchicalDisplayConfig,
  CalibrationDataHierarchical,
  DepthFilterKey,
} from '../types';

interface UseSwingDisplayResult {
  /** Filtered and ranked active swings based on display config (limited by activeSwingCount for chart display) */
  filteredActiveSwings: CalibrationSwing[];
  /** All active swings for enabled scales (not limited - for navigation) */
  allNavigableSwings: CalibrationSwing[];
  /** Filtered stats by scale (only enabled scales) */
  filteredStats: Record<string, { total_swings: number; active_swings: number; displayed_swings: number }>;
}

interface UseHierarchicalDisplayResult {
  /** Filtered and ranked active swings based on hierarchical config (limited by activeSwingCount) */
  filteredActiveSwings: CalibrationSwing[];
  /** All active swings for enabled filters (not limited - for navigation) */
  allNavigableSwings: CalibrationSwing[];
  /** Stats by depth level */
  statsByDepth: Record<string, { total_swings: number; defended_swings: number; displayed_swings: number }>;
}

/**
 * Hook to filter and rank active swings based on display configuration.
 *
 * - Filters by enabled scales (XL/L/M/S toggles)
 * - Limits to top N biggest swings per scale (activeSwingCount)
 * - Ranks swings by size (pts) within each scale
 */
export function useSwingDisplay(
  calibrationData: CalibrationData | null,
  displayConfig: SwingDisplayConfig
): UseSwingDisplayResult {
  return useMemo(() => {
    if (!calibrationData) {
      return {
        filteredActiveSwings: [],
        allNavigableSwings: [],
        filteredStats: {},
      };
    }

    const { enabledScales, activeSwingCount } = displayConfig;
    const scaleOrder: SwingScaleKey[] = ['XL', 'L', 'M', 'S'];

    const filteredActiveSwings: CalibrationSwing[] = [];
    const allNavigableSwings: CalibrationSwing[] = [];
    const filteredStats: Record<string, { total_swings: number; active_swings: number; displayed_swings: number }> = {};

    for (const scale of scaleOrder) {
      const scaleStat = calibrationData.stats_by_scale[scale];
      // Use active_swings_by_scale for both navigation and display (reference swings only)
      const activeSwings = calibrationData.active_swings_by_scale[scale] || [];

      if (!scaleStat) continue;

      // Get displayed swings (top N by size if scale is enabled)
      let displayedSwings: CalibrationSwing[] = [];
      if (enabledScales.has(scale)) {
        // Active swings for navigation - sorted by size, ranked but not limited
        const sortedActiveSwings = [...activeSwings].sort((a, b) => b.size - a.size);
        const rankedActiveSwings = sortedActiveSwings.map((swing, index) => ({
          ...swing,
          rank: index + 1,  // Rank based on size order
        }));
        allNavigableSwings.push(...rankedActiveSwings);

        // Active swings for chart display - take top N from the same list
        displayedSwings = rankedActiveSwings.slice(0, activeSwingCount);
        filteredActiveSwings.push(...displayedSwings);
      }

      // Always include stats for all scales (so UI can show grayed out)
      filteredStats[scale] = {
        total_swings: scaleStat.total_swings,
        active_swings: scaleStat.active_swings,
        displayed_swings: displayedSwings.length,
      };
    }

    return {
      filteredActiveSwings,
      allNavigableSwings,
      filteredStats,
    };
  }, [calibrationData, displayConfig]);
}

/**
 * Hook to filter and rank active swings based on hierarchical display configuration.
 *
 * - Filters by depth (root only, 2 levels, 3 levels, all)
 * - Filters by status (defended, completed, invalidated)
 * - Filters by direction (bull, bear)
 * - Limits to top N biggest defended swings (activeSwingCount)
 * - Ranks swings by size (pts)
 */
export function useHierarchicalDisplay(
  calibrationData: CalibrationDataHierarchical | null,
  displayConfig: HierarchicalDisplayConfig
): UseHierarchicalDisplayResult {
  return useMemo(() => {
    if (!calibrationData || !calibrationData.active_swings_by_depth) {
      return {
        filteredActiveSwings: [],
        allNavigableSwings: [],
        statsByDepth: {},
      };
    }

    const { depthFilter, enabledStatuses: _enabledStatuses, enabledDirections, activeSwingCount } = displayConfig;
    void _enabledStatuses; // Status filtering will be used when completed/invalidated swings are included
    const depthOrder = ['depth_1', 'depth_2', 'depth_3', 'deeper'] as const;

    // Get max depth based on filter
    const maxDepthIndex = getMaxDepthIndex(depthFilter);

    // Collect all swings that pass the depth filter
    let candidateSwings: CalibrationSwing[] = [];

    for (let i = 0; i <= maxDepthIndex && i < depthOrder.length; i++) {
      const depthKey = depthOrder[i];
      const swingsAtDepth = calibrationData.active_swings_by_depth[depthKey] || [];
      candidateSwings.push(...swingsAtDepth);
    }

    // Apply direction filter
    if (!enabledDirections.has('bull')) {
      candidateSwings = candidateSwings.filter(s => s.direction !== 'bull');
    }
    if (!enabledDirections.has('bear')) {
      candidateSwings = candidateSwings.filter(s => s.direction !== 'bear');
    }

    // Apply status filter (for now, active_swings_by_depth only contains defended swings)
    // If we had completed/invalidated swings in the response, we'd filter here
    // For now, defended is implied for active_swings

    // Sort by size and rank
    const sortedSwings = [...candidateSwings].sort((a, b) => b.size - a.size);
    const rankedSwings = sortedSwings.map((swing, index) => ({
      ...swing,
      rank: index + 1,
    }));

    // All navigable swings (not limited)
    const allNavigableSwings = rankedSwings;

    // Filtered for display (limited by activeSwingCount)
    const filteredActiveSwings = rankedSwings.slice(0, activeSwingCount);

    // Build stats by depth
    const statsByDepth: Record<string, { total_swings: number; defended_swings: number; displayed_swings: number }> = {};
    const treeStats = calibrationData.tree_stats;

    statsByDepth['depth_1'] = {
      total_swings: calibrationData.swings_by_depth?.depth_1?.length ?? 0,
      defended_swings: treeStats?.defended_by_depth?.['1'] ?? 0,
      displayed_swings: filteredActiveSwings.filter(s => getSwingDepthCategory(s) === 'depth_1').length,
    };
    statsByDepth['depth_2'] = {
      total_swings: calibrationData.swings_by_depth?.depth_2?.length ?? 0,
      defended_swings: treeStats?.defended_by_depth?.['2'] ?? 0,
      displayed_swings: filteredActiveSwings.filter(s => getSwingDepthCategory(s) === 'depth_2').length,
    };
    statsByDepth['depth_3'] = {
      total_swings: calibrationData.swings_by_depth?.depth_3?.length ?? 0,
      defended_swings: treeStats?.defended_by_depth?.['3'] ?? 0,
      displayed_swings: filteredActiveSwings.filter(s => getSwingDepthCategory(s) === 'depth_3').length,
    };
    statsByDepth['deeper'] = {
      total_swings: calibrationData.swings_by_depth?.deeper?.length ?? 0,
      defended_swings: treeStats?.defended_by_depth?.['deeper'] ?? 0,
      displayed_swings: filteredActiveSwings.filter(s => getSwingDepthCategory(s) === 'deeper').length,
    };

    return {
      filteredActiveSwings,
      allNavigableSwings,
      statsByDepth,
    };
  }, [calibrationData, displayConfig]);
}

/**
 * Get the max depth index based on filter selection.
 */
function getMaxDepthIndex(depthFilter: DepthFilterKey): number {
  switch (depthFilter) {
    case 'root_only':
      return 0;  // Only depth_1 (root)
    case '2_levels':
      return 1;  // depth_1 and depth_2
    case '3_levels':
      return 2;  // depth_1, depth_2, depth_3
    case 'all':
    default:
      return 3;  // All depths
  }
}

/**
 * Get the depth category for a swing based on its depth field.
 */
function getSwingDepthCategory(swing: CalibrationSwing): string {
  // CalibrationSwing has a depth field from the backend
  const depth = (swing as { depth?: number }).depth ?? 0;
  if (depth === 0) return 'depth_1';
  if (depth === 1) return 'depth_2';
  if (depth === 2) return 'depth_3';
  return 'deeper';
}
