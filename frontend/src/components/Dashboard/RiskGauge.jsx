import { useEffect, useState } from 'react';
import './RiskGauge.css';

export default function RiskGauge({ score = 32.4 }) {
  const [animatedScore, setAnimatedScore] = useState(0);

  useEffect(() => {
    let current = 0;
    const step = score / 60;
    const timer = setInterval(() => {
      current += step;
      if (current >= score) {
        setAnimatedScore(score);
        clearInterval(timer);
      } else {
        setAnimatedScore(Math.round(current * 10) / 10);
      }
    }, 16);
    return () => clearInterval(timer);
  }, [score]);

  const getColor = (s) => {
    if (s >= 60) return '#ef4444';
    if (s >= 30) return '#f59e0b';
    return '#10b981';
  };

  const getLevel = (s) => {
    if (s >= 60) return 'High Risk';
    if (s >= 30) return 'Medium Risk';
    return 'Low Risk';
  };

  // SVG arc calculation
  const radius = 80;
  const strokeWidth = 12;
  const cx = 100;
  const cy = 100;
  const startAngle = 180;
  const endAngle = 0;
  const totalAngle = 180;
  const progressAngle = (animatedScore / 100) * totalAngle;

  const polarToCartesian = (cx, cy, r, angleDeg) => {
    const rad = (angleDeg * Math.PI) / 180;
    return {
      x: cx + r * Math.cos(rad),
      y: cy - r * Math.sin(rad),
    };
  };

  const arcPath = (cx, cy, r, startAngle, endAngle) => {
    const start = polarToCartesian(cx, cy, r, startAngle);
    const end = polarToCartesian(cx, cy, r, endAngle);
    const largeArcFlag = startAngle - endAngle > 180 ? 1 : 0;
    return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} 1 ${end.x} ${end.y}`;
  };

  const bgPath = arcPath(cx, cy, radius, 180, 0);
  const progressEnd = 180 - progressAngle;
  const fgPath = arcPath(cx, cy, radius, 180, Math.max(progressEnd, 0.1));

  const needleAngle = 180 - progressAngle;
  const needleTip = polarToCartesian(cx, cy, radius - 20, needleAngle);

  return (
    <div className="risk-gauge glass-card" id="risk-gauge">
      <h3 className="risk-gauge-title">Overall Risk Score</h3>
      <div className="risk-gauge-svg-wrapper">
        <svg viewBox="0 0 200 120" className="risk-gauge-svg">
          <defs>
            <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#10b981" />
              <stop offset="50%" stopColor="#f59e0b" />
              <stop offset="100%" stopColor="#ef4444" />
            </linearGradient>
          </defs>
          {/* Background arc */}
          <path d={bgPath} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={strokeWidth} strokeLinecap="round" />
          {/* Progress arc */}
          <path d={fgPath} fill="none" stroke="url(#gaugeGrad)" strokeWidth={strokeWidth} strokeLinecap="round"
            style={{ transition: 'all 1s ease-out' }} />
          {/* Needle */}
          <line x1={cx} y1={cy} x2={needleTip.x} y2={needleTip.y}
            stroke={getColor(animatedScore)} strokeWidth="2.5" strokeLinecap="round"
            style={{ transition: 'all 1s ease-out' }} />
          <circle cx={cx} cy={cy} r="5" fill={getColor(animatedScore)} />
          <circle cx={cx} cy={cy} r="2.5" fill="var(--bg-primary)" />
        </svg>
      </div>
      <div className="risk-gauge-value" style={{ color: getColor(score) }}>
        {animatedScore.toFixed(1)}
      </div>
      <div className="risk-gauge-level" style={{ color: getColor(score) }}>
        {getLevel(score)}
      </div>
    </div>
  );
}
