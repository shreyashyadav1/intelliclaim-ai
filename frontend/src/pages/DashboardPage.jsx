import ClaimsChart from '../components/Dashboard/ClaimsChart';
import RecentClaims from '../components/Dashboard/RecentClaims';
import RiskOverview from '../components/Dashboard/RiskOverview';
import { OverviewFigures, StatusBreakdown } from '../components/Dashboard/StatsCards';
import PageHeader from '../components/Shared/PageHeader';
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
    <div id="dashboard-page">
      <PageHeader title="Dashboard" description="Claim volume, decisions and risk across the workspace." />
      <OverviewFigures data={overview.data} error={overview.error} onRetry={overview.refetch} />
      <div className="dashboard-grid">
        {!overview.error && <StatusBreakdown data={overview.data} />}
        <RiskOverview data={overview.data} error={overview.error} onRetry={overview.refetch} />
      </div>
      <ClaimsChart data={trend.data} error={trend.error} onRetry={trend.refetch} days={TREND_DAYS} />
      <RecentClaims data={recentClaims.data} error={recentClaims.error} onRetry={recentClaims.refetch} />
    </div>
  );
}
