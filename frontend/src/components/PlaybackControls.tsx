import React from 'react';
import { Play, Pause, SkipBack, SkipForward, FastForward, Rewind, Clock } from 'lucide-react';
import { PLAYBACK_SPEEDS } from '../constants';
import { PlaybackState } from '../types';

interface PlaybackControlsProps {
  playbackState: PlaybackState;
  onPlayPause: () => void;
  onStepBack: () => void;
  onStepForward: () => void;
  onJumpToStart: () => void;
  onJumpToEnd: () => void;
  currentBar: number;
  totalBars: number;
  playbackSpeed: number;
  onSpeedChange: (speed: number) => void;
  isLingering: boolean;
  lingerTimeLeft: number;
  lingerTotalTime: number;
  lingerEventType?: string;
  lingerQueuePosition?: { current: number; total: number };
}

export const PlaybackControls: React.FC<PlaybackControlsProps> = ({
  playbackState,
  onPlayPause,
  onStepBack,
  onStepForward,
  onJumpToStart,
  onJumpToEnd,
  currentBar,
  totalBars,
  playbackSpeed,
  onSpeedChange,
  isLingering,
  lingerTimeLeft,
  lingerTotalTime,
  lingerEventType,
  lingerQueuePosition,
}) => {
  const isPlaying = playbackState === PlaybackState.PLAYING;

  // Timer wheel calculation
  const radius = 22;
  const circumference = 2 * Math.PI * radius;
  const progress = isLingering ? (lingerTimeLeft / lingerTotalTime) : 0;
  const dashOffset = circumference - (progress * circumference);

  // Progress bar percentage
  const progressPercent = totalBars > 0 ? (currentBar / totalBars) * 100 : 0;

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
            onClick={onStepBack}
            className="p-2 text-app-muted hover:text-white hover:bg-app-card rounded-full transition-colors"
            aria-label="Step Back"
            title="Step Back"
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
            onClick={onStepForward}
            className="p-2 text-app-muted hover:text-white hover:bg-app-card rounded-full transition-colors"
            aria-label="Step Forward"
            title="Step Forward"
          >
            <FastForward size={18} />
          </button>
          <button
            onClick={onJumpToEnd}
            className="p-2 text-app-muted hover:text-white hover:bg-app-card rounded-full transition-colors"
            aria-label="Jump to End"
            title="Jump to End"
          >
            <SkipForward size={18} />
          </button>
        </div>

        {/* Speed Selector */}
        <div className="flex items-center bg-app-bg rounded-md p-0.5 border border-app-border">
          {PLAYBACK_SPEEDS.map((s) => (
            <button
              key={s.value}
              onClick={() => onSpeedChange(s.value)}
              className={`
                px-2 py-1 text-xs font-mono rounded transition-colors
                ${playbackSpeed === s.value
                  ? 'bg-app-card text-trading-blue font-bold shadow-sm'
                  : 'text-app-muted hover:text-white'
                }
              `}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Center: Linger Status */}
      <div className="hidden md:flex flex-1 justify-center">
        {isLingering ? (
          <div className="flex items-center gap-2 text-trading-orange bg-trading-orange/10 px-4 py-1.5 rounded-full border border-trading-orange/20 animate-fade-in">
            <Clock size={14} />
            <span className="text-xs font-semibold uppercase tracking-wide">
              {lingerEventType || 'EVENT'} ({Math.ceil(lingerTimeLeft)}s)
              {lingerQueuePosition && lingerQueuePosition.total > 1 && (
                <span className="ml-1 text-trading-orange/70">
                  [{lingerQueuePosition.current}/{lingerQueuePosition.total}]
                </span>
              )}
            </span>
          </div>
        ) : (
          <div className="h-8" /> /* Spacer */
        )}
      </div>

      {/* Right: Bar Counter */}
      <div className="flex items-center gap-4">
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
      </div>
    </div>
  );
};
