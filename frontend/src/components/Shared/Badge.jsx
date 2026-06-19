import './Shared.css';

const variantMap = {
  success: 'badge-success',
  warning: 'badge-warning',
  danger: 'badge-danger',
  info: 'badge-info',
  pending: 'badge-pending',
};

export default function Badge({
  id,
  children,
  variant = 'info',
  pulse = false,
  icon: Icon,
  className = '',
}) {
  return (
    <span
      id={id}
      className={`badge ${variantMap[variant] || 'badge-info'} ${pulse ? 'badge-pulse' : ''} ${className}`}
    >
      {Icon && <Icon size={11} />}
      {children}
    </span>
  );
}
