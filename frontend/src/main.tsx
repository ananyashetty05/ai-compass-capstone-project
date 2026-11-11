/**
 * Application entry point.
 *
 * Provider order matters:
 *   ToastProvider      — outermost, so any layer can report a failure
 *   AuthProvider       — owns the profile every other context reads
 *   ThemeProvider      — depends on auth (persists) and toast (reports)
 *   AccessibilityProvider — depends on auth
 *   SystemStatusProvider  — independent health probe
 *   BrowserRouter      — innermost, so contexts can read the router
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { ToastProvider } from './context/ToastProvider';
import { AuthProvider } from './context/AuthProvider';
import { ThemeProvider } from './context/ThemeProvider';
import { AccessibilityProvider } from './context/AccessibilityProvider';
import { SystemStatusProvider } from './context/SystemStatusProvider';
import './styles/index.css';

const container = document.getElementById('root');
if (!container) throw new Error('Root container #root was not found in index.html.');

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <ThemeProvider>
            <AccessibilityProvider>
              <SystemStatusProvider>
                <App />
              </SystemStatusProvider>
            </AccessibilityProvider>
          </ThemeProvider>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
);
