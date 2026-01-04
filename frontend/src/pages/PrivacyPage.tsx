import { Navbar } from './LandingPage/components/Navbar';
import { Footer } from '../components/Footer';

export const PrivacyPage: React.FC = () => {
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
          <h1 className="text-4xl font-bold text-white mb-8">Privacy Policy</h1>
          <p className="text-slate-400 text-sm mb-12">Last updated: January 3, 2026</p>

          <div className="prose prose-invert prose-slate max-w-none space-y-8">
            <section>
              <h2 className="text-xl font-bold text-white mb-4">1. Information We Collect</h2>
              <p className="text-slate-300 leading-relaxed">
                We collect information you provide directly, including email address and authentication
                credentials when you create an account. We also collect usage data, including interactions
                with the application, chart configurations, and observations you save.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">2. How We Use Your Information</h2>
              <p className="text-slate-300 leading-relaxed">
                We use your information solely to provide and improve the service. We do not sell, rent,
                or share your personal information with third parties for marketing purposes. Your saved
                observations and configurations are stored to provide you with a persistent experience.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">3. Data Storage and Security</h2>
              <p className="text-slate-300 leading-relaxed">
                Your data is stored on secure servers. We implement industry-standard security measures
                to protect your information. However, no method of transmission over the Internet is
                100% secure, and we cannot guarantee absolute security.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">4. Third-Party Services</h2>
              <p className="text-slate-300 leading-relaxed">
                We use third-party authentication providers (Google, GitHub) for account creation.
                These services have their own privacy policies. We also use analytics to understand
                how the service is used.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">5. Your Rights</h2>
              <p className="text-slate-300 leading-relaxed">
                You may request deletion of your account and associated data at any time by contacting
                us. Upon deletion, your data will be permanently removed from our systems.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">6. Changes to This Policy</h2>
              <p className="text-slate-300 leading-relaxed">
                We may update this privacy policy from time to time. We will notify you of any changes
                by posting the new policy on this page and updating the "Last updated" date.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-4">7. Contact</h2>
              <p className="text-slate-300 leading-relaxed">
                For questions about this privacy policy, contact us via{' '}
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
