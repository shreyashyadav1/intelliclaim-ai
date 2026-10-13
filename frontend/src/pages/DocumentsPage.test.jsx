import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { deferred, mockApi } from '../test/mockApi';
import { renderWithRouter } from '../test/render';
import DocumentsPage from './DocumentsPage';

const doc = (id, filename, extra = {}) => ({
  id,
  filename,
  file_type: 'pdf',
  file_size: 2048,
  document_class: 'invoice',
  processing_status: 'processed',
  created_at: '2026-09-01T10:00:00Z',
  ...extra,
});

const documentNames = () => screen.getAllByRole('heading', { level: 4 }).map((heading) => heading.textContent);

describe('DocumentsPage', () => {
  it('restores a document in place when the delete request fails', async () => {
    const pendingDelete = deferred();
    mockApi({
      'GET /documents': { data: { documents: [doc('doc-a', 'invoice_a.pdf'), doc('doc-b', 'invoice_b.pdf')], total: 2 } },
      'DELETE /documents/doc-a': () => pendingDelete.promise,
    });
    const { user } = renderWithRouter(<DocumentsPage />);

    await user.click(await screen.findByRole('button', { name: 'Delete invoice_a.pdf' }));

    // Removed optimistically while the request is in flight...
    expect(documentNames()).toEqual(['invoice_b.pdf']);

    pendingDelete.resolve({ status: 401, data: { detail: 'Admin key required' } });

    // ...then put back in its original position with the reason.
    expect(await screen.findByText(/Deleting is disabled on the public demo\./)).toBeInTheDocument();
    expect(documentNames()).toEqual(['invoice_a.pdf', 'invoice_b.pdf']);
    expect(screen.getByRole('heading', { name: /Documents \(2\)/ })).toBeInTheDocument();
  });

  it('keeps a document removed once the delete succeeds', async () => {
    mockApi({
      'GET /documents': { data: { documents: [doc('doc-a', 'invoice_a.pdf'), doc('doc-b', 'invoice_b.pdf')], total: 2 } },
      'DELETE /documents/doc-a': { data: { message: 'Document deleted', id: 'doc-a' } },
    });
    const { user } = renderWithRouter(<DocumentsPage />);

    await user.click(await screen.findByRole('button', { name: 'Delete invoice_a.pdf' }));

    expect(await screen.findByText('Deleted invoice_a.pdf.')).toBeInTheDocument();
    expect(documentNames()).toEqual(['invoice_b.pdf']);
  });

  it('shows failed documents with their error message', async () => {
    mockApi({
      'GET /documents': {
        data: {
          documents: [doc('doc-f', 'scan.tiff', { processing_status: 'failed', error_message: 'OCR timed out' })],
          total: 1,
        },
      },
    });
    renderWithRouter(<DocumentsPage />);

    expect(await screen.findByText('OCR timed out')).toBeInTheDocument();
    expect(screen.getByText('Processing failed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Extract claim data from scan.tiff' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Index scan.tiff for search' })).toBeDisabled();
  });

  it('shows extracted fields and indexes the document for search', async () => {
    const requests = mockApi({
      'GET /documents': { data: { documents: [doc('doc-a', 'invoice_a.pdf')], total: 1 } },
      'POST /extract/doc-a': {
        data: {
          claim_id: 'clm-9',
          document_id: 'doc-a',
          extracted_data: { patient_name: 'Dana Whitfield', treatment_cost: 18250 },
          confidence_score: 0.82,
          is_new_claim: true,
        },
      },
      'POST /rag/index/doc-a': { data: { success: true, document_id: 'doc-a' } },
    });
    const { user } = renderWithRouter(<DocumentsPage />);

    await user.click(await screen.findByRole('button', { name: 'Extract claim data from invoice_a.pdf' }));

    expect(await screen.findByText('Dana Whitfield')).toBeInTheDocument();
    expect(screen.getByText('$18,250')).toBeInTheDocument();
    expect(screen.getByText('82% confidence')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View claim' })).toHaveAttribute('href', '/claims/clm-9');

    await user.click(screen.getByRole('button', { name: 'Index for search' }));

    expect(await screen.findByText(/is indexed and can be queried from AI Search/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Indexed for search' })).toBeDisabled();
    await waitFor(() => expect(requests.map((request) => `${request.method} ${request.url}`)).toContain('POST /rag/index/doc-a'));
  });

  it('explains that re-indexing everything is disabled on the public demo', async () => {
    mockApi({
      'GET /documents': { data: { documents: [doc('doc-a', 'invoice_a.pdf')], total: 1 } },
      'POST /rag/index-all': { status: 401, data: { detail: 'Admin key required' } },
    });
    const { user } = renderWithRouter(<DocumentsPage />);

    await user.click(await screen.findByRole('button', { name: /Re-index all/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Re-indexing every document is disabled on the public demo.');
  });
});
