import React, { useState, useRef } from 'react';
import { uploadFile } from '../services/api';
import { ApiError } from '../types';
import './UploadComponent.css';

interface UploadComponentProps {
  onUploadComplete: () => void;
}

type ConversionType = 
  | 'docx_to_pdf' | 'pdf_to_docx'
  | 'pdf_to_jpg' | 'pdf_to_png'
  | 'jpg_to_pdf' | 'png_to_pdf';

type InputFormat = 'docx' | 'pdf' | 'jpg' | 'png';

interface OutputOption {
  conversionType: ConversionType;
  outputFormat: string;
  label: string;
}

const FORMAT_CONVERSIONS: Record<InputFormat, OutputOption[]> = {
  docx: [
    { conversionType: 'docx_to_pdf', outputFormat: 'PDF', label: 'PDF Document' },
  ],
  pdf: [
    { conversionType: 'pdf_to_docx', outputFormat: 'DOCX', label: 'Word Document' },
    { conversionType: 'pdf_to_jpg', outputFormat: 'JPG', label: 'JPG Image' },
    { conversionType: 'pdf_to_png', outputFormat: 'PNG', label: 'PNG Image' },
  ],
  jpg: [{ conversionType: 'jpg_to_pdf', outputFormat: 'PDF', label: 'PDF Document' }],
  png: [{ conversionType: 'png_to_pdf', outputFormat: 'PDF', label: 'PDF Document' }],
};

const FORMAT_LABELS: Record<InputFormat, string> = {
  docx: 'Word Document',
  pdf: 'PDF Document',
  jpg: 'JPEG Image',
  png: 'PNG Image',
};

interface FileUploadStatus {
  file: File;
  inputFormat: InputFormat;
  selectedConversion: ConversionType;
  progress: number;
  status: 'pending' | 'uploading' | 'completed' | 'failed';
  error?: string;
}

