import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { mockApi } from '../../test/mockApi';
import UploadZone from './UploadZone';

function pdf(name = 'claim_form.pdf') {
  return new File(['%PDF-1.7 test'], name, { type: 'application/pdf' });
}

function renderUploadZone() {
  const onUploadComplete = vi.fn();
  const user = userEvent.setup();
  render(<UploadZone onUploadComplete={onUploadComplete} />);
  return { user, onUploadComplete, input: screen.getByLabelText('Upload a document') };
}

describe('UploadZone', () => {
  it('shows the classification returned by the API after a successful upload', async () => {
    const requests = mockApi({
      'POST /documents/upload': {
        data: {
          id: 'doc-1',
          filename: 'claim_form.pdf',
          file_type: 'pdf',
          document_class: 'claim_form',
          processing_status: 'processed',
        },
      },
    });
    const { user, input, onUploadComplete } = renderUploadZone();

    await user.upload(input, pdf());

    expect(await screen.findByText('claim form')).toBeInTheDocument();
    expect(screen.getByText(/Classified as/)).toBeInTheDocument();
    expect(onUploadComplete).toHaveBeenCalledWith(expect.objectContaining({ id: 'doc-1' }));
    expect(requests).toHaveLength(1);
    expect(requests[0].body.get('file').name).toBe('claim_form.pdf');
  });

  it('shows the backend error and no success card when the upload fails', async () => {
    mockApi({
      'POST /documents/upload': { status: 415, data: { detail: 'Unsupported file type: application/pdf' } },
    });
    const { user, input, onUploadComplete } = renderUploadZone();

    await user.upload(input, pdf());

    expect(await screen.findByRole('alert')).toHaveTextContent('Upload failed: Unsupported file type: application/pdf');
    expect(screen.queryByText(/Classified as/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Upload Another' })).not.toBeInTheDocument();
    expect(onUploadComplete).not.toHaveBeenCalled();
  });

  it('reports a document the backend could not process', async () => {
    mockApi({
      'POST /documents/upload': {
        data: {
          id: 'doc-2',
          filename: 'blurry.png',
          processing_status: 'failed',
          error_message: 'OCR found no readable text',
        },
      },
    });
    const { user, input } = renderUploadZone();

    await user.upload(input, new File(['png'], 'blurry.png', { type: 'image/png' }));

    expect(await screen.findByText(/processing failed: OCR found no readable text/)).toBeInTheDocument();
    expect(screen.queryByText(/Classified as/)).not.toBeInTheDocument();
  });

  it('rejects files over 50 MB without sending them', async () => {
    const requests = mockApi({});
    const { user, input } = renderUploadZone();
    const largeFile = pdf('scan.pdf');
    Object.defineProperty(largeFile, 'size', { value: 51 * 1024 * 1024 });

    await user.upload(input, largeFile);

    expect(await screen.findByRole('alert')).toHaveTextContent('scan.pdf is larger than the 50 MB limit.');
    expect(requests).toHaveLength(0);
  });

  it('accepts TIFF scans', async () => {
    const requests = mockApi({
      'POST /documents/upload': {
        data: { id: 'doc-3', filename: 'scan.tif', document_class: 'medical_report', processing_status: 'processed' },
      },
    });
    const { user, input } = renderUploadZone();

    await user.upload(input, new File(['tiff'], 'scan.tif', { type: 'image/tiff' }));

    expect(await screen.findByText('medical report')).toBeInTheDocument();
    expect(requests).toHaveLength(1);
  });
});
