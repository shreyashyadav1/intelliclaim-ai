import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Badge from './Badge';

// Claim statuses are passed straight through as the `variant` prop (see
// ClaimsList, ClaimDetail and ValidationPage), so each one must resolve to
// its own badge class rather than sharing one colour.
describe('Badge', () => {
  it('gives approved, rejected and flagged claim statuses distinct classes', () => {
    render(
      <>
        <Badge variant="pending">pending</Badge>
        <Badge variant="approved">approved</Badge>
        <Badge variant="rejected">rejected</Badge>
        <Badge variant="flagged">flagged</Badge>
      </>,
    );

    const classOf = (label) => screen.getByText(label).className;
    const classes = {
      pending: classOf('pending'),
      approved: classOf('approved'),
      rejected: classOf('rejected'),
      flagged: classOf('flagged'),
    };

    expect(classes.approved).toContain('badge-success');
    expect(classes.rejected).toContain('badge-danger');
    expect(classes.flagged).toContain('badge-info');
    expect(classes.pending).toContain('badge-pending');

    // No two statuses should share a colour class.
    expect(new Set(Object.values(classes)).size).toBe(4);
  });

  it('falls back to the info style for an unrecognised variant', () => {
    render(<Badge variant="something-else">other</Badge>);
    expect(screen.getByText('other').className).toContain('badge-info');
  });
});
