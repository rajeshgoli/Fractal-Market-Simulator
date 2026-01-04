import { useState, useEffect } from 'react';
import { Navbar } from './LandingPage/components/Navbar';
import { Footer } from '../components/Footer';
import { StatsBanner } from '../components/StatsBanner';

// Icons from Lucide React (inline SVGs for simplicity)
const CompassIcon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <circle cx="12" cy="12" r="10" />
    <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" fill="currentColor" />
  </svg>
);

const TargetIcon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <circle cx="12" cy="12" r="10" />
    <circle cx="12" cy="12" r="6" />
    <circle cx="12" cy="12" r="2" />
  </svg>
);

const Building2Icon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z" />
    <path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
    <path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2" />
    <path d="M10 6h4" />
    <path d="M10 10h4" />
    <path d="M10 14h4" />
    <path d="M10 18h4" />
  </svg>
);

const CodeIcon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <polyline points="16 18 22 12 16 6" />
    <polyline points="8 6 2 12 8 18" />
  </svg>
);

const ZapIcon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
  </svg>
);

const EyeOffIcon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
    <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
    <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
    <line x1="2" x2="22" y1="2" y2="22" />
  </svg>
);

const BoxIcon = () => (
  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
    <path d="m3.3 7 8.7 5 8.7-5" />
    <path d="M12 22V12" />
  </svg>
);

