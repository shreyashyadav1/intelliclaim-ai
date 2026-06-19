import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, FileText, CheckCircle, Clock, AlertTriangle } from 'lucide-react';
import './StatsCards.css';

const iconMap = {
  total: FileText,
  approved: CheckCircle,
  time: Clock,
  risk: AlertTriangle,
};

const defaultStats = [
  { key: 'total', label: 'Total Claims', value: 1247, trend: 12.5, prefix: '', suffix: '' },
  { key: 'approved', label: 'Approval Rate', value: 74.9, trend: 3.2, prefix: '', suffix: '%' },
  { key: 'time', label: 'Avg. Processing', value: 4.2, trend: -8.1, prefix: '', suffix: 'hrs' },
  { key: 'risk', label: 'Risk Alerts', value: 68, trend: 15.3, prefix: '', suffix: '', danger: true },
];

function AnimatedCounter({ target, suffix = '', prefix = '', duration = 1500 }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let start = 0;
    const end = target;
    const isFloat = !Number.isInteger(target);
    const stepTime = Math.max(duration / (end || 1), 10);
    const increment = end / (duration / 16);
    let current = 0;
    const timer = setInterval(() => {
      current += increment;
      if (current >= end) {
        setCount(end);
        clearInterval(timer);
      } else {
        setCount(isFloat ? Math.round(current * 10) / 10 : Math.floor(current));
      }
    }, 16);
    return () => clearInterval(timer);
  }, [target, duration]);

  return <span>{prefix}{typeof count === 'number' && !Number.isInteger(target) ? count.toFixed(1) : count.toLocaleString()}{suffix}</span>;
}

export default function StatsCards({ data }) {
  const stats = data ? [
    { key: 'total', label: 'Total Claims', value: data.total_claims || 0, trend: 12.5, prefix: '', suffix: '' },
    { key: 'approved', label: 'Approval Rate', value: data.approval_rate || 0, trend: 3.2, prefix: '', suffix: '%' },
    { key: 'time', label: 'Avg. Processing', value: 4.2, trend: -8.1, prefix: '', suffix: 'hrs' },
    { key: 'risk', label: 'Risk Alerts', value: data.high_risk_count || 0, trend: 15.3, prefix: '', suffix: '', danger: true },
  ] : defaultStats;

  return (
    <div className="stats-cards stagger-children">
      {stats.map((stat) => {
        const Icon = iconMap[stat.key];
        const isPositive = stat.trend > 0;
        return (
          <div key={stat.key} className={`stat-card glass-card ${stat.danger ? 'stat-card--danger' : ''}`} id={`stat-${stat.key}`}>
            <div className="stat-card-header">
              <div className={`stat-card-icon ${stat.danger ? 'stat-card-icon--danger' : ''}`}>
                <Icon size={20} />
              </div>
              <div className={`stat-card-trend ${isPositive ? 'trend-up' : 'trend-down'}`}>
                {isPositive ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                <span>{Math.abs(stat.trend)}%</span>
              </div>
            </div>
            <div className="stat-card-value">
              <AnimatedCounter target={stat.value} prefix={stat.prefix} suffix={stat.suffix} />
            </div>
            <div className="stat-card-label">{stat.label}</div>
          </div>
        );
      })}
    </div>
  );
}
