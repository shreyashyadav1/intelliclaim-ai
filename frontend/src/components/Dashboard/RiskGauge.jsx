import { useCountUp } from '../../hooks/useCountUp';
import { getErrorMessage } from '../../services/api';
import { riskColor, riskLevel } from '../../utils/format';
import { ErrorState, LoadingState } from '../Shared/StateMessage';
import './RiskGauge.css';

const RADIUS = 80;
const STROKE_WIDTH = 12;
const CX = 100;
const CY = 100;
const LEVEL_LABELS = { high: 'High Risk', medium: 'Medium Risk', low: 'Low Risk' };

function polarToCartesian(angleDeg, radius = RADIUS) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: CX + radius * Math.cos(rad), y: CY - radius * Math.sin(rad) };
}

// The gauge is a half circle drawn clockwise from 180° (left) towards 0° (right).
function arcPath(startAngle, endAngle) {
  const start = polarToCartesian(startAngle);
  const end = polarToCartesian(endAngle);
  return `M ${start.x} ${start.y} A ${RADIUS} ${RADIUS} 0 0 1 ${end.x} ${end.y}`;
}

export default function RiskGauge({ data, error, onRetry }) {
  const hasClaims = (data?.total_claims ?? 0) > 0;
  const score = hasClaims ? Math.min(Math.max(Number(data.avg_risk_score) || 0, 0), 100) : 0;
  const animatedScore = useCountUp(score, 1000);

  let body;
  if (error) {
    body = <ErrorState title="Couldn't load the risk score" message={getErrorMessage(error)} onRetry={onRetry} />;
  } else if (!data) {
    body = <LoadingState label="Loading risk score…" />;
  } else {
    const color = hasClaims ? riskColor(score) : 'var(--text-tertiary)';
    const needleAngle = 180 - (animatedScore / 100) * 180;
    const needleTip = polarToCartesian(needleAngle, RADIUS - 20);

    body = (
      <>
        <div className="risk-gauge-svg-wrapper">
          <svg
            viewBox="0 0 200 120"
            className="risk-gauge-svg"
            role="img"
            aria-label={hasClaims ? `Average risk score ${score.toFixed(1)} out of 100` : 'No claims to score yet'}
          >
            <defs>
              <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#10b981" />
                <stop offset="50%" stopColor="#f59e0b" />
                <stop offset="100%" stopColor="#ef4444" />
              </linearGradient>
            </defs>
            <path d={arcPath(180, 0)} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={STROKE_WIDTH} strokeLinecap="round" />
            {hasClaims && (
              <path
                d={arcPath(180, Math.max(needleAngle, 0.1))}
                fill="none"
                stroke="url(#gaugeGrad)"
                strokeWidth={STROKE_WIDTH}
                strokeLinecap="round"
              />
            )}
            <line x1={CX} y1={CY} x2={needleTip.x} y2={needleTip.y} stroke={color} strokeWidth="2.5" strokeLinecap="round" />
            <circle cx={CX} cy={CY} r="5" fill={color} />
            <circle cx={CX} cy={CY} r="2.5" fill="var(--bg-primary)" />
          </svg>
        </div>
        <div className="risk-gauge-value" style={{ color }}>
          {hasClaims ? animatedScore.toFixed(1) : '—'}
        </div>
        <div className="risk-gauge-level" style={{ color }}>
          {hasClaims ? LEVEL_LABELS[riskLevel(score)] : 'No claims yet'}
        </div>
      </>
    );
  }

  return (
    <div className="risk-gauge glass-card" id="risk-gauge">
      <h3 className="risk-gauge-title">Overall Risk Score</h3>
      {body}
    </div>
  );
}
