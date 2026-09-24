import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { AlertCircle, AlertTriangle, CheckCircle, FileText, Loader, Upload } from 'lucide-react';
import { documentsApi, getErrorMessage } from '../../services/api';
import { humanize } from '../../utils/format';
import './UploadZone.css';

function UploadResult({ result, onReset }) {
  const failed = result.processing_status === 'failed';
  return (
    <div className="upload-result glass-card" role="status">
      <div className="upload-result-icon">
        {failed
          ? <AlertTriangle size={20} color="var(--status-warning)" />
          : <CheckCircle size={20} color="var(--status-success)" />}
      </div>
      <div className="upload-result-info">
        <p className="upload-result-filename">
          <FileText size={14} /> {result.filename}
        </p>
        {failed ? (
          <p className="upload-result-class upload-result-class--failed">
            Uploaded, but processing failed: {result.error_message || 'the document could not be read.'}
          </p>
        ) : (
          <p className="upload-result-class">
            Classified as: <strong>{humanize(result.document_class) || 'other'}</strong>
          </p>
        )}
      </div>
      <button className="upload-result-reset" onClick={onReset} id="upload-reset-btn">
        Upload Another
      </button>
    </div>
  );
}

export default function UploadZone({ onUploadComplete }) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const onDrop = useCallback(async (acceptedFiles) => {
    const [file] = acceptedFiles;
    if (!file) return;

    setUploading(true);
    setProgress(0);
    setResult(null);
    setError(null);

    try {
      const response = await documentsApi.upload(file, (event) => {
        if (event.total) setProgress(Math.round((event.loaded / event.total) * 100));
      });
      setResult(response);
      onUploadComplete?.(response);
    } catch (err) {
      setError(getErrorMessage(err));
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
        <input {...getInputProps()} id="document-upload-input" aria-label="Upload a document" />

        {uploading ? (
          <div className="upload-progress" role="status">
            <Loader size={40} className="upload-spinner" />
            <p className="upload-progress-text">
              {progress < 100 ? 'Uploading document…' : 'Extracting text and classifying…'}
            </p>
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

      {result && <UploadResult result={result} onReset={resetUpload} />}

      {error && (
        <div className="upload-error" role="alert">
          <AlertCircle size={16} /> Upload failed: {error}
        </div>
      )}
    </div>
  );
}
