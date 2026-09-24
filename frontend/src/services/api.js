import axios from 'axios';

/**
 * Base URL of the IntelliClaim API, including the `/api` prefix,
 * e.g. `http://localhost:8000/api` (see .env.example).
 */
export const API_BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api').replace(/\/+$/, '');

// OCR, LLM extraction and validation routinely take longer than a CRUD call.
const SLOW_REQUEST = { timeout: 120_000 };
const BULK_REQUEST = { timeout: 300_000 };

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
});

/** Error returned by every API call. `message` is always safe to show to users. */
export class ApiError extends Error {
  constructor(message, { status = null, detail = null, cause } = {}) {
    super(message, { cause });
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

const FALLBACK_MESSAGES = {
  400: 'The server rejected the request.',
  401: 'This action requires an admin key and is disabled on the public demo.',
  404: 'The requested item no longer exists.',
  413: 'The file is too large. The maximum size is 50 MB.',
  415: 'This file type is not supported.',
  422: 'Some of the submitted data is invalid.',
  429: 'Too many requests. Please wait a moment and try again.',
  500: 'The server hit an unexpected error. Please try again.',
  502: 'The AI provider failed to respond. Please try again.',
  503: 'The AI provider is not configured on the server.',
};

// FastAPI returns {"detail": "..."}; request-validation errors carry a list of {msg}.
function readDetail(data) {
  const detail = data?.detail;
  if (typeof detail === 'string') return detail.trim() || null;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => item?.msg).filter(Boolean);
    return messages.length > 0 ? messages.join('; ') : null;
  }
  return null;
}

function toApiError(error) {
  if (error instanceof ApiError) return error;
  if (!axios.isAxiosError(error)) {
    return new ApiError(error?.message || 'Something went wrong.', { cause: error });
  }

  const { response } = error;
  if (!response) {
    const timedOut = error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT';
    const message = timedOut
      ? 'The server took too long to respond. Please try again.'
      : `Cannot reach the IntelliClaim API at ${API_BASE_URL}. Check that the backend is running.`;
    return new ApiError(message, { cause: error });
  }

  const { status } = response;
  const detail = readDetail(response.data);
  // A 401 detail describes the missing admin key; the generic wording reads better in the UI.
  const message = (status !== 401 && detail)
    || FALLBACK_MESSAGES[status]
    || `Request failed with HTTP ${status}.`;
  return new ApiError(message, { status, detail, cause: error });
}

api.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(toApiError(error)),
);

/**
 * User-facing message for a failed call. `overrides` maps HTTP status codes to
 * context-specific wording, e.g. `{ 401: 'Deleting is disabled on the public demo.' }`.
 */
export function getErrorMessage(error, overrides = {}) {
  const apiError = toApiError(error);
  return overrides[apiError.status] ?? apiError.message;
}

/* ── Documents ── */
export const documentsApi = {
  upload: (file, onUploadProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/documents/upload', formData, { ...SLOW_REQUEST, onUploadProgress });
  },
  list: (params) => api.get('/documents', { params }),
  get: (id) => api.get(`/documents/${id}`),
  delete: (id) => api.delete(`/documents/${id}`),
};

/* ── Claims ── */
export const claimsApi = {
  list: (params) => api.get('/claims', { params }),
  get: (id) => api.get(`/claims/${id}`),
  update: (id, data) => api.put(`/claims/${id}`, data),
  delete: (id) => api.delete(`/claims/${id}`),
  getDocuments: (id) => api.get(`/claims/${id}/documents`),
};

/* ── Extraction ── */
export const extractionApi = {
  extract: (documentId) => api.post(`/extract/${documentId}`, null, SLOW_REQUEST),
  getResults: (documentId) => api.get(`/extract/${documentId}/results`),
};

/* ── RAG ── */
export const ragApi = {
  query: (question, topK = 5) => api.post('/rag/query', { question, top_k: topK }, SLOW_REQUEST),
  indexDocument: (documentId) => api.post(`/rag/index/${documentId}`, null, SLOW_REQUEST),
  indexAll: () => api.post('/rag/index-all', null, BULK_REQUEST),
  getStats: () => api.get('/rag/stats'),
};

/* ── Analytics ── */
export const analyticsApi = {
  getOverview: () => api.get('/analytics/overview'),
  getClaimsTrend: (days = 30) => api.get('/analytics/claims-trend', { params: { days } }),
  getRiskDistribution: () => api.get('/analytics/risk-distribution'),
  getRecentClaims: (limit = 10) => api.get('/analytics/recent-claims', { params: { limit } }),
};

/* ── Validation ── */
export const validationApi = {
  validate: (claimId) => api.post(`/validate/${claimId}`, null, SLOW_REQUEST),
  getFlagged: (params) => api.get('/validate/flagged', { params }),
  batchValidate: (claimIds) => api.post('/validate/batch', { claim_ids: claimIds }),
};

export default api;
