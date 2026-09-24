import { useCallback, useState } from 'react';
import UploadZone from '../components/Documents/UploadZone';
import DocumentList from '../components/Documents/DocumentList';
import DocumentViewer from '../components/Documents/DocumentViewer';
import ExtractionResults from '../components/Claims/ExtractionResults';
import Notice from '../components/Shared/Notice';
import { useApiQuery } from '../hooks/useApiQuery';
import { documentsApi, extractionApi, getErrorMessage } from '../services/api';

// GET /documents caps `limit` at 100.
const loadDocuments = () => documentsApi.list({ limit: 100 });

function withoutDocument(list, id) {
  if (!list) return list;
  return {
    ...list,
    documents: list.documents.filter((doc) => doc.id !== id),
    total: Math.max((list.total ?? 1) - 1, 0),
  };
}

function withDocumentAt(list, doc, index) {
  if (!list || list.documents.some((existing) => existing.id === doc.id)) return list;
  const documents = [...list.documents];
  documents.splice(Math.min(Math.max(index, 0), documents.length), 0, doc);
  return { ...list, documents, total: (list.total ?? 0) + 1 };
}

export default function DocumentsPage() {
  const documents = useApiQuery(loadDocuments);
  const { setData: setDocuments } = documents;
  const [viewer, setViewer] = useState(null);
  const [busy, setBusy] = useState({});
  const [notice, setNotice] = useState(null);
  const [extraction, setExtraction] = useState(null);

  const setDocumentBusy = (id, action) => {
    setBusy((current) => {
      const next = { ...current };
      if (action) next[id] = action;
      else delete next[id];
      return next;
    });
  };

  const handleView = async (doc) => {
    setViewer({ document: doc, loading: true, error: null });
    try {
      const full = await documentsApi.get(doc.id);
      setViewer((current) => (current?.document.id === doc.id ? { document: full, loading: false, error: null } : current));
    } catch (err) {
      setViewer((current) => (
        current?.document.id === doc.id ? { ...current, loading: false, error: getErrorMessage(err) } : current
      ));
    }
  };

  const closeViewer = useCallback(() => setViewer(null), []);

  const handleDelete = async (doc) => {
    const index = documents.data?.documents.findIndex((existing) => existing.id === doc.id) ?? -1;
    setNotice(null);
    // Optimistic: hide the card immediately and put it back if the server refuses.
    setDocuments((current) => withoutDocument(current, doc.id));
    try {
      await documentsApi.delete(doc.id);
      setNotice({ tone: 'success', message: `Deleted ${doc.filename}.` });
      setExtraction((current) => (current?.document.id === doc.id ? null : current));
    } catch (err) {
      if (err.status === 404) {
        setNotice({ tone: 'info', message: `${doc.filename} had already been deleted.` });
        return;
      }
      setDocuments((current) => withDocumentAt(current, doc, index));
      setNotice({
        tone: 'error',
        message: `Couldn't delete ${doc.filename}: ${getErrorMessage(err, { 401: 'Deleting is disabled on the public demo.' })}`,
      });
    }
  };

  const handleExtract = async (doc) => {
    setViewer(null);
    setNotice(null);
    setExtraction(null);
    setDocumentBusy(doc.id, 'extracting');
    try {
      const result = await extractionApi.extract(doc.id);
      setExtraction({ document: doc, result });
    } catch (err) {
      setNotice({ tone: 'error', message: `Extraction failed for ${doc.filename}: ${getErrorMessage(err)}` });
    } finally {
      setDocumentBusy(doc.id, null);
    }
  };

  return (
    <div className="page-enter" id="documents-page">
      <UploadZone onUploadComplete={documents.refetch} />

      {notice && (
        <Notice tone={notice.tone} onDismiss={() => setNotice(null)}>
          {notice.message}
        </Notice>
      )}

      {extraction && (
        <ExtractionResults
          document={extraction.document}
          result={extraction.result}
          onDismiss={() => setExtraction(null)}
        />
      )}

      <DocumentList
        documents={documents.data?.documents}
        total={documents.data?.total}
        error={documents.error}
        onRetry={documents.refetch}
        busy={busy}
        onView={handleView}
        onDelete={handleDelete}
        onExtract={handleExtract}
      />

      {viewer && (
        <DocumentViewer
          document={viewer.document}
          loading={viewer.loading}
          error={viewer.error}
          extracting={busy[viewer.document.id] === 'extracting'}
          onClose={closeViewer}
          onExtract={handleExtract}
        />
      )}
    </div>
  );
}
