import './Shared.css';

export default function Card({
  id,
  title,
  subtitle,
  children,
  footer,
  hoverable = false,
  className = '',
  headerAction,
  noPadding = false,
}) {
  return (
    <article
      id={id}
      className={`card ${hoverable ? 'card-hoverable' : ''} ${className}`}
    >
      {(title || subtitle || headerAction) && (
        <header className="card-header">
          <div>
            {title && <h3 className="card-title">{title}</h3>}
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          {headerAction && <div>{headerAction}</div>}
        </header>
      )}
      <div className={noPadding ? '' : 'card-body'}>{children}</div>
      {footer && <footer className="card-footer">{footer}</footer>}
    </article>
  );
}
