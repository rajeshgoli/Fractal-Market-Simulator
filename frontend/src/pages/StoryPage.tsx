import { Link } from 'react-router-dom';
import { Navbar } from './LandingPage/components/Navbar';
import { Footer } from '../components/Footer';

export const StoryPage: React.FC = () => {
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

  const quotes = [
    "There is no moat. There's only tempo. Whoever compounds learning fastest wins.",
    "The vision is uncompromising. How I get there? Totally compromising.",
    "This is what a technical VP does at FAANG. Except I'm one person.",
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

        <div className="max-w-3xl mx-auto text-center">
          <h1 className="text-5xl md:text-7xl font-black mb-6 tracking-tighter leading-none text-white">
            Why This
            <br />
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 via-white to-blue-500">
              Exists
            </span>
          </h1>

          <p className="text-lg md:text-xl text-slate-400 leading-relaxed">
            Twelve years building products. Six months of intense study. One realization: the algos are fractal to the core.
          </p>
        </div>
      </section>

      {/* The Builder Section */}
      <section className="py-20 px-6">
        <div className="max-w-3xl mx-auto">
          <div className="prose-container">
            <p className="text-lg text-slate-300 leading-relaxed mb-6">
              I've spent over a decade building products at companies you'd recognize. I learned how to ship, how to scale, how to lead teams through complexity.
            </p>
            <p className="text-lg text-slate-300 leading-relaxed mb-6">
              For most of that time, I believed markets were a random walk. Buy index funds, ignore the noise, don't try to be clever. That was the rational thing to do.
            </p>
            <p className="text-lg text-slate-300 leading-relaxed mb-6">
              Around 2021, I got curious. Started watching price action. Didn't know what I was looking for, but something felt off about the "it's all random" story.
            </p>
            <p className="text-lg text-slate-300 leading-relaxed mb-6">
              Six months of intensive study changed everything. SPX and ES aren't random—they're fractal. Swings within swings within swings. Fibonacci levels that shouldn't matter, but do. A skeleton underneath the chaos.
            </p>
            <p className="text-lg text-white font-medium">
              Now I'm building the tools to prove it.
            </p>
          </div>
        </div>
      </section>

      {/* The Moment Section */}
      <section className="py-20 px-6 bg-slate-950/50">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-8">The Tooling Finally Exists</h2>

          <div className="prose-container">
            <p className="text-lg text-slate-300 leading-relaxed mb-6">
              2025 changed everything.
            </p>
            <p className="text-lg text-slate-300 leading-relaxed mb-6">
              AI-assisted development isn't autocomplete on steroids. It's a fundamental shift in what one person can build.
            </p>
            <p className="text-lg text-slate-300 leading-relaxed mb-6">
              I designed a workflow: four personas, structured handoffs, forced review gates. The system building the system that builds the system.
            </p>
            <p className="text-lg text-white font-medium">
              37,000 lines in 23 days. Not vibe coding. Architected.
            </p>
          </div>
        </div>
      </section>

      {/* The Philosophy Section */}
      <section className="py-20 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-3 gap-6">
            {quotes.map((quote, i) => (
              <div
                key={i}
                className="glass p-8 rounded-xl border-slate-700/50 hover:border-cyan-500/30 transition-all"
              >
                <div className="text-4xl text-cyan-400 mb-4">"</div>
                <p className="text-lg text-white italic leading-relaxed">
                  {quote}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* The Fractal Stack Section */}
      <section className="py-20 px-6 bg-slate-950/50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-12">The Stack</h2>

          <div className="space-y-4">
            {/* Market Structure Layer */}
            <div className="glass p-6 rounded-xl border-cyan-500/30">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-cyan-400">MARKET STRUCTURE</h3>
              </div>
              <p className="text-slate-300 mb-2">Monthly → Daily → Hourly → Minute</p>
              <p className="text-sm text-slate-500">(Hierarchical DAG, Fibonacci levels)</p>
            </div>

            {/* Codebase Layer */}
            <div className="glass p-6 rounded-xl border-slate-600">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-slate-300">CODEBASE</h3>
              </div>
              <p className="text-slate-300 mb-2">~37k lines, 747 commits, 23 days</p>
              <p className="text-sm text-slate-500">(LegDetector → ReferenceLayer → UI)</p>
            </div>

            {/* Workflow Layer */}
            <div className="glass p-6 rounded-xl border-slate-600">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-slate-300">WORKFLOW</h3>
              </div>
              <p className="text-slate-300 mb-2">3,546 prompts, 456 persona invocations, 87 handoffs</p>
              <p className="text-sm text-slate-500">(Director → Product → Architect → Engineer)</p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-8">See What I Built</h2>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={handleLogin}
              className="px-8 py-4 bg-white text-slate-900 font-bold rounded-xl hover:bg-cyan-500 hover:text-white transition-all transform hover:scale-105 active:scale-95 shadow-2xl shadow-cyan-500/20"
            >
              Try the Demo
            </button>
            <Link
              to="/developers"
              className="px-8 py-4 glass text-white font-bold rounded-xl hover:bg-white/10 transition-all border border-white/20"
            >
              Read the Technical Deep-Dive
            </Link>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
};
