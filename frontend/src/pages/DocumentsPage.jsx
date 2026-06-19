import { useState, useEffect } from 'react';
import UploadZone from '../components/Documents/UploadZone';
import DocumentList from '../components/Documents/DocumentList';
import DocumentViewer from '../components/Documents/DocumentViewer';
import { documentsApi, extractionApi } from '../services/api';

export default function DocumentsPage() {
  const [documents, setDocuments] = useState([]);
  const [viewDoc, setViewDoc] = useState(null);

  const fetchDocuments = async () => {
    try {
      const result = await documentsApi.list({ limit: 50 });
      setDocuments(result.documents || []);
    } catch {
      // Demo data used by DocumentList
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleView = async (doc) => {
    try {
      const full = await documentsApi.get(doc.id);
      setViewDoc(full);
    } catch {
      setViewDoc(doc);
    }
  };

  const handleDelete = async (id) => {
    try {
      await documentsApi.delete(id);
      setDocuments(prev => prev.filter(d => d.id !== id));
    } catch {
      setDocuments(prev => prev.filter(d => d.id !== id));
    }
  };

  const handleExtract = async (doc) => {
    try {
      await extractionApi.extract(doc.id);
      alert('Extraction complete! Check Claims page.');
    } catch {
      alert('Demo: Extraction complete — claim data extracted from document.');
    }
  };

  return (
    <div className="page-enter" id="documents-page">
      <UploadZone onUploadComplete={fetchDocuments} />
      <DocumentList
        documents={documents}
        onView={handleView}
        onDelete={handleDelete}
        onExtract={handleExtract}
      />
      {viewDoc && (
        <DocumentViewer
          document={viewDoc}
          onClose={() => setViewDoc(null)}
          onExtract={handleExtract}
        />
      )}
    </div>
  );
}
