import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import { I18nProvider } from './i18n.jsx'

const showFatalError = (title, details) => {
  document.body.innerHTML = `
    <main style="min-height:100vh;display:grid;place-items:center;padding:24px;background:#f6f8fc;color:#0b1220;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif">
      <section style="width:min(720px,95vw);background:#fff;border:1px solid #e6eaf2;border-radius:14px;padding:18px">
        <h1 style="margin:0 0 10px 0;font-size:22px">${title}</h1>
        <p style="margin:0 0 12px 0;color:#5b6475">Open DevTools console for full stack trace.</p>
        <pre style="margin:0;white-space:pre-wrap;background:#f6f8fc;padding:10px;border-radius:10px;overflow:auto">${details}</pre>
      </section>
    </main>
  `;
};

window.addEventListener('error', (event) => {
  showFatalError('Erreur JavaScript au démarrage', event?.error?.message || event.message || 'Unknown error');
});

window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason;
  const message = typeof reason === 'string' ? reason : reason?.message || 'Unhandled promise rejection';
  showFatalError('Promesse non gérée', message);
});

try {
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <ErrorBoundary>
        <I18nProvider>
          <App />
        </I18nProvider>
      </ErrorBoundary>
    </StrictMode>,
  );
} catch (error) {
  showFatalError('Erreur critique React', error?.message || 'Rendering failed');
}
