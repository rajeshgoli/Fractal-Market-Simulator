import React, { useState } from 'react';
import { Play, Pause, SkipBack, SkipForward, FastForward, Rewind, Clock, ChevronDown, ChevronLeft, ChevronRight, X, Timer, TimerOff, Forward, Loader2 } from 'lucide-react';
import { PLAYBACK_SPEEDS } from '../constants';
import { PlaybackState, AggregationScale } from '../types';

interface SpeedAggregationOption {
  value: AggregationScale;
  label: string;
}

interface PlaybackControlsProps {
  playbackState: PlaybackState;
  onPlayPause: () => void;
  onStepBack: () => void;
  onStepForward: () => void;
  onJumpToStart: () => void;
  onJumpToEnd?: () => void;  // Optional: undefined disables the button (forward-only mode)
  // Event navigation
  onJumpToPreviousEvent?: () => void;
  onJumpToNextEvent?: () => void;
  hasPreviousEvent?: boolean;
  hasNextEvent?: boolean;
  currentEventIndex?: number;  // 0-based, -1 if no events yet
  totalEvents?: number;
  // Backward navigation (#278)
  canStepBack?: boolean;  // Whether step back is available (has cached history)
  // Bar counter
  currentBar: number;
  totalBars: number;
  // Forward playback metadata (optional - when set, shows different display)
  calibrationBarCount?: number;
  windowOffset?: number;
  totalSourceBars?: number;
  // Speed controls
  speedMultiplier: number;
  onSpeedMultiplierChange: (multiplier: number) => void;
  speedAggregation: AggregationScale;
  onSpeedAggregationChange: (agg: AggregationScale) => void;
  availableSpeedAggregations: SpeedAggregationOption[];
  isLingering: boolean;
  lingerTimeLeft: number;
  lingerTotalTime: number;
  lingerEventType?: string;
  lingerQueuePosition?: { current: number; total: number };
  onNavigatePrev?: () => void;
  onNavigateNext?: () => void;
  onDismissLinger?: () => void;
  // Linger toggle
  lingerEnabled?: boolean;
  onToggleLinger?: () => void;
  // Process Till feature (#328)
  currentCsvIndex?: number;
  maxCsvIndex?: number;
  onProcessTill?: (targetCsvIndex: number) => Promise<void>;
  isProcessingTill?: boolean;
}

