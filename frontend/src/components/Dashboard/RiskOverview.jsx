import { Link } from 'react-router-dom';
import { getErrorMessage } from '../../services/api';
import { formatScore, riskColor, riskLevel } from '../../utils/format';
import RiskScale from '../Shared/RiskScale';
import { ErrorState, LoadingState } from '../Shared/StateMessage';
import './RiskOverview.css';

const LEVEL_WORDS = { high: 'High risk', medium: 'Medium risk', low: 'Low risk' };

/** The workspace's average risk score on the validator's bands. */
export default function RiskOverview({ data, error, onRetry }) {
  const hasClaims = (data?.total_claims ?? 0) > 0;
  const score = hasClaims ? Math.min(Math.max(Number(data.avg_risk_score) || 0, 0), 100) : null;
  const highRisk = data?.high_risk_count ?? 0;

  let body;
  if (error) {
    body = <ErrorState title="Couldn't load the risk score" message={getErrorMessage(error)} onRetry={onRetry} />;
  } else if (!data) {
    body = <LoadingState label="Loading risk score…" />;
  } else {
    body = (
      <>
        <p className="risk-overview-figure">
          <span className="risk-overview-value">{hasClaims ? formatScore(score) : '—'}</span>
          <span className="risk-overview-level" style={hasClaims ? { color: riskColor(score) } : undefined}>
            {hasClaims ? LEVEL_WORDS[riskLevel(score)] : 'No claims yet'}
          </span>
        </p>
        <RiskScale score={score} label="Average risk score" emptyLabel="No claims to score yet" />
        <p className="risk-overview-note">
          {highRisk === 1 ? '1 claim scores 60 or more.' : `${highRisk.toLocaleString('en-US')} claims score 60 or more.`}{' '}
          <Link to="/validation" className="text-link">Review flagged claims</Link>
        </p>
      </>
    );
  }

  return (
    <section className="risk-overview" id="risk-gauge" aria-labelledby="risk-overview-title">
      <div className="section-head">
        <h2 id="risk-overview-title">Average risk</h2>
        <p>All claims</p>
      </div>
      {body}
    </section>
  );
}
