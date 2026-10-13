import { AlertTriangle, CheckCircle, ClipboardList, FileText } from 'lucide-react';
import { useCountUp } from '../../hooks/useCountUp';
import { getErrorMessage } from '../../services/api';
import { ErrorState } from '../Shared/StateMessage';
import './StatsCards.css';

const CARDS = [
  { key: 'total', label: 'Total Claims', icon: ClipboardList },
  { key: 'approved', label: 'Approval Rate', icon: CheckCircle, suffix: '%', decimals: 1 },
  { key: 'documents', label: 'Documents Processed', icon: FileText },
  { key: 'risk', label: 'Risk Alerts', icon: AlertTriangle, danger: true },
];

function statsFromOverview(overview) {
  const byStatus = overview.claims_by_status ?? {};
  return {
    total: { value: overview.total_claims ?? 0, note: `${byStatus.pending ?? 0} pending` },
    approved: { value: overview.approval_rate ?? 0, note: `${byStatus.approved ?? 0} approved` },
    documents: { value: overview.documents_processed ?? 0 },
    risk: { value: overview.high_risk_count ?? 0, note: 'risk ≥ 60' },
  };
}

function AnimatedNumber({ value, decimals = 0, suffix = '' }) {
  const current = useCountUp(value);
  const text = current.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return <span>{text}{suffix}</span>;
}

export default function StatsCards({ data, error, onRetry }) {
  if (error) {
    return (
      <div className="stats-cards">
        <div className="stats-cards-error glass-card">
          <ErrorState title="Couldn't load claim statistics" message={getErrorMessage(error)} onRetry={onRetry} />
        </div>
      </div>
    );
  }

  const stats = data ? statsFromOverview(data) : null;

  return (
    <div className="stats-cards stagger-children" aria-busy={!stats}>
      {CARDS.map(({ key, label, icon: Icon, suffix, decimals, danger }) => {
        const stat = stats?.[key];
        return (
          <div
            key={key}
            className={`stat-card glass-card ${danger ? 'stat-card--danger' : ''}`}
            id={`stat-${key}`}
            role="group"
            aria-label={label}
          >
            <div className="stat-card-header">
              <div className={`stat-card-icon ${danger ? 'stat-card-icon--danger' : ''}`}>
                <Icon size={20} />
              </div>
              {stat?.note && <span className="stat-card-note">{stat.note}</span>}
            </div>
            <div className="stat-card-value">
              {stat ? <AnimatedNumber value={stat.value} decimals={decimals} suffix={suffix} /> : '—'}
            </div>
            <div className="stat-card-label">{label}</div>
          </div>
        );
      })}
    </div>
  );
}
