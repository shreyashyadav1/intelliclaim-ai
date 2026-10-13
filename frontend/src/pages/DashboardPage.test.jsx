import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mockApi } from '../test/mockApi';
import { renderWithRouter } from '../test/render';
import DashboardPage from './DashboardPage';

const emptyOverview = {
  total_claims: 0,
  documents_processed: 0,
  claims_by_status: {},
  avg_treatment_cost: 0,
  avg_risk_score: 0,
  high_risk_count: 0,
  approval_rate: 0,
};

const emptyTrend = Array.from({ length: 30 }, (_, index) => ({
  date: `2026-06-${String(index + 1).padStart(2, '0')}`,
  count: 0,
}));

describe('DashboardPage', () => {
  it('renders zeros and empty states when there is no data', async () => {
    mockApi({
      'GET /analytics/overview': { data: emptyOverview },
      'GET /analytics/claims-trend': { data: emptyTrend },
      'GET /analytics/recent-claims': { data: [] },
    });
    renderWithRouter(<DashboardPage />);

    const stat = (name) => within(screen.getByRole('group', { name }));
    expect(await stat('Total Claims').findByText('0')).toBeInTheDocument();
    expect(stat('Total Claims').getByText('0 pending')).toBeInTheDocument();
    expect(stat('Approval Rate').getByText('0.0%')).toBeInTheDocument();
    expect(stat('Documents Processed').getByText('0')).toBeInTheDocument();
    expect(stat('Risk Alerts').getByText('0')).toBeInTheDocument();

    expect(await screen.findByRole('img', { name: 'No claims to score yet' })).toBeInTheDocument();
    expect(await screen.findByText('No claims in the last 30 days')).toBeInTheDocument();
    expect(await screen.findByText(/extract it to create the first claim/)).toBeInTheDocument();

    // None of the previously hard-coded figures may appear.
    for (const placeholder of [/32\.4/, /4\.2\s*hrs/, /12\.5%/, /Avg\. Processing/, /Sarah Johnson/]) {
      expect(screen.queryByText(placeholder)).not.toBeInTheDocument();
    }
  });

  it('reports a failed section without hiding the others', async () => {
    mockApi({
      'GET /analytics/overview': { status: 500, data: { detail: 'Aggregation failed' } },
      'GET /analytics/claims-trend': { data: emptyTrend },
      'GET /analytics/recent-claims': { data: [] },
    });
    renderWithRouter(<DashboardPage />);

    expect(await screen.findByText("Couldn't load claim statistics")).toBeInTheDocument();
    expect(screen.getAllByText('Aggregation failed')).toHaveLength(2); // stats cards and risk gauge
    expect(await screen.findByText('No claims in the last 30 days')).toBeInTheDocument();
  });
});
