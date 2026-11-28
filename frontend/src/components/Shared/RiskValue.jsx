import { formatScore, riskColor, riskLevel } from '../../utils/format';
import './Shared.css';

const LEVEL_WORDS = { high: 'High', medium: 'Medium', low: 'Low' };

/** A claim's risk score in its band colour, with the band named beside it. */
export default function RiskValue({ score }) {
  return (
    <span className="risk-value">
      <span className="risk-value-score" style={{ color: riskColor(score) }}>{formatScore(score)}</span>
      <span className="risk-value-band">{LEVEL_WORDS[riskLevel(score)]}</span>
    </span>
  );
}
