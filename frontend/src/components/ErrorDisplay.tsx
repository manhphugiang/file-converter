import React from 'react';
import { ApiError } from '../types';
import './ErrorDisplay.css';

interface ErrorDisplayProps {
  error: ApiError | string | null;
  onRetry?: () => void;
  onDismiss?: () => void;
  showRetry?: boolean;
  className?: string;
}

interface ErrorSuggestion {
  message: string;
  action?: string;
}

const ErrorDisplay: React.FC<ErrorDisplayProps> = ({
  error,
  onRetry,
  onDismiss,
  showRetry = false,
  className = ''
}) => {
  if (!error) return null;

  // Parse error message and code
  let errorMessage: string;
  let errorCode: string | undefined;
  let errorDetails: string | undefined;
  
  if (typeof error === 'string') {
    errorMessage = error;
  } else {
    errorMessage = error.error?.message || 'An unexpected error occurred';
    errorCode = error.error?.code;
    errorDetails = error.error?.details;
  }

  // Get user-friendly suggestions based on error code
  const getErrorSuggestions = (code?: string): ErrorSuggestion[] => {
    switch (code) {
      case 'INVALID_FILE_TYPE':
        return [
          { message: 'Please select a valid DOCX file' },
          { message: 'Supported formats: .docx files only' }
        ];
      
      case 'FILE_TOO_LARGE':
        return [
          { message: 'Try compressing your document' },
          { message: 'Remove large images or media from the document' },
          { message: 'Split large documents into smaller files' }
        ];
      
      case 'EMPTY_FILE':
        return [
          { message: 'Please select a file with content' },
          { message: 'Check that the file is not corrupted' }
        ];
      
      case 'NETWORK_ERROR':
        return [
          { message: 'Check your internet connection' },
          { message: 'Try again in a few moments', action: 'retry' }
        ];
      
      case 'TIMEOUT':
        return [
          { message: 'The request took too long to complete' },
          { message: 'Try uploading a smaller file' },
          { message: 'Check your internet connection and try again', action: 'retry' }
        ];
      
      case 'SERVICE_UNAVAILABLE':
      case 'INTERNAL_SERVER_ERROR':
        return [
          { message: 'The service is temporarily unavailable' },
          { message: 'Please try again in a few minutes', action: 'retry' }
        ];
      
      case 'JOB_NOT_FOUND':
        return [
          { message: 'The conversion job could not be found' },
          { message: 'It may have expired or been removed' },
          { message: 'Try uploading the file again' }
        ];
      
      case 'CONVERSION_FAILED':
        return [
          { message: 'The document could not be converted' },
          { message: 'Check that the DOCX file is not corrupted' },
          { message: 'Try saving the document in a newer format' }
        ];
      
      default:
        return [
          { message: 'Please try again' },
          { message: 'If the problem persists, contact support' }
        ];
    }
  };

  const suggestions = getErrorSuggestions(errorCode);
  const hasRetryAction = suggestions.some(s => s.action === 'retry') || showRetry;

  return (
    <div className={`error-display ${className}`}>
      <div className="error-content">
        <div className="error-header">
          <span className="error-icon">⚠️</span>
          <div className="error-text">
            <h4 className="error-title">
              {errorCode ? getErrorTitle(errorCode) : 'Error'}
            </h4>
            <p className="error-message">{errorMessage}</p>
          </div>
          {onDismiss && (
            <button 
              className="error-dismiss"
              onClick={onDismiss}
              aria-label="Dismiss error"
            >
              ✕
            </button>
          )}
        </div>
        
        {errorDetails && (
          <div className="error-details">
            <p>{errorDetails}</p>
          </div>
        )}
        
        {suggestions.length > 0 && (
          <div className="error-suggestions">
            <h5>What you can do:</h5>
            <ul>
              {suggestions.map((suggestion, index) => (
                <li key={index}>{suggestion.message}</li>
              ))}
            </ul>
          </div>
        )}
        
        {hasRetryAction && onRetry && (
          <div className="error-actions">
            <button 
              className="retry-button"
              onClick={onRetry}
            >
              Try Again
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

function getErrorTitle(errorCode: string): string {
  switch (errorCode) {
    case 'INVALID_FILE_TYPE':
      return 'Invalid File Type';
    case 'FILE_TOO_LARGE':
      return 'File Too Large';
    case 'EMPTY_FILE':
      return 'Empty File';
    case 'NETWORK_ERROR':
      return 'Connection Error';
    case 'TIMEOUT':
      return 'Request Timeout';
    case 'SERVICE_UNAVAILABLE':
      return 'Service Unavailable';
    case 'INTERNAL_SERVER_ERROR':
      return 'Server Error';
    case 'JOB_NOT_FOUND':
      return 'Job Not Found';
    case 'CONVERSION_FAILED':
      return 'Conversion Failed';
    default:
      return 'Error';
  }
}

export default ErrorDisplay;