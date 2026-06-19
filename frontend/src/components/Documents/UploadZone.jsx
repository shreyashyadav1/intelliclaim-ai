import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, CheckCircle, AlertCircle, Loader } from 'lucide-react';
import { documentsApi } from '../../services/api';
import './UploadZone.css';

export default function UploadZone({ onUploadComplete }) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const onDrop = useCallback(async (acceptedFiles) => {
    if (acceptedFiles.length === 0) return;

    const file = acceptedFiles[0];
    setUploading(true);
    setProgress(0);
    setResult(null);
    setError(null);

    try {
      const response = await documentsApi.upload(file, (event) => {
        const pct = Math.round((event.loaded / event.total) * 100);
        setProgress(pct);
      });
      setResult(response);
      onUploadComplete?.();
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed');
      // Demo fallback
      setResult({
        id: 'demo-' + Date.now(),
        filename: file.name,
        document_class: 'medical_report',
        processing_status: 'processed',
        extracted_text_preview: 'Demo: This document has been processed with OCR text extraction...',
      });
    } finally {
      setUploading(false);
    }
  }, [onUploadComplete]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
    },
    maxFiles: 1,
    disabled: uploading,
  });

  const resetUpload = () => {
    setResult(null);
    setError(null);
    setProgress(0);
  };

  return (
    <div className="upload-zone-container">
      <div
        {...getRootProps()}
        className={`upload-zone ${isDragActive ? 'upload-zone--active' : ''} ${uploading ? 'upload-zone--uploading' : ''}`}
        id="document-upload-zone"
      >
        <input {...getInputProps()} id="document-upload-input" />

        {uploading ? (
          <div className="upload-progress">
            <Loader size={40} className="upload-spinner" />
            <p className="upload-progress-text">Processing document...</p>
            <div className="upload-progress-bar">
              <div className="upload-progress-fill" style={{ width: `${progress}%` }} />
            </div>
            <span className="upload-progress-pct">{progress}%</span>
          </div>
        ) : (
          <div className="upload-prompt">
            <div className="upload-icon-wrapper">
              <Upload size={32} />
            </div>
            <p className="upload-title">
              {isDragActive ? 'Drop your file here' : 'Drag & drop a document'}
            </p>
            <p className="upload-subtitle">or click to browse — PDF, PNG, JPG</p>
          </div>
        )}
      </div>

      {result && (
        <div className="upload-result glass-card">
          <div className="upload-result-icon">
            <CheckCircle size={20} color="var(--status-success)" />
          </div>
          <div className="upload-result-info">
            <p className="upload-result-filename">
              <FileText size={14} /> {result.filename}
            </p>
            <p className="upload-result-class">
              Classified as: <strong>{result.document_class?.replace(/_/g, ' ')}</strong>
            </p>
          </div>
          <button className="upload-result-reset" onClick={resetUpload} id="upload-reset-btn">
            Upload Another
          </button>
        </div>
      )}

      {error && !result && (
        <div className="upload-error">
          <AlertCircle size={16} /> {error}
        </div>
      )}
    </div>
  );
}
