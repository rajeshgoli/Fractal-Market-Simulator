import { Navbar } from './LandingPage/components/Navbar';
import { Footer } from '../components/Footer';

export const TermsPage: React.FC = () => {
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

  return (
    <div className="min-h-screen fractal-bg">
      <Navbar onLogin={handleLogin} />

      <section className="pt-32 pb-20 px-6">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-4xl font-bold text-white mb-8">Terms of Service</h1>
          <p className="text-slate-400 text-sm mb-12">Last updated: January 3, 2026</p>

          <div className="prose prose-invert prose-slate max-w-none space-y-8">
            <section className="bg-red-950/30 border border-red-500/30 rounded-xl p-6 mb-8">
              <h2 className="text-xl font-bold text-red-400 mb-4">IMPORTANT: NOT FINANCIAL ADVICE</h2>
              <p className="text-slate-300 leading-relaxed">
                This software is for <strong>educational and research purposes only</strong>. Nothing
                in this application constitutes financial advice, investment advice, trading advice,
                or any other sort of advice. You should not treat any of the application's content
                as such. <strong>Do not make any financial decisions based on this software.</strong>
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">1. Acceptance of Terms</h2>
              <p className="text-slate-300 leading-relaxed">
                By accessing or using Fractal Market ("the Service"), you agree to be bound by these
                Terms of Service. If you do not agree to these terms, do not use the Service.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">2. Description of Service</h2>
              <p className="text-slate-300 leading-relaxed">
                Fractal Market is an experimental software tool that analyzes historical market data
                and displays technical analysis visualizations. The Service is provided for educational,
                research, and entertainment purposes only.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">3. No Warranties</h2>
              <p className="text-slate-300 leading-relaxed uppercase font-mono text-sm">
                THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND,
                EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF
                MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT. WE DO NOT
                WARRANT THAT THE SERVICE WILL BE UNINTERRUPTED, ERROR-FREE, OR FREE OF VIRUSES OR
                OTHER HARMFUL COMPONENTS.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">4. Limitation of Liability</h2>
              <p className="text-slate-300 leading-relaxed uppercase font-mono text-sm">
                TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL FRACTAL MARKET,
                ITS OPERATORS, AFFILIATES, DIRECTORS, EMPLOYEES, OR AGENTS BE LIABLE FOR ANY INDIRECT,
                INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING WITHOUT LIMITATION,
                LOSS OF PROFITS, DATA, USE, GOODWILL, OR OTHER INTANGIBLE LOSSES, RESULTING FROM:
                (I) YOUR ACCESS TO OR USE OF OR INABILITY TO ACCESS OR USE THE SERVICE;
                (II) ANY CONDUCT OR CONTENT OF ANY THIRD PARTY ON THE SERVICE;
                (III) ANY CONTENT OBTAINED FROM THE SERVICE;
                (IV) UNAUTHORIZED ACCESS, USE, OR ALTERATION OF YOUR TRANSMISSIONS OR CONTENT;
                (V) ANY TRADING OR INVESTMENT DECISIONS YOU MAKE.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">5. Assumption of Risk</h2>
              <p className="text-slate-300 leading-relaxed">
                You expressly acknowledge and agree that your use of the Service is at your sole risk.
                Trading and investing in financial markets involves substantial risk of loss and is not
                suitable for all investors. You are solely responsible for any and all trading and
                investment decisions you make. We are not responsible for any losses you may incur.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">6. Indemnification</h2>
              <p className="text-slate-300 leading-relaxed">
                You agree to defend, indemnify, and hold harmless Fractal Market, its operators,
                affiliates, licensors, and service providers, and its and their respective officers,
                directors, employees, contractors, agents, licensors, suppliers, successors, and
                assigns from and against any claims, liabilities, damages, judgments, awards, losses,
                costs, expenses, or fees (including reasonable attorneys' fees) arising out of or
                relating to your violation of these Terms of Service or your use of the Service.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">7. No Professional Advice</h2>
              <p className="text-slate-300 leading-relaxed">
                The information provided by the Service is not intended to be a substitute for
                professional financial advice. Always seek the advice of a qualified financial
                advisor with any questions you may have regarding investment decisions.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">8. Accuracy of Information</h2>
              <p className="text-slate-300 leading-relaxed">
                While we strive to provide accurate data and analysis, we make no representations
                or warranties about the accuracy, reliability, completeness, or timeliness of any
                information provided by the Service. Market data may be delayed, inaccurate, or
                incomplete. Any reliance you place on such information is strictly at your own risk.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">9. Modifications to Service</h2>
              <p className="text-slate-300 leading-relaxed">
                We reserve the right to modify, suspend, or discontinue the Service at any time
                without notice. We shall not be liable to you or any third party for any modification,
                suspension, or discontinuance of the Service.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">10. Governing Law</h2>
              <p className="text-slate-300 leading-relaxed">
                These Terms shall be governed by and construed in accordance with the laws of the
                State of California, United States, without regard to its conflict of law provisions.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">11. Severability</h2>
              <p className="text-slate-300 leading-relaxed">
                If any provision of these Terms is held to be unenforceable or invalid, such provision
                will be changed and interpreted to accomplish the objectives of such provision to the
                greatest extent possible under applicable law, and the remaining provisions will
                continue in full force and effect.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">12. Entire Agreement</h2>
              <p className="text-slate-300 leading-relaxed">
                These Terms constitute the entire agreement between you and Fractal Market regarding
                the use of the Service, superseding any prior agreements between you and Fractal
                Market relating to your use of the Service.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">13. Contact</h2>
              <p className="text-slate-300 leading-relaxed">
                For questions about these Terms, contact us via{' '}
                <a
                  href="https://x.com/rajeshgoli"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-cyan-400 hover:text-cyan-300"
                >
                  Twitter/X
                </a>.
              </p>
            </section>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
};
