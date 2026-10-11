import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { BarChart3 } from 'lucide-react';
import { getErrorMessage } from '../../services/api';
import { formatDate } from '../../utils/format';
import { EmptyState, ErrorState, LoadingState } from '../Shared/StateMessage';
import './ClaimsChart.css';

const AXIS_TICK = { fill: '#545b68', fontSize: 12 };

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip-value">{point.count === 1 ? '1 claim' : `${point.count} claims`}</p>
      <p className="chart-tooltip-label">{point.label}</p>
    </div>
  );
}

function TrendChart({ points, days }) {
  return (
    <>
      <div className="claims-chart-plot">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart
            data={points}
            margin={{ top: 8, right: 0, left: 0, bottom: 0 }}
            barCategoryGap="22%"
            title={`Claims received per day over the last ${days} days`}
          >
            <CartesianGrid vertical={false} stroke="#cdd1d8" />
            <XAxis
              dataKey="tick"
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={{ stroke: '#7a818d' }}
              interval="preserveStartEnd"
              minTickGap={24}
            />
            <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} allowDecimals={false} width={32} />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: '#e6eaf0' }} isAnimationActive={false} />
            <Bar dataKey="count" className="claims-chart-bar" maxBarSize={20} radius={[3, 3, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="visually-hidden">
        <caption>Claims received per day</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Claims</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.date}>
              <td>{point.label}</td>
              <td>{point.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export default function ClaimsChart({ data, error, onRetry, days }) {
  const points = Array.isArray(data)
    ? data.map((day) => ({
        date: day.date,
        tick: formatDate(day.date, { month: 'short', day: 'numeric' }),
        label: formatDate(day.date, { weekday: 'short', month: 'short', day: 'numeric' }),
        count: day.count ?? 0,
      }))
    : [];
  const total = points.reduce((sum, point) => sum + point.count, 0);

  let body;
  if (error) {
    body = <ErrorState title="Couldn't load the claims trend" message={getErrorMessage(error)} onRetry={onRetry} />;
  } else if (!data) {
    body = <LoadingState label="Loading claims trend…" />;
  } else if (total === 0) {
    body = (
      <EmptyState icon={BarChart3} title={`No claims in the last ${days} days`}>
        Claims appear here once documents are extracted.
      </EmptyState>
    );
  } else {
    body = <TrendChart points={points} days={days} />;
  }

  return (
    <section className="claims-chart" id="claims-trend-chart" aria-labelledby="claims-chart-title">
      <div className="section-head">
        <h2 id="claims-chart-title">Claims received per day</h2>
        <p>
          {data && total > 0
            ? `${total.toLocaleString('en-US')} in the last ${days} days`
            : `Last ${days} days`}
        </p>
      </div>
      {body}
    </section>
  );
}
