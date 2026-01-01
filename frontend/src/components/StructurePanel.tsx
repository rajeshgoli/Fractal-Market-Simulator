import React from 'react';
import {
  LevelTouch,
  FibLevel,
  StructurePanelResponse,
  ReferenceSwing,
} from '../lib/api';
import { Eye, EyeOff, Layers, Target, Clock, ChevronDown, ChevronUp } from 'lucide-react';

interface StructurePanelProps {
  structureData: StructurePanelResponse | null;
  references: ReferenceSwing[];
  trackedLegIds: Set<string>;
  onToggleTrack: (legId: string) => Promise<{ success: boolean; error?: string }>;
  isLoading?: boolean;
}

// Scale badge colors
const SCALE_BADGE_COLORS: Record<string, { bg: string; text: string }> = {
  'XL': { bg: 'bg-purple-600/20', text: 'text-purple-400' },
  'L': { bg: 'bg-blue-600/20', text: 'text-blue-400' },
  'M': { bg: 'bg-green-600/20', text: 'text-green-400' },
  'S': { bg: 'bg-gray-600/20', text: 'text-gray-400' },
};

// Format level display
const formatLevel = (level: FibLevel, currentPrice: number): { distance: string; direction: 'above' | 'below' } => {
  const direction = level.price > currentPrice ? 'above' : 'below';
  const distance = Math.abs(level.price - currentPrice).toFixed(2);
  return {
    distance,
    direction,
  };
};

export const StructurePanel: React.FC<StructurePanelProps> = ({
  structureData,
  references,
  trackedLegIds,
  onToggleTrack,
  isLoading = false,
}) => {
  if (isLoading || !structureData) {
    return (
      <div className="bg-app-card rounded-lg p-3 border border-app-border">
        <div className="flex items-center gap-2 mb-3">
          <Layers size={14} className="text-trading-blue" />
          <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">Structure</h3>
        </div>
        <div className="text-xs text-app-muted text-center py-4">
          {isLoading ? 'Loading...' : 'No structure data'}
        </div>
      </div>
    );
  }

  const { touched_this_session, currently_active, current_bar_touches, current_price } = structureData;

  return (
    <div className="bg-app-card rounded-lg p-3 border border-app-border h-full overflow-hidden flex flex-col">
      <div className="flex items-center gap-2 mb-3">
        <Layers size={14} className="text-trading-blue" />
        <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">Structure</h3>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3">
        {/* Current Bar Touches */}
        <section>
          <div className="flex items-center gap-1.5 mb-1.5">
            <Target size={12} className="text-yellow-400" />
            <span className="text-[10px] font-medium text-app-muted uppercase">Current Bar</span>
          </div>
          {current_bar_touches.length > 0 ? (
            <div className="space-y-1">
              {current_bar_touches.map((touch, idx) => (
                <TouchItem key={`current-${idx}`} touch={touch} />
              ))}
            </div>
          ) : (
            <div className="text-[10px] text-app-muted pl-4">No touches</div>
          )}
        </section>

        {/* Currently Active */}
        <section>
          <div className="flex items-center gap-1.5 mb-1.5">
            <ChevronDown size={12} className="text-trading-blue" />
            <span className="text-[10px] font-medium text-app-muted uppercase">Active Levels</span>
            <span className="text-[9px] text-app-muted">(within 0.5%)</span>
          </div>
          {currently_active.length > 0 ? (
            <div className="space-y-1">
              {currently_active.slice(0, 6).map((level, idx) => (
                <ActiveLevelItem
                  key={`active-${idx}`}
                  level={level}
                  currentPrice={current_price}
                  isTracked={trackedLegIds.has(level.leg_id)}
                  onToggleTrack={onToggleTrack}
                />
              ))}
              {currently_active.length > 6 && (
                <div className="text-[9px] text-app-muted pl-4">
                  +{currently_active.length - 6} more
                </div>
              )}
            </div>
          ) : (
            <div className="text-[10px] text-app-muted pl-4">No levels nearby</div>
          )}
        </section>

        {/* Touched This Session */}
        <section>
          <div className="flex items-center gap-1.5 mb-1.5">
            <Clock size={12} className="text-gray-400" />
            <span className="text-[10px] font-medium text-app-muted uppercase">Session History</span>
          </div>
          {touched_this_session.length > 0 ? (
            <div className="space-y-1 max-h-24 overflow-y-auto">
              {touched_this_session.slice(-8).reverse().map((touch, idx) => (
                <TouchItem key={`history-${idx}`} touch={touch} compact />
              ))}
              {touched_this_session.length > 8 && (
                <div className="text-[9px] text-app-muted pl-4">
                  +{touched_this_session.length - 8} earlier
                </div>
              )}
            </div>
          ) : (
            <div className="text-[10px] text-app-muted pl-4">No touches yet</div>
          )}
        </section>

        {/* Active References with Track Button */}
        <section>
          <div className="flex items-center gap-1.5 mb-1.5">
            <Eye size={12} className="text-trading-blue" />
            <span className="text-[10px] font-medium text-app-muted uppercase">Track References</span>
            <span className="text-[9px] text-app-muted">({trackedLegIds.size}/10)</span>
          </div>
          {references.length > 0 ? (
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {references.slice(0, 10).map((ref) => (
                <ReferenceItem
                  key={ref.leg_id}
                  reference={ref}
                  isTracked={trackedLegIds.has(ref.leg_id)}
                  onToggleTrack={onToggleTrack}
                />
              ))}
            </div>
          ) : (
            <div className="text-[10px] text-app-muted pl-4">No references</div>
          )}
        </section>
      </div>
    </div>
  );
};

