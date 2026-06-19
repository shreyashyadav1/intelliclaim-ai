import { useState, useEffect } from 'react';
import StatsCards from '../components/Dashboard/StatsCards';
import ClaimsChart from '../components/Dashboard/ClaimsChart';
import RiskGauge from '../components/Dashboard/RiskGauge';
import RecentClaims from '../components/Dashboard/RecentClaims';
import { analyticsApi } from '../services/api';

export default function DashboardPage() {
  const [overview, setOverview] = useState(null);
  const [trend, setTrend] = useState(null);
  const [recentClaims, setRecentClaims] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [ov, tr, rc] = await Promise.allSettled([
          analyticsApi.getOverview(),
          analyticsApi.getClaimsTrend(30),
          analyticsApi.getRecentClaims(10),
        ]);
        if (ov.status === 'fulfilled') setOverview(ov.value);
        if (tr.status === 'fulfilled') setTrend(tr.value);
        if (rc.status === 'fulfilled') setRecentClaims(rc.value);
      } catch {
        // Demo data will be used by components
      }
    };
    fetchData();
  }, []);

  return (
    <div className="page-enter" id="dashboard-page">
      <StatsCards data={overview} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 20, marginBottom: 20 }}>
        <ClaimsChart data={trend} />
        <RiskGauge score={overview?.avg_risk_score || 32.4} />
      </div>
      <RecentClaims data={recentClaims} />
    </div>
  );
}
