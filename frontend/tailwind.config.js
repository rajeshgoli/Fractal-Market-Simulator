/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        app: {
          bg: '#1a1a2e',
          secondary: '#16213e',
          card: '#0f3460',
          text: '#eaeaea',
          muted: '#a0a0a0',
          border: '#333333',
        },
        trading: {
          bull: '#26a69a',
          bear: '#ef5350',
          blue: '#2196f3',
          purple: '#9c27b0',
          orange: '#ff9800',
        }
      },
      fontFamily: {
        mono: ['"SF Mono"', 'Monaco', '"Cascadia Code"', 'monospace'],
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
      },
      animation: {
        'spin-slow': 'spin 3s linear infinite',
        'fade-in': 'fadeIn 0.3s ease-in-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        }
      }
    }
  },
  plugins: [],
}
