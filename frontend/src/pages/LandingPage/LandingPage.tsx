import { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { MarketChartPreview } from './components/MarketChartPreview';

export const LandingPage: React.FC = () => {
  const [scrollY, setScrollY] = useState(0);

  useEffect(() => {
    const handleScroll = () => setScrollY(window.scrollY);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const features = [
    {
      title: "Find Structure Before Price Does",
      description: "The system identifies swing highs and lows as they form. No repainting. No lookahead. Levels appear before price gets there.",
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
      )
    },
    {
      title: "Fibonacci Levels That Matter",
      description: "0.382, 0.618, 1.0, 1.618—projected from confirmed swings. Watch price respect these levels in real-time.",
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6z" />
        </svg>
      )
    },
    {
      title: "Multi-Timeframe Alignment",
      description: "See how minute structure nests inside hourly, daily, and weekly swings. Trade with the larger structure, not against it.",
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      )
    }
  ];

  const handleLogin = async () => {
    // Check if multi-tenant mode - if so, go to login, otherwise go directly to app
    try {
      const res = await fetch('/auth/status');
      const data = await res.json();
      if (data.multi_tenant) {
        window.location.href = '/login';
      } else {
        window.location.href = '/app';
      }
    } catch {
      // Fallback to app if auth check fails
      window.location.href = '/app';
    }
  };

  return (
    <div className="min-h-screen fractal-bg">
      <Navbar onLogin={handleLogin} />

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 px-6 overflow-hidden">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-7xl h-full -z-10">
          <div className="absolute top-[10%] left-[10%] w-[500px] h-[500px] bg-cyan-500/10 rounded-full blur-[120px] animate-pulse"></div>
          <div className="absolute bottom-[20%] right-[10%] w-[400px] h-[400px] bg-blue-600/10 rounded-full blur-[100px]"></div>
        </div>

        <div className="max-w-7xl mx-auto flex flex-col items-center text-center">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full border border-cyan-500/20 bg-cyan-500/5 mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
            <span className="text-[10px] mono font-bold text-cyan-400 uppercase tracking-widest">Now in Beta</span>
          </div>

          <h1 className="text-5xl md:text-7xl lg:text-8xl font-black mb-6 tracking-tighter leading-none">
            SEE THE <br />
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 via-white to-blue-500">
              STRUCTURE.
            </span>
          </h1>

          <p className="max-w-2xl text-lg md:text-xl text-slate-400 mb-10 leading-relaxed font-medium">
            Price moves in patterns. Swings nest inside swings. This tool finds the skeleton underneath price action—and shows you where the next decision points are.
          </p>

          <div className="flex flex-col sm:flex-row items-center space-y-4 sm:space-y-0 sm:space-x-6 mb-16">
            <button
              onClick={handleLogin}
              className="px-8 py-4 bg-white text-slate-900 font-bold rounded-xl hover:bg-cyan-500 hover:text-white transition-all transform hover:scale-105 active:scale-95 shadow-2xl shadow-cyan-500/20"
            >
              Get Started
            </button>
            <button
              onClick={handleLogin}
              className="px-8 py-4 glass text-white font-bold rounded-xl hover:bg-white/10 transition-all border border-white/20"
            >
              Login
            </button>
          </div>

          <div className="w-full max-w-5xl mx-auto perspective-1000">
             <div
              className="transition-transform duration-500 ease-out"
              style={{ transform: `translateY(${Math.max(0, scrollY * -0.05)}px)` }}
             >
              <MarketChartPreview />
             </div>
          </div>
        </div>
      </section>

      {/* Stats Section - Trader focused */}
      <section className="py-20 border-y border-white/5 bg-slate-950/40 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 grid grid-cols-3 gap-8">
          {[
            { label: 'Retracements', value: '0.618' },
            { label: 'Extensions', value: '1.618' },
            { label: 'Timeframes', value: '1m–1D' },
          ].map((stat, i) => (
            <div key={i} className="text-center">
              <p className="text-3xl font-black text-white mb-1">{stat.value}</p>
              <p className="text-xs mono font-bold text-slate-500 uppercase tracking-widest">{stat.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features Grid */}
      <section id="features" className="py-32 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-3 gap-12">
            {features.map((feature, i) => (
              <div key={i} className="group p-8 rounded-2xl glass hover:border-cyan-500/50 transition-all duration-300">
                <div className="w-12 h-12 bg-cyan-500/10 rounded-lg flex items-center justify-center text-cyan-400 mb-6 group-hover:scale-110 transition-transform">
                  {feature.icon}
                </div>
                <h3 className="text-xl font-bold text-white mb-4">{feature.title}</h3>
                <p className="text-slate-400 leading-relaxed text-sm">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Key Insight Block */}
      <section className="py-20 px-6 bg-gradient-to-b from-transparent to-slate-950">
        <div className="max-w-4xl mx-auto glass p-12 rounded-3xl relative overflow-hidden text-center border-cyan-500/30">
          <div className="absolute inset-0 bg-cyan-500/5 -z-10"></div>
          <h2 className="text-xs mono font-bold text-cyan-400 uppercase tracking-widest mb-6">The Edge</h2>
          <p className="text-2xl md:text-3xl font-medium text-white italic leading-snug">
            "The system found the structure with no lookahead. Price respected the levels. That's the edge."
          </p>
          <div className="mt-8 flex justify-center space-x-12">
             <div className="text-center">
                <p className="text-cyan-400 font-bold">0.382</p>
                <p className="text-[10px] text-slate-500 uppercase">Shallow</p>
             </div>
             <div className="text-center">
                <p className="text-cyan-400 font-bold">0.618</p>
                <p className="text-[10px] text-slate-500 uppercase">Golden</p>
             </div>
             <div className="text-center">
                <p className="text-cyan-400 font-bold">1.618</p>
                <p className="text-[10px] text-slate-500 uppercase">Extension</p>
             </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-20 px-6 border-t border-white/5">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center text-slate-500 text-sm">
          <div className="flex items-center space-x-4 mb-8 md:mb-0">
            <span className="font-bold text-slate-300">FRACTAL MARKET</span>
            <span className="text-slate-700">|</span>
            <span>Structure over noise</span>
          </div>

          <div className="flex space-x-8">
            <a href="https://x.com/rajeshgoli" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">Twitter</a>
            <a href="https://github.com/rajeshgoli/Fractal-Market-Simulator" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">GitHub</a>
          </div>
        </div>
        <div className="max-w-7xl mx-auto mt-12 text-center text-[10px] text-slate-700 uppercase tracking-widest font-bold">
          &copy; 2026 All rights reserved.
        </div>
      </footer>
    </div>
  );
};
