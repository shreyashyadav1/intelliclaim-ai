import './Shared.css';

const variantMap = {
  info: 'badge-info',
  success: 'badge-success',
  warning: 'badge-warning',
  danger: 'badge-danger',
  pending: 'badge-pending',
  mock: 'badge-mock',
  // Claim statuses are passed straight through as the variant (see StatusBadge),
  // so each one needs its own distinct style rather than the shared default.
  approved: 'badge-success',
  rejected: 'badge-danger',
  flagged: 'badge-warning',
};

export default function Badge({ id, children, variant = 'info', icon: Icon, className = '', title }) {
  return (
    <span id={id} title={title} className={`badge ${variantMap[variant] || 'badge-info'} ${className}`.trim()}>
      {Icon && <Icon size={12} aria-hidden="true" />}
      {children}
    </span>
  );
}

/** A claim's status (pending, approved, rejected or flagged), shown in sentence case. */
export function StatusBadge({ status }) {
  return (
    <Badge variant={status} className="badge--status">
      {status || 'unknown'}
    </Badge>
  );
}
