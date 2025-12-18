import React, { useState, useEffect, useRef } from 'react';
import { Play, Pause, SkipBack, SkipForward, FastForward, Rewind, Clock } from 'lucide-react';

interface PlaybackControlsProps {
  isPlaying: boolean;
  onPlayPause: () => void;
  currentBar: number;
  totalBars: number;
  playbackSpeed: number;
  onSpeedChange: (speed: number) => void;
  isLingering: boolean;
  lingerTimeLeft: number; // in seconds
  lingerTotalTime: number;
}

export const PlaybackControls: React.FC<PlaybackControlsProps> = ({
  isPlaying,
  onPlayPause,
  currentBar,
  totalBars,
  playbackSpeed,
  onSpeedChange,
  isLingering,
  lingerTimeLeft,
  lingerTotalTime
}) => {
  const speeds = [0.5, 1, 2, 5, 10];

  // Timer Wheel Calculation
  // Calculate stroke dash array for circular progress
  const radius = 22; // Radius of circle
  const circumference = 2 * Math.PI * radius;
  const progress = isLingering ? (lingerTimeLeft / lingerTotalTime) : 0;
  const dashOffset = circumference - (progress * circumference);

  return (
    <div className="bg-app-secondary border-t border-b border-app-border p-3 flex flex-col md:flex-row items-center justify-between gap-4 select-none">
      
      {/* Left: Transport Controls */}
      <div className="flex items-center gap-4">
        
        {/* Buttons Group */}
        <div className="flex items-center gap-2">
          <button className="p-2 text-app-muted hover:text-white hover:bg-app-card rounded-full transition-colors" aria-label="Start">
            <SkipBack size={18} />
          </button>
          <button className="p-2 text-app-muted hover:text-white hover:bg-app-card rounded-full transition-colors" aria-label="Step Back">
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
              {isPlaying ? <Pause size={20} fill="currentColor" /> : <Play size={20} fill="currentColor" className="ml-0.5" />}
            </button>
          </div>

          <button className="p-2 text-app-muted hover:text-white hover:bg-app-card rounded-full transition-colors" aria-label="Step Forward">
            <FastForward size={18} />
          </button>
          <button className="p-2 text-app-muted hover:text-white hover:bg-app-card rounded-full transition-colors" aria-label="End">
            <SkipForward size={18} />
          </button>
        </div>

        {/* Speed Selector */}
        <div className="flex items-center bg-app-bg rounded-md p-0.5 border border-app-border">
          {speeds.map((s) => (
            <button
              key={s}
              onClick={() => onSpeedChange(s)}
              className={`
                px-2 py-1 text-xs font-mono rounded transition-colors
                ${playbackSpeed === s 
                  ? 'bg-app-card text-trading-blue font-bold shadow-sm' 
                  : 'text-app-muted hover:text-white'
                }
              `}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      {/* Center: Status / Linger Message */}
      <div className="hidden md:flex flex-1 justify-center">
         {isLingering ? (
           <div className="flex items-center gap-2 text-trading-orange bg-trading-orange/10 px-4 py-1.5 rounded-full border border-trading-orange/20 animate-fade-in">
             <Clock size={14} className="animate-spin-slow" />
             <span className="text-xs font-semibold uppercase tracking-wide">Auto-Pause: Review Event ({Math.ceil(lingerTimeLeft)}s)</span>
           </div>
         ) : (
           <div className="h-8"></div> /* Spacer to prevent layout jump */
         )}
      </div>

      {/* Right: Bar Counter */}
      <div className="flex items-center gap-4">
        <div className="text-right">
          <span className="text-[10px] text-app-muted uppercase tracking-wider block">Current Bar</span>
          <div className="font-mono text-sm tabular-nums text-app-text">
            <span className="text-white font-bold">{currentBar.toLocaleString()}</span>
            <span className="text-app-muted mx-1">/</span>
            {totalBars.toLocaleString()}
          </div>
        </div>
        
        {/* Progress Bar (Visual only for this demo) */}
        <div className="w-32 h-2 bg-app-bg rounded-full overflow-hidden border border-app-border hidden sm:block">
          <div 
            className="h-full bg-trading-blue" 
            style={{ width: `${(currentBar / totalBars) * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
};