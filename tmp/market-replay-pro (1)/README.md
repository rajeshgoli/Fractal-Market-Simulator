# Market Replay Pro - Integration Guide

This folder contains the UI components and logic for the Market Replay Pro interface. To integrate this into your existing application, follow the steps below.

## 1. Dependencies

Ensure your project has the following dependencies installed. This design uses **Tailwind CSS** for styling, **Lightweight Charts** for data visualization, and **Lucide React** for icons.

```bash
npm install lightweight-charts lucide-react clsx tailwind-merge
```

*Note: The project uses React 18+. If you are using an older version, ensure compatibility hooks are used.*

## 2. Tailwind Configuration

To match the visual design exactly, update your `tailwind.config.js` to include the specific color palette and font families used in this view.

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        app: {
          bg: '#1a1a2e',      // Main background
          secondary: '#16213e', // Panel background
          card: '#0f3460',    // Card/Input background
          text: '#eaeaea',    // Primary text
          muted: '#a0a0a0',   // Secondary text
          border: '#333333',  // Borders
        },
        trading: {
          bull: '#26a69a',    // Green/Bullish
          bear: '#ef5350',    // Red/Bearish
          blue: '#2196f3',    // Primary Action
          purple: '#9c27b0',  // Swing/Algo
          orange: '#ff9800',  // Warning/Linger
        }
      },
      fontFamily: {
        mono: ['"SF Mono"', 'Monaco', '"Cascadia Code"', 'monospace'],
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
      }
    }
  }
}
```

## 3. Global Styles (CSS)

Add the following to your global CSS file or root component to ensure the dark theme and scrollbars look correct.

```css
body {
  background-color: #1a1a2e;
  color: #eaeaea;
}

/* Custom Scrollbar */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
::-webkit-scrollbar-track {
  background: #16213e; 
}
::-webkit-scrollbar-thumb {
  background: #0f3460; 
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: #2196f3; 
}
```

## 4. Fonts

The design relies on system fonts for performance. No external font imports (like Google Fonts) are required unless you want to override the `sans` stack.

## 5. Component Usage

The main entry point is `App.tsx`, which orchestrates the following sub-components:

1.  **`ChartArea.tsx`**: Handles the `lightweight-charts` instances. Ensure the parent container has a defined height (e.g., `flex-1` in a flex column).
2.  **`ExplanationPanel.tsx`**: Renders the algorithmic swing details. It requires a `SwingData` object.
3.  **`PlaybackControls.tsx`**: Handles the timeline interactions and the "Linger" timer visualization.

### Example: Rendering the Explanation Panel

To render the explanation panel with data (as seen in the "Swing Formed" state):

```tsx
import { ExplanationPanel } from './components/ExplanationPanel';
import { SwingScale, Direction } from './types';

// ... inside your component
<ExplanationPanel 
  swing={{
    id: 'swing-1234',
    scale: SwingScale.XL,
    direction: Direction.BULL,
    highPrice: 5862.50,
    highBar: 1234,
    highTime: 'Mar 15, 14:30',
    lowPrice: 5750.00,
    lowBar: 1200,
    lowTime: 'Mar 14, 09:15',
    size: 112.50,
    sizePct: 1.92,
    ratio: 0.42,
    previousSwingId: 'abc-prev-99',
  }} 
/>
```