// Touch item component
const TouchItem: React.FC<{ touch: LevelTouch; compact?: boolean }> = ({ touch, compact = false }) => {
  const scaleStyle = SCALE_BADGE_COLORS[touch.scale] || SCALE_BADGE_COLORS['S'];
  const crossIcon = touch.cross_direction === 'up' ? <ChevronUp size={10} /> : <ChevronDown size={10} />;
  const crossColor = touch.cross_direction === 'up' ? 'text-trading-bull' : 'text-trading-bear';

  return (
    <div className={`flex items-center gap-1.5 ${compact ? 'text-[9px]' : 'text-[10px]'}`}>
      <span className={`px-1 py-0.5 rounded ${scaleStyle.bg} ${scaleStyle.text} text-[9px] font-medium`}>
        {touch.scale}
      </span>
      <span className={touch.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
        {touch.direction === 'bull' ? '▲' : '▼'}
      </span>
      <span className="font-mono text-app-text">
        {touch.ratio.toFixed(3)}
      </span>
      <span className={`${crossColor}`}>
        {crossIcon}
      </span>
      {!compact && (
        <span className="text-app-muted">
          @ bar {touch.bar_index}
        </span>
      )}
    </div>
  );
};

// Active level item with track button
const ActiveLevelItem: React.FC<{
  level: FibLevel;
  currentPrice: number;
  isTracked: boolean;
  onToggleTrack: (legId: string) => Promise<{ success: boolean; error?: string }>;
}> = ({ level, currentPrice, isTracked, onToggleTrack }) => {
  const scaleStyle = SCALE_BADGE_COLORS[level.scale] || SCALE_BADGE_COLORS['S'];
  const { distance, direction } = formatLevel(level, currentPrice);

  const handleClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await onToggleTrack(level.leg_id);
  };

  return (
    <div className="flex items-center gap-1.5 text-[10px] group">
      <button
        onClick={handleClick}
        className={`p-0.5 rounded transition-colors ${
          isTracked
            ? 'bg-trading-blue/20 text-trading-blue'
            : 'bg-app-border text-app-muted hover:text-app-text'
        }`}
        title={isTracked ? 'Untrack' : 'Track'}
      >
        {isTracked ? <Eye size={10} /> : <EyeOff size={10} />}
      </button>
      <span className={`px-1 py-0.5 rounded ${scaleStyle.bg} ${scaleStyle.text} text-[9px] font-medium`}>
        {level.scale}
      </span>
      <span className={level.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
        {level.direction === 'bull' ? '▲' : '▼'}
      </span>
      <span className="font-mono text-app-text">
        {level.ratio.toFixed(3)}
      </span>
      <span className="text-app-muted">
        @ {level.price.toFixed(2)}
      </span>
      <span className={`text-[9px] ${direction === 'above' ? 'text-trading-bull' : 'text-trading-bear'}`}>
        ({distance} {direction})
      </span>
    </div>
  );
};

// Reference item with track button
const ReferenceItem: React.FC<{
  reference: ReferenceSwing;
  isTracked: boolean;
  onToggleTrack: (legId: string) => Promise<{ success: boolean; error?: string }>;
}> = ({ reference, isTracked, onToggleTrack }) => {
  const scaleStyle = SCALE_BADGE_COLORS[reference.scale] || SCALE_BADGE_COLORS['S'];
  const range = Math.abs(reference.origin_price - reference.pivot_price).toFixed(2);

  const handleClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await onToggleTrack(reference.leg_id);
  };

  return (
    <div className="flex items-center gap-1.5 text-[10px] group">
      <button
        onClick={handleClick}
        className={`p-0.5 rounded transition-colors ${
          isTracked
            ? 'bg-trading-blue/20 text-trading-blue'
            : 'bg-app-border text-app-muted hover:text-app-text'
        }`}
        title={isTracked ? 'Untrack' : 'Track'}
      >
        {isTracked ? <Eye size={10} /> : <EyeOff size={10} />}
      </button>
      <span className={`px-1 py-0.5 rounded ${scaleStyle.bg} ${scaleStyle.text} text-[9px] font-medium`}>
        {reference.scale}
      </span>
      <span className={reference.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
        {reference.direction === 'bull' ? '▲' : '▼'}
      </span>
      <span className="font-mono text-app-text">
        {reference.pivot_price.toFixed(2)}
      </span>
      <span className="text-app-muted">
        → {reference.origin_price.toFixed(2)}
      </span>
      <span className="text-[9px] text-app-muted">
        ({range})
      </span>
    </div>
  );
};
