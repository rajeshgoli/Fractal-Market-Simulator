import React, { useState, useEffect, useRef } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChartArea } from './components/ChartArea';
import { PlaybackControls } from './components/PlaybackControls';
import { ExplanationPanel } from './components/ExplanationPanel';
import { INITIAL_FILTERS, MOCK_CHART_DATA_1H, MOCK_CHART_DATA_5M, MOCK_SWING } from './constants';
import { FilterState, SwingData } from './types';
import { Monitor, Menu, Clock } from 'lucide-react';

const App: React.FC = () => {
  // State
  const [filters, setFilters] = useState<FilterState[]>(INITIAL_FILTERS);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [currentBar, setCurrentBar] = useState(1234);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  
  // Linger Simulation State
  const [isLingering, setIsLingering] = useState(false);
  const [lingerTimeLeft, setLingerTimeLeft] = useState(30);
  const LINGER_DURATION = 30;

  // Animation Refs
  const lastTimeRef = useRef<number>(0);
  const requestRef = useRef<number>(0);

  // Toggle Filter Handler
  const handleToggleFilter = (id: string) => {
    setFilters(prev => prev.map(f => f.id === id ? { ...f, isEnabled: !f.isEnabled } : f));
  };

  // Playback Loop Simulation
  useEffect(() => {
    const animate = (time: number) => {
      if (lastTimeRef.current !== undefined) {
        const deltaTime = (time - lastTimeRef.current) / 1000;
        
        if (isPlaying) {
          // Normal playback
          if (!isLingering) {
            // Simulate bar progression
            setCurrentBar(prev => {
              const next = prev + (0.1 * playbackSpeed);
              // Mock Event Trigger at specific bar (demo purpose)
              if (Math.floor(next) > Math.floor(prev) && Math.floor(next) % 100 === 0) {
                 // Trigger linger
                 setIsLingering(true);
                 setLingerTimeLeft(LINGER_DURATION);
                 setIsPlaying(false); // Actually pause playback logic, but keep UI in linger state
                 return Math.floor(next);
              }
              return next;
            });
          }
        }

        // Linger Countdown Logic
        if (isLingering && isPlaying) {
          // If user pressed Play during linger, we skip linger
          setIsLingering(false);
        } else if (isLingering && !isPlaying) {
           // If we are lingering, count down (visual only unless we want auto-resume)
           setLingerTimeLeft(prev => {
             if (prev <= 0) {
               setIsLingering(false);
               setIsPlaying(true); // Auto resume
               return 0;
             }
             return prev - deltaTime;
           });
        }
      }
      lastTimeRef.current = time;
      requestRef.current = requestAnimationFrame(animate);
    };

    requestRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(requestRef.current!);
  }, [isPlaying, isLingering, playbackSpeed]);


  const handlePlayPause = () => {
    if (isLingering) {
      // If lingering, play button acts as "Skip Linger"
      setIsLingering(false);
      setIsPlaying(true);
    } else {
      setIsPlaying(!isPlaying);
    }
  };

  return (
    <div className="flex flex-col h-screen w-full bg-app-bg text-app-text font-sans overflow-hidden">
      
      {/* 1. Header */}
      <header className="h-12 bg-app-secondary border-b border-app-border flex items-center justify-between px-4 shrink-0 z-20">
        <div className="flex items-center gap-4">
          <button 
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className="text-app-muted hover:text-white p-1 rounded hover:bg-app-card"
          >
            <Menu size={20} />
          </button>
          <div className="flex items-center gap-2">
            <Monitor className="text-trading-blue" size={18} />
            <h1 className="font-bold tracking-wide text-sm">MARKET REPLAY <span className="text-app-muted font-normal">| ALPHA V2.1</span></h1>
          </div>
        </div>

        <div className="flex items-center gap-6">
           {/* Current Time Position */}
           <div className="flex items-center gap-2 text-sm font-mono tabular-nums text-app-text bg-app-card px-3 py-1 rounded border border-app-border/50">
             <Clock size={14} className="text-app-muted" />
             <span>Mar 15, 2024</span>
             <span className="text-app-border">|</span>
             <span>14:32:05</span>
           </div>
           
           <div className="flex items-center gap-2">
             <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
             <span className="text-xs font-bold text-app-muted uppercase">System Ready</span>
           </div>
        </div>
      </header>

      {/* 2. Main Layout Grid */}
      <div className="flex-1 flex min-h-0">
        
        {/* Sidebar */}
        <div className={`${isSidebarOpen ? 'w-64' : 'w-0'} transition-all duration-300 ease-in-out overflow-hidden`}>
          <Sidebar filters={filters} onToggleFilter={handleToggleFilter} className="w-64" />
        </div>

        {/* Center Content */}
        <main className="flex-1 flex flex-col min-w-0">
          
          {/* Charts Area */}
          <ChartArea data1H={MOCK_CHART_DATA_1H} data5M={MOCK_CHART_DATA_5M} />

          {/* Playback Controls (Sticky under chart) */}
          <div className="shrink-0 z-10">
            <PlaybackControls 
              isPlaying={isPlaying} 
              onPlayPause={handlePlayPause}
              currentBar={Math.floor(currentBar)}
              totalBars={50000}
              playbackSpeed={playbackSpeed}
              onSpeedChange={setPlaybackSpeed}
              isLingering={isLingering}
              lingerTimeLeft={lingerTimeLeft}
              lingerTotalTime={LINGER_DURATION}
            />
          </div>

          {/* Explanation Panel (Fixed height at bottom) */}
          <div className="h-48 md:h-56 shrink-0 transition-all duration-300">
            <ExplanationPanel swing={isLingering ? MOCK_SWING : null} />
          </div>

        </main>
      </div>
    </div>
  );
};

export default App;