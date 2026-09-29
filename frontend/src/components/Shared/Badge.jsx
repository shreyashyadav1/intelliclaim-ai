import './Shared.css';

const variantMap = {
  success: 'badge-success',
  warning: 'badge-warning',
  danger: 'badge-danger',
  info: 'badge-info',
  pending: 'badge-pending',
  // Claim statuses are passed straight through as the variant (see ClaimsList,
  // ClaimDetail and ValidationPage), so each one needs its own distinct colour
  // rather than falling back to the shared "badge-info" default.
  approved: 'badge-success',
  rejected: 'badge-danger',
  flagged: 'badge-info',
};

export default function Badge({
  id,
  children,
  variant = 'info',
  pulse = false,
  icon: Icon,
  className = '',
  title,
}) {
  return (
    <span
      id={id}
      title={title}
      className={`badge ${variantMap[variant] || 'badge-info'} ${pulse ? 'badge-pulse' : ''} ${className}`}
    >
      {Icon && <Icon size={11} />}
      {children}
    </span>
  );
}
