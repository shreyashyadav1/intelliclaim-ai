import { FileText, Image, Trash2, Eye, Brain } from 'lucide-react';
import Badge from '../Shared/Badge';
import './DocumentList.css';

const demoDocuments = [
  { id: 'doc-1', filename: 'medical_report_johnson.pdf', file_type: 'pdf', document_class: 'medical_report', file_size: 245000, processing_status: 'processed', created_at: '2026-06-15T10:00:00Z' },
  { id: 'doc-2', filename: 'invoice_chen_diabetes.pdf', file_type: 'pdf', document_class: 'invoice', file_size: 128000, processing_status: 'processed', created_at: '2026-06-14T09:30:00Z' },
  { id: 'doc-3', filename: 'claim_form_rodriguez.pdf', file_type: 'pdf', document_class: 'claim_form', file_size: 312000, processing_status: 'processed', created_at: '2026-06-13T14:20:00Z' },
  { id: 'doc-4', filename: 'discharge_summary_williams.pdf', file_type: 'pdf', document_class: 'discharge_summary', file_size: 198000, processing_status: 'processed', created_at: '2026-06-12T11:45:00Z' },
  { id: 'doc-5', filename: 'xray_scan_thompson.jpg', file_type: 'image', document_class: 'medical_report', file_size: 890000, processing_status: 'processed', created_at: '2026-06-11T08:15:00Z' },
  { id: 'doc-6', filename: 'billing_statement_davis.pdf', file_type: 'pdf', document_class: 'invoice', file_size: 156000, processing_status: 'processed', created_at: '2026-06-10T16:00:00Z' },
];

const classColors = {
  medical_report: 'info',
  invoice: 'warning',
  claim_form: 'success',
  discharge_summary: 'pending',
  other: 'default',
};

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function formatDate(dateStr) {
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function DocumentList({ documents, onView, onDelete, onExtract }) {
  const docs = documents && documents.length > 0 ? documents : demoDocuments;

  return (
    <div className="document-list" id="document-list">
      <div className="document-list-header">
        <h3>Documents ({docs.length})</h3>
      </div>
      <div className="document-grid">
        {docs.map((doc) => (
          <div key={doc.id} className="document-card glass-card" id={`doc-${doc.id}`}>
            <div className="document-card-icon">
              {doc.file_type === 'image' ? <Image size={24} /> : <FileText size={24} />}
            </div>
            <div className="document-card-info">
              <h4 className="document-card-name" title={doc.filename}>{doc.filename}</h4>
              <div className="document-card-meta">
                <Badge variant={classColors[doc.document_class] || 'default'}>
                  {doc.document_class?.replace(/_/g, ' ')}
                </Badge>
                <span className="document-card-size">{formatSize(doc.file_size)}</span>
                <span className="document-card-date">{formatDate(doc.created_at)}</span>
              </div>
            </div>
            <div className="document-card-actions">
              <button className="doc-action-btn" onClick={() => onView?.(doc)} title="View" id={`view-${doc.id}`}>
                <Eye size={16} />
              </button>
              <button className="doc-action-btn doc-action-btn--accent" onClick={() => onExtract?.(doc)} title="Extract Data" id={`extract-${doc.id}`}>
                <Brain size={16} />
              </button>
              <button className="doc-action-btn doc-action-btn--danger" onClick={() => onDelete?.(doc.id)} title="Delete" id={`delete-${doc.id}`}>
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
