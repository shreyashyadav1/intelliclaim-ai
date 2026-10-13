import { AlertTriangle } from 'lucide-react';
import { formatScore, riskColor, riskLevel } from '../../utils/format';
import Badge from '../Shared/Badge';
import MockBadge from '../Shared/MockBadge';

const LEVEL_LABELS = { high: 'High risk', medium: 'Medium risk', low: 'Low risk' };

/** Result of POST /validate/{claim_id}: composite score, flags and the AI reviewer's summary. */
export default function ValidationSummary({ result }) {
  const level = result.risk_level ?? riskLevel(result.risk_score);
  const color = riskColor(result.risk_score);
  const flags = result.flags ?? [];
  const summary = result.ai_review?.ai_summary;

  return (
    <div className="validation-summary" id="validation-summary">
      <div className="validation-summary-header">
        <span className="validation-summary-title">Latest validation</span>
        <span className="validation-level-pill" style={{ color, background: `${color}15` }}>
          {LEVEL_LABELS[level] ?? level} · {formatScore(result.risk_score)}
        </span>
        {result.is_duplicate && <Badge variant="danger">Possible duplicate</Badge>}
        <MockBadge source={result.source} />
      </div>

      {summary && <p className="validation-summary-text">{summary}</p>}

      {flags.length > 0 ? (
        <div className="risk-flags-list">
          {flags.map((flag, index) => (
            <div key={index} className="risk-flag-item">
              <AlertTriangle size={14} style={{ color }} />
              <span className="risk-flag-text">{flag.description}</span>
              {flag.severity && (
                <span className={`severity-chip severity-chip--${flag.severity}`}>{flag.severity}</span>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="risk-assessment-empty">No risk flags were raised.</p>
      )}
    </div>
  );
}
