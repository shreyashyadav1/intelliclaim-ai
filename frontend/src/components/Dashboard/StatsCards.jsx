import { getErrorMessage } from '../../services/api';
import { ErrorState } from '../Shared/StateMessage';
import './StatsCards.css';

const STATUS_ROWS = [
  { key: 'pending', label: 'Pending' },
  { key: 'flagged', label: 'Flagged' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
];

const count = (value) => Number(value ?? 0).toLocaleString('en-US');
const percent = (value) => `${Number(value ?? 0).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;

function figuresFromOverview(overview) {
  const byStatus = overview.claims_by_status ?? {};
  const failed = overview.documents_failed ?? 0;
  return [
    { key: 'total', label: 'Total claims', value: count(overview.total_claims), note: `${byStatus.pending ?? 0} pending` },
    { key: 'approved', label: 'Approval rate', value: percent(overview.approval_rate), note: `${byStatus.approved ?? 0} approved` },
    {
      key: 'documents',
      label: 'Documents processed',
      value: count(overview.documents_processed),
      note: failed > 0 ? `${failed} failed` : 'none failed',
    },
    { key: 'risk', label: 'High-risk claims', value: count(overview.high_risk_count), note: 'score 60 or more' },
  ];
}

/** Headline figures for the workspace, as a plain row of labelled numbers. */
export function OverviewFigures({ data, error, onRetry }) {
  if (error) {
    return (
      <section className="overview-figures overview-figures--error" aria-label="Claim statistics">
        <ErrorState title="Couldn't load claim statistics" message={getErrorMessage(error)} onRetry={onRetry} />
      </section>
    );
  }

  const figures = data ? figuresFromOverview(data) : null;
  return (
    <section className="overview-figures" aria-label="Claim statistics" aria-busy={!figures}>
      {(figures ?? figuresFromOverview({})).map(({ key, label, value, note }) => (
        <div key={key} className="overview-figure" id={`stat-${key}`} role="group" aria-label={label}>
          <span className="overview-figure-label">{label}</span>
          <span className="overview-figure-value">{figures ? value : '—'}</span>
          <span className="overview-figure-note">{figures ? note : ' '}</span>
        </div>
      ))}
    </section>
  );
}

/** Claims by status as a bar list: each bar is that status's share of all claims. */
export function StatusBreakdown({ data }) {
  const byStatus = data?.claims_by_status ?? {};
  const total = Number(data?.total_claims ?? 0);

  return (
    <section className="status-breakdown" aria-labelledby="status-breakdown-title">
      <div className="section-head">
        <h2 id="status-breakdown-title">Claims by status</h2>
        {data && <p>{total === 1 ? '1 claim' : `${count(total)} claims`}</p>}
      </div>
      <ul className="status-bars" role="list">
        {STATUS_ROWS.map(({ key, label }) => {
          const value = Number(byStatus[key] ?? 0);
          const share = total > 0 ? value / total : 0;
          return (
            <li key={key} className="status-bar-row" data-status={key}>
              <span className="status-bar-label">{label}</span>
              <span className="status-bar-track" aria-hidden="true">
                <span className="status-bar-fill" style={{ transform: `scaleX(${share})` }} />
              </span>
              <span className="status-bar-count tabular">{data ? count(value) : '—'}</span>
              <span className="status-bar-share tabular">{data ? `${Math.round(share * 100)}%` : ''}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
