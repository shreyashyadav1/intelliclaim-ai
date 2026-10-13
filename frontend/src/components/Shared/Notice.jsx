import { AlertCircle, CheckCircle, Info, X } from 'lucide-react';
import './Shared.css';

const ICONS = { success: CheckCircle, error: AlertCircle, info: Info };

/** Inline, dismissible feedback banner for the result of a user action. */
export default function Notice({ tone = 'info', children, onDismiss }) {
  const Icon = ICONS[tone] ?? Info;
  return (
    <div className={`notice notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon size={16} aria-hidden="true" />
      <div className="notice-message">{children}</div>
      {onDismiss && (
        <button type="button" className="notice-dismiss" onClick={onDismiss} aria-label="Dismiss message">
          <X size={14} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
