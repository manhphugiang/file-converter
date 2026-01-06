import React, { useState } from 'react';
import { downloadFile } from '../services/api';
import { ApiError } from '../types';
import './DownloadHandler.css';

interface DownloadHandlerProps {
  jobId: string;
  filename: string;
  onDownloadComplete?: () => void;
  className?: string;
}

interface DownloadState {
  isDownloading: boolean;
  downloadProgress: number;
  error: string | null;
  isCompleted: boolean;
}

const DownloadHandler: React.FC<DownloadHandlerProps> = ({
  jobId,
  filename,
  onDownloadComplete,
  className = ''
}) => {
  const [state, setState] = useState<DownloadState>({
    isDownloading: false,
    downloadProgress: 0,
    error: null,
    isCompleted: false
  });

  const generatePdfFilename = (originalFilename: string): string => {
    // Remove .docx extension and add .pdf
    const nameWithoutExt = originalFilename.replace(/\.docx?$/i, '');
    return `${nameWithoutExt}.pdf`;
  };

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  };

  const handleDownload = async () => {
    setState(prev => ({
      ...prev,
      isDownloading: true,
      downloadProgress: 0,
      error: null,
      isCompleted: false
    }));

    try {
      // Start progress simulation since we can't track actual download progress with blob response
      const progressInterval = setInterval(() => {
        setState(prev => {
          if (prev.downloadProgress < 90) {
            return { ...prev, downloadProgress: prev.downloadProgress + 10 };
          }
          return prev;
        });
      }, 200);

      const blob = await downloadFile(jobId);
      
      // Clear progress interval and set to 100%
      clearInterval(progressInterval);
      setState(prev => ({ ...prev, downloadProgress: 100 }));

      // Validate that we received a PDF blob
      if (blob.type !== 'application/pdf' && blob.size === 0) {
        throw new Error('Invalid PDF file received');
      }

      // Generate appropriate filename
      const pdfFilename = generatePdfFilename(filename);
      
      // Trigger download
      downloadBlob(blob, pdfFilename);

      setState(prev => ({
        ...prev,
        isDownloading: false,
        isCompleted: true,
        error: null
      }));

      // Call completion callback
      if (onDownloadComplete) {
        onDownloadComplete();
      }

      // Reset completed state after a delay
      setTimeout(() => {
        setState(prev => ({ ...prev, isCompleted: false }));
      }, 3000);

    } catch (error) {
      const apiError = error as ApiError;
      let errorMessage = 'Download failed. Please try again.';
      
      if (apiError.error?.code === 'JOB_NOT_FOUND') {
        errorMessage = 'File not found. It may have been deleted or expired.';
      } else if (apiError.error?.code === 'FILE_NOT_READY') {
        errorMessage = 'File is not ready for download yet. Please wait for conversion to complete.';
      } else if (apiError.error?.message) {
        errorMessage = apiError.error.message;
      }

      setState(prev => ({
        ...prev,
        isDownloading: false,
        downloadProgress: 0,
        error: errorMessage,
        isCompleted: false
      }));
    }
  };

  const handleRetry = () => {
    setState(prev => ({ ...prev, error: null }));
    handleDownload();
  };

  return (
    <div className={`download-handler ${className}`}>
      {!state.isDownloading && !state.isCompleted && !state.error && (
        <button
          type="button"
          className="download-button"
          onClick={handleDownload}
        >
          📥 Download PDF
        </button>
      )}

      {state.isDownloading && (
        <div className="download-progress">
          <div className="progress-info">
            <span className="download-icon">📥</span>
            <div className="progress-details">
              <p className="progress-text">Downloading {generatePdfFilename(filename)}...</p>
              <p className="progress-percentage">{state.downloadProgress}%</p>
            </div>
          </div>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${state.downloadProgress}%` }}
            />
          </div>
        </div>
      )}

      {state.isCompleted && (
        <div className="download-success">
          <span className="success-icon">✅</span>
          <span className="success-text">Download completed!</span>
        </div>
      )}

      {state.error && (
        <div className="download-error">
          <div className="error-content">
            <span className="error-icon">⚠️</span>
            <span className="error-text">{state.error}</span>
          </div>
          <button
            type="button"
            className="retry-button"
            onClick={handleRetry}
          >
            🔄 Retry
          </button>
        </div>
      )}
    </div>
  );
};

export default DownloadHandler;