export const DevelopersPage: React.FC = () => {
  const [animationStep, setAnimationStep] = useState(0);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    setIsVisible(true);
    const interval = setInterval(() => {
      setAnimationStep((prev) => (prev + 1) % 4);
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  const handleLogin = async () => {
    try {
      const res = await fetch('/auth/status');
      const data = await res.json();
      if (data.multi_tenant) {
        window.location.href = '/login';
      } else {
        window.location.href = '/app';
      }
    } catch {
      window.location.href = '/app';
    }
  };

  const personas = [
    { name: 'Director', icon: <CompassIcon />, role: 'Evolves the workflow itself', artifact: '.claude/personas/*' },
    { name: 'Product', icon: <TargetIcon />, role: 'Owns direction and priorities', artifact: 'product_direction.md' },
    { name: 'Architect', icon: <Building2Icon />, role: 'Reviews, simplifies, deletes', artifact: 'architect_notes.md' },
    { name: 'Engineer', icon: <CodeIcon />, role: 'Ships code against issues', artifact: 'GitHub Issues' },
  ];

  const deletedFeatures = [
    { feature: 'S/M/L/XL classification system', lines: '1,300', reason: 'Replaced with continuous bins' },
    { feature: 'Duplicate cache layers', lines: '1,692', reason: 'API namespace restructure' },
    { feature: 'Calibration concept', lines: '681', reason: 'Created bugs, removed entirely' },
    { feature: 'Confluence zones UI', lines: '213', reason: 'Too cluttered, users ignored it' },
    { feature: 'CLI legacy parameters', lines: '260', reason: 'Superseded, no tombstones' },
  ];

  const archCards = [
    { title: 'O(n log k) Swing Detection', copy: 'Each bar comes in, update the graph, done. No rescanning history.', icon: <ZapIcon /> },
    { title: 'No Lookahead Guarantee', copy: 'Levels appear before price gets there. Causal constraint enforced at the algorithm level.', icon: <EyeOffIcon /> },
    { title: 'Container-Ready', copy: "Runs in one box? Make it run in many. No hidden state, no local file dependencies.", icon: <BoxIcon /> },
  ];

  return (
    <div className="min-h-screen fractal-bg">
      <Navbar onLogin={handleLogin} />

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 px-6 overflow-hidden">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-7xl h-full -z-10">
          <div className="absolute top-[10%] left-[10%] w-[500px] h-[500px] bg-cyan-500/10 rounded-full blur-[120px] animate-pulse"></div>
          <div className="absolute bottom-[20%] right-[10%] w-[400px] h-[400px] bg-blue-600/10 rounded-full blur-[100px]"></div>
        </div>

        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-5xl md:text-7xl font-black mb-6 tracking-tighter leading-none">
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 via-white to-blue-500">
              37,000 Lines
            </span>
            <br />
            <span className="text-white">in 23 Days</span>
          </h1>

          <p className="text-lg md:text-xl text-slate-400 mb-12 leading-relaxed max-w-2xl mx-auto">
            This is the new way of working. Four personas. Structured handoffs. Deletion discipline. One person shipping at team velocity.
          </p>

          {/* Animated Workflow Diagram */}
          <div className={`transition-all duration-1000 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
            <div className="flex items-center justify-center gap-2 md:gap-4 flex-wrap">
              {personas.map((persona, i) => (
                <div key={persona.name} className="flex items-center">
                  <div
                    className={`px-4 py-3 rounded-lg border transition-all duration-500 ${
                      animationStep === i
                        ? 'bg-cyan-500/20 border-cyan-500 scale-110'
                        : 'bg-slate-800/50 border-slate-700 scale-100'
                    }`}
                  >
                    <div className={`text-sm font-bold ${animationStep === i ? 'text-cyan-400' : 'text-slate-300'}`}>
                      {persona.name}
                    </div>
                  </div>
                  {i < personas.length - 1 && (
                    <svg className="w-6 h-6 text-slate-600 mx-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-4 flex items-center justify-center gap-2 text-slate-500">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <span className="text-xs font-mono">Handoff</span>
            </div>
          </div>
        </div>
      </section>

      {/* The Numbers Section */}
      <section className="py-20 px-6 bg-slate-950/50">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-12">The Numbers</h2>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
            {[
              { value: '747', label: 'commits' },
              { value: '37,000', label: 'lines' },
              { value: '600+', label: 'tests' },
              { value: '23', label: 'days' },
            ].map((stat) => (
              <div key={stat.label} className="text-center">
                <p className="text-4xl md:text-5xl font-mono font-bold text-white mb-2">{stat.value}</p>
                <p className="text-xs text-slate-500 uppercase tracking-widest">{stat.label}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {[
              { value: '3,546', label: 'prompts' },
              { value: '456', label: 'skill uses' },
              { value: '87', label: 'handoffs' },
              { value: '10', label: 'max pending' },
            ].map((stat) => (
              <div key={stat.label} className="text-center">
                <p className="text-4xl md:text-5xl font-mono font-bold text-white mb-2">{stat.value}</p>
                <p className="text-xs text-slate-500 uppercase tracking-widest">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Not Vibe Coding Section */}
      <section className="py-20 px-6">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-4">Not Vibe Coding</h2>
          <p className="text-slate-400 text-center mb-12 max-w-2xl mx-auto">
            AI doesn't replace expertise. It amplifies it. You still need to know what you're building.
          </p>

          <div className="space-y-8">
            {/* The Problem */}
            <div className="glass p-6 rounded-xl border-red-500/30">
              <h3 className="text-lg font-bold text-red-400 mb-3">Vibe Coding</h3>
              <p className="text-slate-300 mb-4">
                "Make it work." Ship fast, fix later. The AI writes code, you approve it, things break at scale, you prompt again. Repeat until exhausted.
              </p>
              <p className="text-slate-500 text-sm italic">
                Works for prototypes. Breaks for production.
              </p>
            </div>

            {/* The Solution */}
            <div className="glass p-6 rounded-xl border-cyan-500/30">
              <h3 className="text-lg font-bold text-cyan-400 mb-3">Intentional Architecture</h3>
              <p className="text-slate-300 mb-4">
                You understand the system. You make the architectural calls. The AI executes at 10x speed—but you're steering.
              </p>
            </div>

            {/* Real Examples */}
            <div className="mt-12">
              <h3 className="text-lg font-bold text-white mb-6 text-center">Real prompts from this project:</h3>
              <div className="space-y-4">
                <div className="bg-slate-900 p-4 rounded-lg border border-slate-700">
                  <p className="font-mono text-sm text-slate-300 leading-relaxed">
                    "Audit algorithm complexity. Review bar aggregation, swing detection, and event detection for any <span className="text-cyan-400">O(N²) or worse</span> patterns. Anything that won't scale to 16 million bars needs to be flagged."
                  </p>
                </div>
                <div className="bg-slate-900 p-4 rounded-lg border border-slate-700">
                  <p className="font-mono text-sm text-slate-300 leading-relaxed">
                    "Remember if you load more data, there can be <span className="text-cyan-400">no lookahead</span>. Swing detection should work bar-by-bar. If user clicks next event, run 'process bar' in a loop until something interesting happens."
                  </p>
                </div>
                <div className="bg-slate-900 p-4 rounded-lg border border-slate-700">
                  <p className="font-mono text-sm text-slate-300 leading-relaxed">
                    "The direction of bugs indicate a fundamental misunderstanding. We may want to <span className="text-cyan-400">rewrite as an incremental algo</span>. Then call the same algo in a loop for calibration. This prevents all the lookahead type bugs."
                  </p>
                </div>
                <div className="bg-slate-900 p-4 rounded-lg border border-slate-700">
                  <p className="font-mono text-sm text-slate-300 leading-relaxed">
                    "I am convinced there's a <span className="text-cyan-400">O(N log K) approach if we use a DAG</span>. Let me demonstrate... at all points we have two extremas and one defended pivot. The rules naturally apply because you're enforcing strict temporal ordering."
                  </p>
                </div>
                <div className="bg-slate-900 p-4 rounded-lg border border-slate-700">
                  <p className="font-mono text-sm text-slate-300 leading-relaxed">
                    "If 2x extension happened, the leg is <span className="text-cyan-400">fatally origin breached</span>. What does it mean to reform? It served as a reference from formation until completion. What more can it do now? <span className="text-cyan-400">Completion is terminal.</span>"
                  </p>
                </div>
              </div>
            </div>

            {/* The Point */}
            <div className="glass p-8 rounded-2xl border-white/10 mt-8">
              <p className="text-lg text-white leading-relaxed text-center">
                AI doesn't come with opinions about O(N²) complexity or lookahead corruption. It needs direction.
                <br /><br />
                <span className="text-slate-400">The prompts above aren't clever tricks—they're just what I'd tell any engineer on my team.</span>
                <br /><br />
                <span className="text-cyan-400 font-medium">AI amplifies expertise. Bring yours.</span>
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* The Workflow Section */}
      <section className="py-20 px-6">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-12">The Workflow</h2>

          <div className="grid md:grid-cols-4 gap-6">
            {personas.map((persona) => (
              <div key={persona.name} className="glass p-6 rounded-xl hover:border-cyan-500/50 transition-all">
                <div className="w-12 h-12 bg-cyan-500/10 rounded-lg flex items-center justify-center text-cyan-400 mb-4">
                  {persona.icon}
                </div>
                <h3 className="text-lg font-bold text-white mb-2">{persona.name}</h3>
                <p className="text-sm text-slate-400 mb-4">{persona.role}</p>
                <code className="text-xs font-mono text-cyan-400 bg-slate-800 px-2 py-1 rounded">
                  {persona.artifact}
                </code>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* The Deletion Discipline Section */}
      <section className="py-20 px-6">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-4">The Deletion Discipline</h2>
          <p className="text-slate-400 text-center mb-6 max-w-2xl mx-auto">
            4,000+ lines deleted across major refactors. The codebase stays clean because we delete aggressively.
          </p>
          <p className="text-cyan-400 text-center mb-12 font-mono text-sm">
            "Delete means delete. No legacy, no tombstones, don't retain it with another name. Delete and fix what breaks."
          </p>

          <div className="overflow-x-auto mb-12">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="py-4 px-4 text-xs text-slate-500 uppercase tracking-widest font-bold">Feature</th>
                  <th className="py-4 px-4 text-xs text-slate-500 uppercase tracking-widest font-bold">Lines</th>
                  <th className="py-4 px-4 text-xs text-slate-500 uppercase tracking-widest font-bold">Reason</th>
                </tr>
              </thead>
              <tbody>
                {deletedFeatures.map((item) => (
                  <tr key={item.feature} className="border-b border-slate-800">
                    <td className="py-4 px-4 text-white font-medium">{item.feature}</td>
                    <td className="py-4 px-4 font-mono text-red-400">{item.lines}</td>
                    <td className="py-4 px-4 text-slate-400">{item.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="glass p-8 rounded-2xl border-cyan-500/30 max-w-3xl mx-auto">
            <div className="flex items-start gap-4">
              <div className="text-4xl text-cyan-400">"</div>
              <p className="text-lg md:text-xl text-white italic leading-relaxed">
                Calibration was creating bugs. I didn't deprecate it, didn't add a flag, didn't leave a comment. I deleted the concept. 681 lines gone. Fix what breaks.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Architecture Highlights Section */}
      <section className="py-20 px-6 bg-slate-950/50">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-12">Architecture Highlights</h2>

          <div className="grid md:grid-cols-3 gap-8">
            {archCards.map((card) => (
              <div key={card.title} className="glass p-8 rounded-xl hover:border-cyan-500/50 transition-all">
                <div className="w-12 h-12 bg-cyan-500/10 rounded-lg flex items-center justify-center text-cyan-400 mb-6">
                  {card.icon}
                </div>
                <h3 className="text-xl font-bold text-white mb-4">{card.title}</h3>
                <p className="text-slate-400 leading-relaxed">{card.copy}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Stats Banner */}
      <StatsBanner />

      {/* CTA Section */}
      <section className="py-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-8">See It In Action</h2>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={handleLogin}
              className="px-8 py-4 bg-white text-slate-900 font-bold rounded-xl hover:bg-cyan-500 hover:text-white transition-all transform hover:scale-105 active:scale-95 shadow-2xl shadow-cyan-500/20"
            >
              Try the Demo
            </button>
            <a
              href="https://github.com/rajeshgoli/Fractal-Market-Simulator"
              target="_blank"
              rel="noopener noreferrer"
              className="px-8 py-4 glass text-white font-bold rounded-xl hover:bg-white/10 transition-all border border-white/20"
            >
              View on GitHub
            </a>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
};
