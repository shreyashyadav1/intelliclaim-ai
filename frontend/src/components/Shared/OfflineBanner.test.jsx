import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi } from '../../test/mockApi';
import { HEALTH_CHECK_INTERVAL } from '../../hooks/useApiHealth';
import OfflineBanner from './OfflineBanner';

const MESSAGE = /server is offline right now/;

describe('OfflineBanner', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing while the API reports healthy', async () => {
    mockApi({ 'GET /health': { data: { status: 'ok' } } });
    render(<OfflineBanner />);

    // Give the initial check a turn to resolve before asserting the negative.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText(MESSAGE)).not.toBeInTheDocument();
  });

  it('shows the banner when the health check is a network error', async () => {
    mockApi({}); // no route registered -> the shared mock throws a network error
    render(<OfflineBanner />);

    expect(await screen.findByText(MESSAGE)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'GitHub' })).toHaveAttribute(
      'href',
      'https://github.com/shreyashyadav1/intelliclaim-ai',
    );
  });

  it('shows the banner on a 503 (the backend reports the database as down)', async () => {
    mockApi({ 'GET /health': { status: 503, data: { status: 'error', database: 'down' } } });
    render(<OfflineBanner />);

    expect(await screen.findByText(MESSAGE)).toBeInTheDocument();
  });

  it('hides the banner again once a later check recovers', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let healthy = false;
    mockApi({
      'GET /health': () => (healthy ? { data: { status: 'ok' } } : { status: 503, data: {} }),
    });
    render(<OfflineBanner />);

    expect(await screen.findByText(MESSAGE)).toBeInTheDocument();

    healthy = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(HEALTH_CHECK_INTERVAL);
    });

    expect(screen.queryByText(MESSAGE)).not.toBeInTheDocument();
  });

  it('can be dismissed', async () => {
    mockApi({ 'GET /health': { status: 503, data: {} } });
    const user = userEvent.setup();
    render(<OfflineBanner />);

    expect(await screen.findByText(MESSAGE)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /dismiss/i }));

    expect(screen.queryByText(MESSAGE)).not.toBeInTheDocument();
  });
});
