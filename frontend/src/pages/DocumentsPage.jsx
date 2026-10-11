import { useCallback, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import UploadZone from '../components/Documents/UploadZone';
import DocumentList from '../components/Documents/DocumentList';
import DocumentViewer from '../components/Documents/DocumentViewer';
import Notice from '../components/Shared/Notice';
import PageHeader from '../components/Shared/PageHeader';
import { useApiQuery } from '../hooks/useApiQuery';
import { documentsApi, extractionApi, getErrorMessage, ragApi } from '../services/api';

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
  const [searchParams, setSearchParams] = useSearchParams();
  const [busy, setBusy] = useState({});
  const [notice, setNotice] = useState(null);
  const [extractions, setExtractions] = useState({});
  const [indexedIds, setIndexedIds] = useState(() => new Set());
  const [indexingAll, setIndexingAll] = useState(false);
  // Documents opened from an upload result, before the refreshed list includes them.
  const [opened, setOpened] = useState({});

  // The open document lives in the URL (?doc=<id>), so a review can be linked to.
  const openId = searchParams.get('doc');
  const loadOpenDocument = useCallback(() => (openId ? documentsApi.get(openId) : Promise.resolve(null)), [openId]);
  const openDocument = useApiQuery(loadOpenDocument);
  const openSummary = documents.data?.documents.find((doc) => doc.id === openId) ?? opened[openId];
  const sheetDocument = openDocument.data ?? openSummary ?? (openId ? { id: openId, filename: 'Document' } : null);

  const setDocumentBusy = (id, action) => {
    setBusy((current) => {
      const next = { ...current };
      if (action) next[id] = action;
      else delete next[id];
      return next;
    });
  };

  const setOpenId = (id) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (id) next.set('doc', id);
      else next.delete('doc');
      return next;
    }, { replace: true });
  };

  const handleView = (doc) => {
    setNotice(null);
    setOpened((current) => ({ ...current, [doc.id]: doc }));
    setOpenId(doc.id);
  };

  const closeViewer = useCallback(() => {
    setNotice(null);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete('doc');
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const handleDelete = async (doc) => {
    const index = documents.data?.documents.findIndex((existing) => existing.id === doc.id) ?? -1;
    setNotice(null);
    // Optimistic: hide the row immediately and put it back if the server refuses.
    setDocuments((current) => withoutDocument(current, doc.id));
    try {
      await documentsApi.delete(doc.id);
      setNotice({ tone: 'success', message: `Deleted ${doc.filename}.` });
      setExtractions((current) => {
        const next = { ...current };
        delete next[doc.id];
        return next;
      });
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

  // Extraction runs with the document open, so its fields appear beside the text they came from.
  const handleExtract = async (doc) => {
    handleView(doc);
    setDocumentBusy(doc.id, 'extracting');
    try {
      const result = await extractionApi.extract(doc.id);
      setExtractions((current) => ({ ...current, [doc.id]: result }));
    } catch (err) {
      setNotice({ tone: 'error', message: `Extraction failed for ${doc.filename}: ${getErrorMessage(err)}` });
    } finally {
      setDocumentBusy(doc.id, null);
    }
  };

  const handleIndex = async (doc) => {
    setNotice(null);
    setDocumentBusy(doc.id, 'indexing');
    try {
      const response = await ragApi.indexDocument(doc.id);
      if (response?.success === false) {
        setNotice({ tone: 'error', message: `${doc.filename} could not be added to the search index.` });
        return;
      }
      setIndexedIds((current) => new Set(current).add(doc.id));
      setNotice({ tone: 'success', message: `${doc.filename} is indexed and can be queried from AI Search.` });
    } catch (err) {
      setNotice({ tone: 'error', message: `Indexing failed for ${doc.filename}: ${getErrorMessage(err)}` });
    } finally {
      setDocumentBusy(doc.id, null);
    }
  };

  const handleIndexAll = async () => {
    setNotice(null);
    setIndexingAll(true);
    try {
      const { indexed = 0, errors = 0, total = 0 } = await ragApi.indexAll();
      setNotice({
        tone: errors > 0 ? 'error' : 'success',
        message: `Re-indexed ${indexed} of ${total} processed documents${errors > 0 ? `; ${errors} failed` : ''}.`,
      });
    } catch (err) {
      setNotice({
        tone: 'error',
        message: getErrorMessage(err, {
          401: 'Re-indexing every document is disabled on the public demo. Index documents individually instead.',
        }),
      });
    } finally {
      setIndexingAll(false);
    }
  };

  const noticeElement = notice && (
    <Notice tone={notice.tone} onDismiss={() => setNotice(null)}>
      {notice.message}
    </Notice>
  );

  return (
    <div id="documents-page">
      <PageHeader
        title="Documents"
        description="Upload scans and PDFs, check the text that was read from them, and extract each one into a claim."
      />

      <UploadZone onUploadComplete={documents.refetch} onReview={handleView} />

      {!sheetDocument && noticeElement && <div className="documents-notice">{noticeElement}</div>}

      <DocumentList
        documents={documents.data?.documents}
        total={documents.data?.total}
        error={documents.error}
        onRetry={documents.refetch}
        busy={busy}
        indexedIds={indexedIds}
        indexingAll={indexingAll}
        onView={handleView}
        onDelete={handleDelete}
        onExtract={handleExtract}
        onIndex={handleIndex}
        onIndexAll={handleIndexAll}
      />

      {sheetDocument && (
        <DocumentViewer
          key={sheetDocument.id}
          document={sheetDocument}
          loading={!openDocument.data && !openDocument.error}
          error={openDocument.error ? getErrorMessage(openDocument.error) : null}
          onRetry={openDocument.refetch}
          extraction={extractions[sheetDocument.id]}
          extracting={busy[sheetDocument.id] === 'extracting'}
          indexing={busy[sheetDocument.id] === 'indexing'}
          indexed={indexedIds.has(sheetDocument.id)}
          notice={noticeElement}
          onClose={closeViewer}
          onExtract={handleExtract}
          onIndex={handleIndex}
        />
      )}
    </div>
  );
}
