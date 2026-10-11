import { formatScore, getFlagThreshold, HIGH_RISK_THRESHOLD, riskLevel } from '../../utils/format';
import './RiskScale.css';

const LEVEL_NAMES = { low: 'Low', medium: 'Medium', high: 'High' };

/**
 * A 0-100 risk score on the validator's bands: low below the flag threshold
 * (reported by the API), medium from the threshold, high from 60. Without a
 * score the bands are drawn with no marker and `emptyLabel` is announced.
 */
export default function RiskScale({ score, label = 'Risk score', emptyLabel = 'Not scored yet' }) {
  const threshold = getFlagThreshold();
  const value = Number(score);
  const hasScore = score !== null && score !== undefined && score !== '' && Number.isFinite(value);
  const clamped = hasScore ? Math.min(Math.max(value, 0), 100) : null;
  const level = hasScore ? riskLevel(clamped) : null;

  const description = hasScore
    ? `${label} ${formatScore(clamped)} out of 100: ${level} risk. Medium from ${formatScore(threshold)}, high from ${HIGH_RISK_THRESHOLD}.`
    : emptyLabel;

  const bands = [
    { band: 'low', start: 0, size: threshold },
    { band: 'medium', start: threshold, size: HIGH_RISK_THRESHOLD - threshold },
    { band: 'high', start: HIGH_RISK_THRESHOLD, size: 100 - HIGH_RISK_THRESHOLD },
  ];

  return (
    <div className="risk-scale" role="img" aria-label={description}>
      <div className="risk-scale-track" aria-hidden="true">
        {bands.map(({ band, size }) => (
          <span key={band} className="risk-scale-band" data-band={band} data-current={band === level || undefined} style={{ flexGrow: size }} />
        ))}
        {hasScore && <span className="risk-scale-marker" style={{ left: `${clamped}%` }} />}
      </div>
      <div className="risk-scale-labels" aria-hidden="true">
        {bands.map(({ band, start, size }) => (
          <span key={band} className="risk-scale-label" data-current={band === level || undefined} style={{ flexGrow: size }}>
            <span className="risk-scale-tick tabular">{formatScore(start)}</span>
            {LEVEL_NAMES[band]}
          </span>
        ))}
        <span className="risk-scale-end tabular">100</span>
      </div>
    </div>
  );
}
