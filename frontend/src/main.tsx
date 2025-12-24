import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Suppress lightweight-charts "Object is disposed" errors that occur during React re-renders
// These errors happen in animation frames when charts are recreated, but don't affect functionality
window.addEventListener('error', (event) => {
  if (event.message?.includes('Object is disposed')) {
    event.preventDefault();
    console.warn('Chart disposal race condition (harmless):', event.message);
  }
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
