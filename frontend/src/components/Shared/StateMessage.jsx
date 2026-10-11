import { AlertCircle, RefreshCw } from 'lucide-react';
import './Shared.css';

/** Placeholder lines while a section loads; the label is announced to screen readers. */
export function LoadingState({ label = 'Loading…' }) {
  return (
    <div className="state state--loading" role="status">
      <span className="visually-hidden">{label}</span>
      <span className="skeleton-line" aria-hidden="true" />
      <span className="skeleton-line" aria-hidden="true" />
      <span className="skeleton-line" aria-hidden="true" />
    </div>
  );
}

export function EmptyState({ icon: Icon, title, children, action }) {
  return (
    <div className="state">
      {Icon && <Icon size={20} className="state-icon" aria-hidden="true" />}
      <p className="state-title">{title}</p>
      {children && <div className="state-body">{children}</div>}
      {action && <div className="state-action">{action}</div>}
    </div>
  );
}

export function ErrorState({ title = 'Something went wrong', message, onRetry }) {
  return (
    <div className="state state--error" role="alert">
      <AlertCircle size={20} className="state-icon" aria-hidden="true" />
      <p className="state-title">{title}</p>
      {message && <p className="state-body">{message}</p>}
      {onRetry && (
        <div className="state-action">
          <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
            <RefreshCw size={14} aria-hidden="true" /> Try again
          </button>
        </div>
      )}
    </div>
  );
}
