export type ConversionType = 
  | 'docx_to_pdf' | 'pdf_to_docx'
  | 'pdf_to_jpg' | 'pdf_to_png'
  | 'jpg_to_pdf' | 'png_to_pdf'
  | 'docx_to_html' | 'html_to_pdf' | 'html_to_docx'
  | 'md_to_html' | 'md_to_pdf';

export interface Job {
  id: string;
  filename: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  conversionType?: ConversionType;
  createdAt: string;
  completedAt?: string;
  errorMessage?: string;
}

export interface UploadResponse {
  job_id: string;
  status: string;
  message: string;
  conversion_type?: ConversionType;
}

export interface JobStatusResponse {
  job_id: string;
  filename: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  conversion_type?: ConversionType;
  created_at: string;
  completed_at?: string;
  error_message?: string;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: string;
    job_id?: string;
    timestamp: string;
  };
}
