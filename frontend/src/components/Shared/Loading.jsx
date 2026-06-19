import './Shared.css';

export function Spinner({ size = 36 }) {
  return (
    <div className="loading-spinner-container">
      <div className="loading-spinner" style={{ width: size, height: size }} />
    </div>
  );
}

export function LoadingDots() {
  return (
    <div className="loading-dots">
      <span className="loading-dot" />
      <span className="loading-dot" />
      <span className="loading-dot" />
    </div>
  );
}

export function Skeleton({ lines = 3, className = '' }) {
  return (
    <div className={className}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={`skeleton-line ${i === 0 ? 'h-lg' : ''} ${i === lines - 1 ? 'w-50' : i % 2 === 0 ? 'w-75' : ''}`}
        />
      ))}
    </div>
  );
}

export default function Loading({ type = 'spinner', ...props }) {
  switch (type) {
    case 'dots':
      return <LoadingDots />;
    case 'skeleton':
      return <Skeleton {...props} />;
    default:
      return <Spinner {...props} />;
  }
}
