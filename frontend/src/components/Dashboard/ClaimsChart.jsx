import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { BarChart3 } from 'lucide-react';
import { getErrorMessage } from '../../services/api';
import { formatDate } from '../../utils/format';
import { EmptyState, ErrorState, LoadingState } from '../Shared/StateMessage';
import './ClaimsChart.css';

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="chart-tooltip">
        <p className="chart-tooltip-label">{label}</p>
        <p className="chart-tooltip-value">{payload[0].value} claims</p>
      </div>
    );
  }
  return null;
};

function TrendChart({ points }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={points} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
        <defs>
          <linearGradient id="claimsGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis
          dataKey="date"
          tick={{ fill: '#64748b', fontSize: 11 }}
          axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
          tickLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: '#64748b', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <Tooltip content={<CustomTooltip />} />
        <Area
          type="monotone"
          dataKey="count"
          stroke="#6366f1"
          strokeWidth={2.5}
          fill="url(#claimsGradient)"
          animationDuration={1500}
          dot={false}
          activeDot={{ r: 5, fill: '#6366f1', stroke: '#fff', strokeWidth: 2 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export default function ClaimsChart({ data, error, onRetry, days }) {
  const points = Array.isArray(data)
    ? data.map((day) => ({
        date: formatDate(day.date, { month: 'short', day: 'numeric' }),
        count: day.count ?? 0,
      }))
    : [];

  let body;
  if (error) {
    body = <ErrorState title="Couldn't load the claims trend" message={getErrorMessage(error)} onRetry={onRetry} />;
  } else if (!data) {
    body = <LoadingState label="Loading claims trend…" />;
  } else if (!points.some((point) => point.count > 0)) {
    body = (
      <EmptyState icon={BarChart3} title={`No claims in the last ${days} days`}>
        Claims appear here once documents are extracted.
      </EmptyState>
    );
  } else {
    body = <TrendChart points={points} />;
  }

  return (
    <div className="claims-chart glass-card" id="claims-trend-chart">
      <div className="claims-chart-header">
        <h3 className="claims-chart-title">Claims Processed</h3>
        <span className="claims-chart-period">Last {days} days</span>
      </div>
      <div className="claims-chart-body">{body}</div>
    </div>
  );
}
