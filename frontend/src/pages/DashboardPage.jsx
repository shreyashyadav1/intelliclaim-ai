import StatsCards from '../components/Dashboard/StatsCards';
import ClaimsChart from '../components/Dashboard/ClaimsChart';
import RiskGauge from '../components/Dashboard/RiskGauge';
import RecentClaims from '../components/Dashboard/RecentClaims';
import { useApiQuery } from '../hooks/useApiQuery';
import { analyticsApi } from '../services/api';
import './DashboardPage.css';

const TREND_DAYS = 30;
const RECENT_CLAIMS_LIMIT = 7;

const loadOverview = () => analyticsApi.getOverview();
const loadTrend = () => analyticsApi.getClaimsTrend(TREND_DAYS);
const loadRecentClaims = () => analyticsApi.getRecentClaims(RECENT_CLAIMS_LIMIT);

export default function DashboardPage() {
  const overview = useApiQuery(loadOverview);
  const trend = useApiQuery(loadTrend);
  const recentClaims = useApiQuery(loadRecentClaims);

  return (
    <div className="page-enter" id="dashboard-page">
      <StatsCards data={overview.data} error={overview.error} onRetry={overview.refetch} />
      <div className="dashboard-chart-grid">
        <ClaimsChart data={trend.data} error={trend.error} onRetry={trend.refetch} days={TREND_DAYS} />
        <RiskGauge data={overview.data} error={overview.error} onRetry={overview.refetch} />
      </div>
      <RecentClaims data={recentClaims.data} error={recentClaims.error} onRetry={recentClaims.refetch} />
    </div>
  );
}
