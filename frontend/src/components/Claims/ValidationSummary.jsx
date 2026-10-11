import { AlertTriangle } from 'lucide-react';
import { formatScore, levelColor, riskLevel } from '../../utils/format';
import Badge from '../Shared/Badge';
import MockBadge from '../Shared/MockBadge';

const LEVEL_LABELS = { high: 'High risk', medium: 'Medium risk', low: 'Low risk' };
const SEVERITY_VARIANTS = { high: 'danger', medium: 'warning', low: 'info' };

/** Result of POST /validate/{claim_id}: composite score, flags and the AI reviewer's summary. */
export default function ValidationSummary({ result }) {
  // The API's risk_level decides both the label and the colour.
  const level = result.risk_level ?? riskLevel(result.risk_score);
  const flags = result.flags ?? [];
  const summary = result.ai_review?.ai_summary;

  return (
    <div className="validation-summary" id="validation-summary">
      <div className="validation-summary-head">
        <h3 className="validation-summary-title">Latest validation</h3>
        <span className="validation-level" style={{ color: levelColor(level) }}>
          {LEVEL_LABELS[level] ?? level}, score {formatScore(result.risk_score)}
        </span>
        {result.is_duplicate && <Badge variant="danger">Possible duplicate</Badge>}
      </div>

      {summary && (
        <div className="ai-review">
          <p className="ai-review-label">
            AI review <MockBadge source={result.ai_review?.source ?? result.source} />
          </p>
          <p className="ai-review-text">{summary}</p>
        </div>
      )}
      {!summary && <MockBadge source={result.ai_review?.source ?? result.source} />}

      {flags.length > 0 ? (
        <ul className="risk-flags" role="list">
          {flags.map((flag, index) => (
            <li key={index} className="risk-flag">
              <AlertTriangle size={14} aria-hidden="true" className="risk-flag-icon" />
              <span className="risk-flag-text">{flag.description}</span>
              {flag.severity && (
                <Badge variant={SEVERITY_VARIANTS[flag.severity] ?? 'info'} className="badge--status">
                  {flag.severity}
                </Badge>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="risk-empty">No risk flags were raised.</p>
      )}
    </div>
  );
}