export const PlaybackControls: React.FC<PlaybackControlsProps> = ({
  playbackState,
  onPlayPause,
  onStepBack,
  onStepForward,
  onJumpToStart,
  onJumpToEnd,
  onJumpToPreviousEvent,
  onJumpToNextEvent,
  hasPreviousEvent = false,
  hasNextEvent = true,
  currentEventIndex = -1,
  totalEvents = 0,
  canStepBack = true,  // Default to true for backward compatibility (#278)
  currentBar,
  totalBars,
  calibrationBarCount,
  windowOffset,
  totalSourceBars,
  speedMultiplier,
  onSpeedMultiplierChange,
  speedAggregation,
  onSpeedAggregationChange,
  availableSpeedAggregations,
  isLingering,
  lingerTimeLeft,
  lingerTotalTime,
  lingerEventType,
  lingerQueuePosition,
  onNavigatePrev,
  onNavigateNext,
  onDismissLinger,
  lingerEnabled = true,
  onToggleLinger,
  currentCsvIndex,
  maxCsvIndex,
  onProcessTill,
  isProcessingTill = false,
}) => {
  const isPlaying = playbackState === PlaybackState.PLAYING;

  // Process Till state (#328)
  const [processTillInput, setProcessTillInput] = useState('');
  const [processTillError, setProcessTillError] = useState<string | null>(null);

  // Check if we're in forward playback mode (have calibration data)
  const isForwardPlayback = calibrationBarCount !== undefined && calibrationBarCount > 0;

  // Format large numbers with K/M suffix
  const formatCount = (n: number): string => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
    return n.toLocaleString();
  };

  // Calculate remaining bars for forward playback
  const remainingBars = isForwardPlayback && totalSourceBars !== undefined && windowOffset !== undefined
    ? Math.max(0, totalSourceBars - windowOffset - currentBar - 1)
    : 0;

  // Timer wheel calculation
  const radius = 22;
  const circumference = 2 * Math.PI * radius;
  const progress = isLingering ? (lingerTimeLeft / lingerTotalTime) : 0;
  const dashOffset = circumference - (progress * circumference);

  // Progress bar percentage
  const progressPercent = totalBars > 0 ? (currentBar / totalBars) * 100 : 0;

  // Handle Process Till submit (#328)
  const handleProcessTill = async () => {
    if (!onProcessTill) return;

    const targetIndex = parseInt(processTillInput.trim(), 10);
    if (isNaN(targetIndex)) {
      setProcessTillError('Enter a valid number');
      return;
    }
    if (currentCsvIndex !== undefined && targetIndex <= currentCsvIndex) {
      setProcessTillError('Target must be > current');
      return;
    }
    if (maxCsvIndex !== undefined && targetIndex > maxCsvIndex) {
      setProcessTillError(`Max is ${maxCsvIndex}`);
      return;
    }

    setProcessTillError(null);
    try {
      await onProcessTill(targetIndex);
      setProcessTillInput(''); // Clear on success
    } catch (err) {
      setProcessTillError(err instanceof Error ? err.message : 'Failed');
    }
  };

  return (
    <div className="bg-app-secondary border-t border-b border-app-border p-3 flex flex-col md:flex-row items-center justify-between gap-4 select-none">
      {/* Left: Transport Controls */}
      <div className="flex items-center gap-4">
        {/* Buttons Group */}
        <div className="flex items-center gap-2">
          <button
            onClick={onJumpToStart}
            className="p-2 text-app-muted hover:text-white hover:bg-app-card rounded-full transition-colors"
            aria-label="Jump to Start"
            title="Jump to Start"
          >
            <SkipBack size={18} />
          </button>
          <button
            onClick={onJumpToPreviousEvent || onStepBack}
            disabled={onJumpToPreviousEvent ? !hasPreviousEvent : !canStepBack}
            className={`p-2 rounded-full transition-colors ${
              (onJumpToPreviousEvent && !hasPreviousEvent) || (!onJumpToPreviousEvent && !canStepBack)
                ? 'text-app-muted/30 cursor-not-allowed'
                : 'text-app-muted hover:text-white hover:bg-app-card'
            }`}
            aria-label="Previous Event"
            title={onJumpToPreviousEvent ? "Previous Event ([)" : canStepBack ? "Step Back ([)" : "No history cached"}
          >
            <Rewind size={18} />
          </button>

          {/* Main Play Button with Timer Wheel */}
          <div className="relative flex items-center justify-center w-14 h-14">
            {/* Background Circle */}
            <svg className="absolute inset-0 w-full h-full transform -rotate-90">
              <circle
                cx="28"
                cy="28"
                r={radius}
                fill="transparent"
                strokeWidth="3"
                className="stroke-app-card"
              />
              {/* Progress Circle (Only visible during linger) */}
              {isLingering && (
                <circle
                  cx="28"
                  cy="28"
                  r={radius}
                  fill="transparent"
                  strokeWidth="3"
                  className="stroke-trading-blue transition-all duration-100 ease-linear"
                  strokeDasharray={circumference}
                  strokeDashoffset={dashOffset}
                  strokeLinecap="round"
                />
              )}
            </svg>

            <button
              onClick={onPlayPause}
              className={`
                relative z-10 w-10 h-10 rounded-full flex items-center justify-center transition-all duration-200 shadow-lg
                ${isLingering
                  ? 'bg-trading-orange text-white animate-pulse'
                  : isPlaying
                    ? 'bg-app-card text-trading-blue ring-1 ring-trading-blue/50'
                    : 'bg-trading-blue text-white hover:bg-blue-600'
                }
              `}
            >
              {isPlaying || isLingering ? (
                <Pause size={20} fill="currentColor" />
              ) : (
                <Play size={20} fill="currentColor" className="ml-0.5" />
              )}
            </button>
          </div>

          <button
            onClick={onJumpToNextEvent || onStepForward}
            disabled={onJumpToNextEvent ? !hasNextEvent : false}
            className={`p-2 rounded-full transition-colors ${
              onJumpToNextEvent && !hasNextEvent
                ? 'text-app-muted/30 cursor-not-allowed'
                : 'text-app-muted hover:text-white hover:bg-app-card'
            }`}
            aria-label="Next Event"
            title={onJumpToNextEvent ? "Next Event (])" : "Step Forward"}
          >
            <FastForward size={18} />
          </button>
          <button
            onClick={onJumpToEnd}
            disabled={!onJumpToEnd}
            className={`p-2 rounded-full transition-colors ${
              onJumpToEnd
                ? 'text-app-muted hover:text-white hover:bg-app-card'
                : 'text-app-muted/30 cursor-not-allowed'
            }`}
            aria-label="Jump to End"
            title={onJumpToEnd ? "Jump to End" : "Not available in forward-only mode"}
          >
            <SkipForward size={18} />
          </button>
        </div>

        {/* Speed Control: "Speed: [Nx] per [aggregation] bar" */}
        <div className="flex items-center gap-2 text-xs text-app-muted">
          <span>Speed:</span>

          {/* Speed Multiplier Dropdown */}
          <div className="relative">
            <select
              value={speedMultiplier}
              onChange={(e) => onSpeedMultiplierChange(Number(e.target.value))}
              className="appearance-none bg-app-bg text-trading-blue font-mono font-bold px-2 py-1 pr-6 rounded border border-app-border cursor-pointer focus:outline-none focus:ring-1 focus:ring-trading-blue"
            >
              {PLAYBACK_SPEEDS.map((s) => (
                <option key={s.value} value={s.value} className="bg-app-card text-app-text">
                  {s.label}
                </option>
              ))}
            </select>
            <ChevronDown size={12} className="absolute right-1.5 top-1/2 -translate-y-1/2 pointer-events-none text-trading-blue" />
          </div>

          <span>per</span>

          {/* Aggregation Dropdown */}
          <div className="relative">
            <select
              value={speedAggregation}
              onChange={(e) => onSpeedAggregationChange(e.target.value as AggregationScale)}
              className="appearance-none bg-app-bg text-trading-blue font-mono font-bold px-2 py-1 pr-6 rounded border border-app-border cursor-pointer focus:outline-none focus:ring-1 focus:ring-trading-blue"
            >
              {availableSpeedAggregations.map((opt) => (
                <option key={opt.value} value={opt.value} className="bg-app-card text-app-text">
                  {opt.label}
                </option>
              ))}
            </select>
            <ChevronDown size={12} className="absolute right-1.5 top-1/2 -translate-y-1/2 pointer-events-none text-trading-blue" />
          </div>

          <span>bar</span>
        </div>

        {/* Linger Toggle */}
        {onToggleLinger && (
          <button
            onClick={onToggleLinger}
            className={`flex items-center gap-1.5 px-2 py-1 rounded border transition-colors ${
              lingerEnabled
                ? 'bg-trading-orange/10 border-trading-orange/30 text-trading-orange hover:bg-trading-orange/20'
                : 'bg-app-bg border-app-border text-app-muted hover:text-white hover:bg-app-card'
            }`}
            title={lingerEnabled ? "Linger ON: Pause on events" : "Linger OFF: Continuous playback"}
            aria-label={lingerEnabled ? "Disable linger (pause on events)" : "Enable linger (pause on events)"}
          >
            {lingerEnabled ? <Timer size={14} /> : <TimerOff size={14} />}
            <span className="text-xs font-medium">Linger</span>
          </button>
        )}

        {/* Process Till (#328) */}
        {onProcessTill && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-app-muted">Till:</span>
            <input
              type="text"
              value={processTillInput}
              onChange={(e) => {
                setProcessTillInput(e.target.value);
                setProcessTillError(null);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleProcessTill();
              }}
              placeholder={currentCsvIndex !== undefined ? `> ${currentCsvIndex}` : 'CSV index'}
              disabled={isProcessingTill || isPlaying}
              className={`w-20 px-2 py-1 text-xs font-mono bg-app-bg border rounded focus:outline-none focus:ring-1 focus:ring-trading-blue ${
                processTillError ? 'border-trading-bear' : 'border-app-border'
              } disabled:opacity-50`}
            />
            <button
              onClick={handleProcessTill}
              disabled={isProcessingTill || isPlaying || !processTillInput.trim()}
              className="p-1.5 rounded border border-app-border bg-app-bg text-app-muted hover:text-white hover:bg-app-card transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title={isPlaying ? "Stop playback first" : "Process till target index"}
              aria-label="Process till target"
            >
              {isProcessingTill ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Forward size={14} />
              )}
            </button>
            {processTillError && (
              <span className="text-xs text-trading-bear">{processTillError}</span>
            )}
          </div>
        )}
      </div>

      {/* Center: Linger Status */}
      <div className="hidden md:flex flex-1 justify-center">
        {isLingering ? (
          <div className="flex items-center gap-2 text-trading-orange bg-trading-orange/10 px-4 py-1.5 rounded-full border border-trading-orange/20 animate-fade-in">
            {/* Previous button - only show when multiple events */}
            {lingerQueuePosition && lingerQueuePosition.total > 1 && (
              <button
                onClick={onNavigatePrev}
                disabled={lingerQueuePosition.current <= 1}
                className={`p-0.5 rounded transition-colors ${
                  lingerQueuePosition.current <= 1
                    ? 'text-trading-orange/30 cursor-not-allowed'
                    : 'text-trading-orange hover:text-white hover:bg-trading-orange/30'
                }`}
                aria-label="Previous swing"
                title="Previous swing (←)"
              >
                <ChevronLeft size={16} />
              </button>
            )}

            <Clock size={14} />
            <span className="text-xs font-semibold uppercase tracking-wide">
              {lingerEventType || 'EVENT'} ({Math.ceil(lingerTimeLeft)}s)
            </span>

            {/* Queue position and next button - only show when multiple events */}
            {lingerQueuePosition && lingerQueuePosition.total > 1 && (
              <>
                <span className="text-xs font-mono text-trading-orange/70">
                  [{lingerQueuePosition.current}/{lingerQueuePosition.total}]
                </span>
                <button
                  onClick={onNavigateNext}
                  disabled={lingerQueuePosition.current >= lingerQueuePosition.total}
                  className={`p-0.5 rounded transition-colors ${
                    lingerQueuePosition.current >= lingerQueuePosition.total
                      ? 'text-trading-orange/30 cursor-not-allowed'
                      : 'text-trading-orange hover:text-white hover:bg-trading-orange/30'
                  }`}
                  aria-label="Next swing"
                  title="Next swing (→)"
                >
                  <ChevronRight size={16} />
                </button>
              </>
            )}

            {/* Dismiss button */}
            <button
              onClick={onDismissLinger}
              className="p-0.5 rounded transition-colors text-trading-orange hover:text-white hover:bg-trading-orange/30 ml-1"
              aria-label="Dismiss and continue"
              title="Dismiss and continue"
            >
              <X size={14} />
            </button>
          </div>
        ) : (
          <div className="h-8" /> /* Spacer */
        )}
      </div>

      {/* Right: Event Counter and Bar Counter */}
      <div className="flex items-center gap-4">
        {/* Event Counter - only show if we have event navigation */}
        {onJumpToNextEvent && (
          <div className="text-right">
            <span className="text-[10px] text-app-muted uppercase tracking-wider block">Event</span>
            <div className="font-mono text-sm tabular-nums text-app-text">
              {totalEvents > 0 ? (
                <>
                  <span className="text-trading-blue font-bold">{currentEventIndex + 1}</span>
                  <span className="text-app-muted mx-1">/</span>
                  {totalEvents}
                  {!hasNextEvent && <span className="text-trading-orange ml-1 text-xs">(end)</span>}
                </>
              ) : (
                <span className="text-app-muted">--</span>
              )}
            </div>
          </div>
        )}

        {/* Bar Counter - different display for forward playback vs legacy */}
        {isForwardPlayback ? (
          // Forward playback: show bar counter, calibrated, offset, remaining
          <div className="flex items-center gap-4">
            <div className="text-right">
              <span className="text-[10px] text-app-muted uppercase tracking-wider block">Bar</span>
              <div className="font-mono text-sm tabular-nums text-white font-bold">
                {formatCount(Math.max(1, currentBar - calibrationBarCount! + 2))}
              </div>
            </div>
            <div className="text-right">
              <span className="text-[10px] text-app-muted uppercase tracking-wider block">Calibrated</span>
              <div className="font-mono text-sm tabular-nums text-trading-blue font-bold">
                {formatCount(calibrationBarCount!)}
              </div>
            </div>
            <div className="text-right">
              <span className="text-[10px] text-app-muted uppercase tracking-wider block">Offset</span>
              <div className="font-mono text-sm tabular-nums text-app-text">
                {formatCount(windowOffset || 0)}
              </div>
            </div>
            <div className="text-right">
              <span className="text-[10px] text-app-muted uppercase tracking-wider block">Remaining</span>
              <div className="font-mono text-sm tabular-nums text-app-text">
                {formatCount(remainingBars)}
              </div>
            </div>
          </div>
        ) : (
          // Legacy mode: show current bar / total bars
          <>
            <div className="text-right">
              <span className="text-[10px] text-app-muted uppercase tracking-wider block">Current Bar</span>
              <div className="font-mono text-sm tabular-nums text-app-text">
                <span className="text-white font-bold">{(currentBar + 1).toLocaleString()}</span>
                <span className="text-app-muted mx-1">/</span>
                {totalBars.toLocaleString()}
              </div>
            </div>

            {/* Progress Bar */}
            <div className="w-32 h-2 bg-app-bg rounded-full overflow-hidden border border-app-border hidden sm:block">
              <div
                className="h-full bg-trading-blue transition-all duration-100"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
};
