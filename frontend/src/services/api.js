import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
    }
    return Promise.reject(error);
  }
);

/* ── Documents ── */
export const documentsApi = {
  upload: (file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    });
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
  extract: (documentId) => api.post(`/extract/${documentId}`),
  getResults: (documentId) => api.get(`/extract/${documentId}/results`),
};

/* ── RAG ── */
export const ragApi = {
  query: (question, topK = 5) => api.post('/rag/query', { question, top_k: topK }),
  indexDocument: (documentId) => api.post(`/rag/index/${documentId}`),
  indexAll: () => api.post('/rag/index-all'),
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
  validate: (claimId) => api.post(`/validate/${claimId}`),
  getFlagged: () => api.get('/validate/flagged'),
  batchValidate: (claimIds) => api.post('/validate/batch', { claim_ids: claimIds }),
};

export default api;
