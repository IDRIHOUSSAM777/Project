import { Component } from 'react';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('App crash caught by ErrorBoundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: '24px' }}>
          <div style={{ maxWidth: '680px', width: '100%', border: '1px solid #e6eaf2', borderRadius: '16px', background: '#fff', padding: '20px' }}>
            <h1 style={{ marginTop: 0 }}>Une erreur est survenue</h1>
            <p style={{ color: '#5b6475' }}>
              L&apos;application a rencontré une erreur JavaScript. Ouvrez la console du navigateur
              pour voir le détail et corriger rapidement.
            </p>
            {this.state.error?.message && (
              <pre style={{ whiteSpace: 'pre-wrap', background: '#f6f8fc', padding: '12px', borderRadius: '10px', overflowX: 'auto' }}>
                {this.state.error.message}
              </pre>
            )}
          </div>
        </main>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
