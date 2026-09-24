import { afterEach, describe, expect, it } from 'vitest';
import { mockApi } from '../test/mockApi';
import { BATCH_VALIDATE_LIMIT, claimsApi, documentsApi, getErrorMessage, validationApi } from './api';

async function rejectionOf(promise) {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error('Expected the request to fail');
}

describe('API errors', () => {
  it('uses the backend detail message', async () => {
    mockApi({ 'GET /claims/missing': { status: 404, data: { detail: 'Claim not found' } } });

    const error = await rejectionOf(claimsApi.get('missing'));

    expect(error.status).toBe(404);
    expect(getErrorMessage(error)).toBe('Claim not found');
  });

  it('joins FastAPI validation errors into one message', async () => {
    mockApi({
      'GET /claims': {
        status: 422,
        data: { detail: [{ loc: ['query', 'limit'], msg: 'Input should be less than or equal to 100' }] },
      },
    });

    const error = await rejectionOf(claimsApi.list({ limit: 500 }));

    expect(getErrorMessage(error)).toBe('Input should be less than or equal to 100');
  });

  it('falls back to a status-specific message when there is no detail', async () => {
    mockApi({ 'POST /documents/upload': { status: 413, data: null } });

    const error = await rejectionOf(documentsApi.upload(new File(['x'], 'scan.pdf')));

    expect(getErrorMessage(error)).toBe('The file is too large. The maximum size is 50 MB.');
  });

  it('explains admin-only 401s and lets callers override the wording', async () => {
    mockApi({ 'DELETE /documents/doc-1': { status: 401, data: { detail: 'Missing admin key' } } });

    const error = await rejectionOf(documentsApi.delete('doc-1'));

    expect(getErrorMessage(error)).toMatch(/disabled on the public demo/);
    expect(getErrorMessage(error, { 401: 'Deleting is disabled on the public demo.' }))
      .toBe('Deleting is disabled on the public demo.');
  });

  it('reports an unreachable server', async () => {
    mockApi({});

    const error = await rejectionOf(claimsApi.list());

    expect(error.status).toBeNull();
    expect(getErrorMessage(error)).toMatch(/Cannot reach the IntelliClaim API/);
  });
});

describe('requests', () => {
  afterEach(() => localStorage.clear());

  it('does not send an Authorization header', async () => {
    localStorage.setItem('auth_token', 'stale-token');
    const requests = mockApi({ 'GET /claims': { data: { claims: [], total: 0 } } });

    await claimsApi.list();

    expect(requests[0].headers.Authorization).toBeUndefined();
  });
});

describe('validationApi.batchValidate', () => {
  it('posts claim IDs to /batch-validate', async () => {
    const requests = mockApi({
      'POST /batch-validate': ({ body }) => ({
        data: { results: body.claim_ids.map((id) => ({ claim_id: id, risk_level: 'low' })) },
      }),
    });

    const response = await validationApi.batchValidate(['clm-1', 'clm-2']);

    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({ method: 'POST', url: '/batch-validate', body: { claim_ids: ['clm-1', 'clm-2'] } });
    expect(response.total_validated).toBe(2);
  });

  it('splits more than 100 IDs into sequential requests and merges the results', async () => {
    const requests = mockApi({
      'POST /batch-validate': ({ body }) => ({
        data: { results: body.claim_ids.map((id) => ({ claim_id: id })) },
      }),
    });
    const ids = Array.from({ length: 250 }, (_, index) => `clm-${index}`);

    const response = await validationApi.batchValidate(ids);

    expect(requests.map((request) => request.body.claim_ids.length)).toEqual([100, 100, 50]);
    expect(Math.max(...requests.map((request) => request.body.claim_ids.length))).toBe(BATCH_VALIDATE_LIMIT);
    expect(response.results.map((result) => result.claim_id)).toEqual(ids);
    expect(response.total_validated).toBe(250);
  });

  it('makes no request for an empty list', async () => {
    const requests = mockApi({});

    await expect(validationApi.batchValidate([])).resolves.toEqual({ results: [], total_validated: 0 });
    expect(requests).toHaveLength(0);
  });
});
