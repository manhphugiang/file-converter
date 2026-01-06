import axios, { AxiosProgressEvent } from 'axios';
import { UploadResponse, JobStatusResponse } from '../types';
import { RetryableApiClient } from '../utils/retry';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  withCredentials: true,  // Send cookies for session tracking
});

// Create retry client for API operations
const retryClient = new RetryableApiClient({
  maxAttempts: 3,
  baseDelay: 1000,
  maxDelay: 5000,
  backoffFactor: 2
});

// Request interceptor for common functionality
apiClient.interceptors.request.use(
  (config) => {
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response?.data?.error) {
      // Return structured error from backend
      return Promise.reject(error.response.data);
    }
    
    // Handle network errors
    if (error.code === 'ECONNABORTED') {
      return Promise.reject({
        error: {
          code: 'TIMEOUT',
          message: 'Request timed out. Please try again.',
          timestamp: new Date().toISOString()
        }
      });
    }
    
    if (!error.response) {
      return Promise.reject({
        error: {
          code: 'NETWORK_ERROR',
          message: 'Unable to connect to server. Please check your connection.',
          timestamp: new Date().toISOString()
        }
      });
    }
    
    return Promise.reject(error);
  }
);

export const uploadFile = async (
  file: File,
  onProgress?: (progress: number) => void,
  conversionType?: string
): Promise<UploadResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  if (conversionType) {
    formData.append('conversion_type', conversionType);
  }

  const response = await apiClient.post<UploadResponse>('/api/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (progressEvent: AxiosProgressEvent) => {
      if (progressEvent.total && onProgress) {
        const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress(progress);
      }
    },
  });

  return response.data;
};

export const getJobStatus = async (jobId: string): Promise<JobStatusResponse> => {
  return retryClient.execute(async () => {
    const response = await apiClient.get<JobStatusResponse>(`/api/status/${jobId}`);
    return response.data;
  }, {
    // Custom retry options for status checks
    maxAttempts: 2,
    baseDelay: 500
  });
};

export const downloadFile = async (jobId: string): Promise<Blob> => {
  return retryClient.execute(async () => {
    const response = await apiClient.get(`/api/download/${jobId}`, {
      responseType: 'blob',
    });
    return response.data;
  }, {
    // Custom retry options for downloads
    maxAttempts: 2,
    baseDelay: 1000
  });
};