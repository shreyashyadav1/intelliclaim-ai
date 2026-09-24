import { AlertCircle, RefreshCw } from 'lucide-react';
import './Shared.css';

export function LoadingState({ label = 'Loading…' }) {
  return (
    <div className="state-message" role="status">
      <span className="loading-spinner" aria-hidden="true" />
      <p className="state-message-body">{label}</p>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, children }) {
  return (
    <div className="state-message">
      {Icon && <Icon size={28} className="state-message-icon" aria-hidden="true" />}
      <p className="state-message-title">{title}</p>
      {children && <div className="state-message-body">{children}</div>}
    </div>
  );
}

export function ErrorState({ title = 'Something went wrong', message, onRetry }) {
  return (
    <div className="state-message state-message--error" role="alert">
      <AlertCircle size={28} className="state-message-icon" aria-hidden="true" />
      <p className="state-message-title">{title}</p>
      {message && <p className="state-message-body">{message}</p>}
      {onRetry && (
        <button type="button" className="state-message-retry" onClick={onRetry}>
          <RefreshCw size={14} aria-hidden="true" /> Try again
        </button>
      )}
    </div>
  );
}