const UploadComponent: React.FC<UploadComponentProps> = ({ onUploadComplete }) => {
  const [files, setFiles] = useState<FileUploadStatus[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const detectInputFormat = (filename: string): InputFormat | null => {
    const ext = filename.toLowerCase().split('.').pop();
    switch (ext) {
      case 'docx': return 'docx';
      case 'pdf': return 'pdf';
      case 'jpg': case 'jpeg': return 'jpg';
      case 'png': return 'png';
      default: return null;
    }
  };

  const validateFile = (file: File): { valid: boolean; format?: InputFormat; error?: string } => {
    const format = detectInputFormat(file.name);
    if (!format) return { valid: false, error: `Unsupported format: ${file.name}` };
    const maxSize = 10 * 1024 * 1024;  // 10MB for all files
    if (file.size > maxSize) return { valid: false, error: `File too large: ${file.name}` };
    if (file.size === 0) return { valid: false, error: `Empty file: ${file.name}` };
    return { valid: true, format };
  };

  const handleFilesSelect = (fileList: FileList) => {
    const newFiles: FileUploadStatus[] = [];
    const errors: string[] = [];

    Array.from(fileList).forEach(file => {
      const validation = validateFile(file);
      if (!validation.valid) {
        errors.push(validation.error!);
      } else if (!files.some(f => f.file.name === file.name && f.file.size === file.size)) {
        newFiles.push({
          file,
          inputFormat: validation.format!,
          selectedConversion: FORMAT_CONVERSIONS[validation.format!][0].conversionType,
          progress: 0,
          status: 'pending'
        });
      }
    });

    setFiles(prev => [...prev, ...newFiles]);
    if (errors.length > 0) setError(errors.join('. '));
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files.length > 0) handleFilesSelect(e.dataTransfer.files);
  };

  const handleConversionChange = (index: number, conversionType: ConversionType) => {
    setFiles(prev => prev.map((f, i) => i === index ? { ...f, selectedConversion: conversionType } : f));
  };

  const uploadSingleFile = async (fileStatus: FileUploadStatus, index: number) => {
    setFiles(prev => prev.map((f, i) => i === index ? { ...f, status: 'uploading', progress: 0 } : f));

    try {
      await uploadFile(
        fileStatus.file,
        (progress) => setFiles(prev => prev.map((f, i) => i === index ? { ...f, progress } : f)),
        fileStatus.selectedConversion
      );
      setFiles(prev => prev.map((f, i) => i === index ? { ...f, status: 'completed', progress: 100 } : f));
      onUploadComplete();
    } catch (err) {
      const apiError = err as ApiError;
      setFiles(prev => prev.map((f, i) => 
        i === index ? { ...f, status: 'failed', error: apiError.error?.message || 'Upload failed' } : f
      ));
    }
  };

  const handleUploadAll = async () => {
    const pendingIndices = files.map((f, i) => f.status === 'pending' ? i : -1).filter(i => i !== -1);
    if (pendingIndices.length === 0) return;

    setIsUploading(true);
    setError(null);

    for (const index of pendingIndices) {
      await uploadSingleFile(files[index], index);
    }

    setIsUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeFile = (index: number) => setFiles(prev => prev.filter((_, i) => i !== index));
  const clearCompleted = () => setFiles(prev => prev.filter(f => f.status === 'pending'));

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const pendingCount = files.filter(f => f.status === 'pending').length;
  const completedCount = files.filter(f => f.status !== 'pending').length;

  return (
    <div className="upload-component">
      <div
        className={`upload-area ${isDragOver ? 'drag-over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
        onDragLeave={(e) => { e.preventDefault(); setIsDragOver(false); }}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".docx,.pdf,.jpg,.jpeg,.png"
          onChange={(e) => e.target.files && handleFilesSelect(e.target.files)}
          multiple
          style={{ display: 'none' }}
        />
        <div className="upload-content">
          <div className="upload-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <p className="upload-text">Drag and drop files here, or</p>
          <button className="btn btn-primary" onClick={() => fileInputRef.current?.click()} disabled={isUploading}>
            Browse Files
          </button>
          <p className="upload-hint">Supported: DOCX, PDF, JPG, PNG (Max 10MB)</p>
        </div>
      </div>

      {files.length > 0 && (
        <div className="files-panel">
          <div className="files-header">
            <span className="files-title">Selected Files ({files.length})</span>
            <div className="files-actions">
              {pendingCount > 0 && (
                <button className="btn btn-primary" onClick={handleUploadAll} disabled={isUploading}>
                  {isUploading ? 'Converting...' : `Convert ${pendingCount} File${pendingCount > 1 ? 's' : ''}`}
                </button>
              )}
              {completedCount > 0 && (
                <button className="btn btn-outline" onClick={clearCompleted} disabled={isUploading}>
                  Clear
                </button>
              )}
            </div>
          </div>
          <div className="files-list">
            {files.map((f, index) => (
              <div key={`${f.file.name}-${index}`} className={`file-row ${f.status}`}>
                <div className="file-info">
                  <span className="file-name">{f.file.name}</span>
                  <span className="file-meta">{FORMAT_LABELS[f.inputFormat]} · {formatFileSize(f.file.size)}</span>
                </div>
                {f.status === 'pending' && (
                  <select
                    className="output-select"
                    value={f.selectedConversion}
                    onChange={(e) => handleConversionChange(index, e.target.value as ConversionType)}
                    disabled={isUploading}
                  >
                    {FORMAT_CONVERSIONS[f.inputFormat].map(opt => (
                      <option key={opt.conversionType} value={opt.conversionType}>
                        {opt.outputFormat}
                      </option>
                    ))}
                  </select>
                )}
                {f.status === 'uploading' && (
                  <div className="progress-bar"><div className="progress-fill" style={{ width: `${f.progress}%` }} /></div>
                )}
                {f.status === 'completed' && <span className="status-label success">Done</span>}
                {f.status === 'failed' && <span className="status-label error">Failed</span>}
                {f.status === 'pending' && !isUploading && (
                  <button className="remove-btn" onClick={() => removeFile(index)}>×</button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}
    </div>
  );
};

export default UploadComponent;
