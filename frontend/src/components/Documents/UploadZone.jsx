import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { AlertCircle, AlertTriangle, CheckCircle2, FileUp } from 'lucide-react';
import { documentsApi, getErrorMessage } from '../../services/api';
import { humanize } from '../../utils/format';
import './UploadZone.css';

// Mirrors the backend's upload validation (POST /documents/upload).
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const ACCEPTED_TYPES = {
  'application/pdf': ['.pdf'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/tiff': ['.tif', '.tiff'],
};

function describeRejection({ file, errors }) {
  const codes = errors.map((error) => error.code);
  if (codes.includes('too-many-files')) return 'Upload one document at a time.';
  if (codes.includes('file-too-large')) return `${file.name} is larger than the 50 MB limit.`;
  if (codes.includes('file-invalid-type')) {
    return `${file.name} is not a supported file type. Use a PDF, PNG, JPG or TIFF file.`;
  }
  return errors[0]?.message ?? `${file.name} cannot be uploaded.`;
}

function UploadResult({ result, onReset, onReview }) {
  const failed = result.processing_status === 'failed';
  return (
    <div className={`upload-result ${failed ? 'upload-result--failed' : ''}`} role="status">
      {failed
        ? <AlertTriangle size={18} className="upload-result-icon" aria-hidden="true" />
        : <CheckCircle2 size={18} className="upload-result-icon" aria-hidden="true" />}
      <div className="upload-result-info">
        <p className="upload-result-filename" translate="no">{result.filename}</p>
        {failed ? (
          <p className="upload-result-class">
            Uploaded, but processing failed: {result.error_message || 'the document could not be read.'}
          </p>
        ) : (
          <p className="upload-result-class">
            Classified as: <strong>{humanize(result.document_class) || 'other'}</strong>
          </p>
        )}
      </div>
      <div className="upload-result-actions">
        {onReview && !failed && (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => onReview(result)}>
            Review document
          </button>
        )}
        <button type="button" className="btn btn-secondary btn-sm" onClick={onReset} id="upload-reset-btn">
          Upload another
        </button>
      </div>
    </div>
  );
}

export default function UploadZone({ onUploadComplete, onReview }) {
  const [uploading, setUploading] = useState(false);
  const [fileName, setFileName] = useState('');
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const onDrop = useCallback(async (acceptedFiles, fileRejections) => {
    if (fileRejections.length > 0) {
      setResult(null);
      setError(describeRejection(fileRejections[0]));
      return;
    }
    const [file] = acceptedFiles;
    if (!file) return;

    setUploading(true);
    setFileName(file.name);
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
      setError(`Upload failed: ${getErrorMessage(err)}`);
    } finally {
      setUploading(false);
    }
  }, [onUploadComplete]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxSize: MAX_UPLOAD_BYTES,
    maxFiles: 1,
    multiple: false,
    disabled: uploading,
  });

  const resetUpload = () => {
    setResult(null);
    setError(null);
    setProgress(0);
  };

  const reading = progress >= 100;

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
            <p className="upload-progress-text">
              <span translate="no">{fileName}</span>
              <span>{reading ? 'Reading the text and classifying…' : `Uploading… ${progress}%`}</span>
            </p>
            <span className="upload-progress-bar" aria-hidden="true">
              <span
                className={`upload-progress-fill ${reading ? 'upload-progress-fill--reading' : ''}`}
                style={{ transform: `scaleX(${progress / 100})` }}
              />
            </span>
          </div>
        ) : (
          <div className="upload-prompt">
            <FileUp size={22} className="upload-prompt-icon" aria-hidden="true" />
            <div>
              <p className="upload-title">
                {isDragActive ? 'Drop the file to upload it' : (
                  <>Drop a document here, or <span className="upload-choose">choose a file</span></>
                )}
              </p>
              <p className="upload-subtitle">
                PDF, PNG, JPG or TIFF up to 50&nbsp;MB. Scans are read with OCR and classified as they upload.
              </p>
            </div>
          </div>
        )}
      </div>

      {result && <UploadResult result={result} onReset={resetUpload} onReview={onReview} />}

      {error && (
        <div className="upload-error" role="alert">
          <AlertCircle size={16} aria-hidden="true" /> {error}
        </div>
      )}
    </div>
  );
}
