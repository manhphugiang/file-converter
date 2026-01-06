import React, { useState, useEffect, useCallback } from 'react';
import { ConversionType } from '../types';
import './JobsList.css';

interface Job {
  id: string;
  filename: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  conversion_type: ConversionType;
  original_size: number;
  created_at: string;
  completed_at?: string;
  error_message?: string;
}

interface JobsResponse {
  jobs: Job[];
  total: number;
}

const ITEMS_PER_PAGE = 30;

const CONVERSION_LABELS: Record<string, string> = {
  'docx_to_pdf': 'DOCX → PDF',
  'pdf_to_docx': 'PDF → DOCX',
  'pdf_to_jpg': 'PDF → JPG',
  'pdf_to_png': 'PDF → PNG',
  'jpg_to_pdf': 'JPG → PDF',
  'png_to_pdf': 'PNG → PDF',
  'docx_to_html': 'DOCX → HTML',
  'html_to_pdf': 'HTML → PDF',
  'html_to_docx': 'HTML → DOCX',
  'md_to_html': 'MD → HTML',
  'md_to_pdf': 'MD → PDF',
  'mov_to_mp4': 'MOV → MP4',
  'mp4_to_mov': 'MP4 → MOV',
  'mp4_to_mp3': 'MP4 → MP3',
};

const JobsList: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const offset = (currentPage - 1) * ITEMS_PER_PAGE;
      const response = await fetch(
        `${process.env.REACT_APP_API_URL || 'http://localhost'}/api/session/jobs?limit=${ITEMS_PER_PAGE}&offset=${offset}`,
        { credentials: 'include' }
      );
      if (!response.ok) throw new Error('Failed to fetch jobs');
      const data: JobsResponse = await response.json();
      setJobs(data.jobs);
      setTotal(data.total);
    } catch (err) {
      setError('Failed to load conversion history');
    } finally {
      setIsLoading(false);
    }
  }, [currentPage]);

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, [fetchJobs]);

  const totalPages = Math.ceil(total / ITEMS_PER_PAGE);

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    const completedJobs = jobs.filter(j => j.status === 'completed');
    if (selectedIds.size === completedJobs.length && completedJobs.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(completedJobs.map(j => j.id)));
    }
  };

  const downloadSelected = async () => {
    const ids = Array.from(selectedIds);
    for (let i = 0; i < ids.length; i++) {
      const link = document.createElement('a');
      link.href = `${process.env.REACT_APP_API_URL || 'http://localhost'}/api/download/${ids[i]}`;
      link.download = '';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      // Add delay between downloads to prevent rate limiting and browser issues
      if (i < ids.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 300));
      }
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { 
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' 
    });
  };

  const completedJobs = jobs.filter(j => j.status === 'completed');
  const allCompletedSelected = completedJobs.length > 0 && selectedIds.size === completedJobs.length;

  if (jobs.length === 0 && !isLoading) {
    return (
      <div className="jobs-empty">
        <p>No conversion history yet</p>
        <span>Your converted files will appear here</span>
      </div>
    );
  }

  return (
    <div className="jobs-container">
      <div className="jobs-toolbar">
        <h3 className="jobs-title">Conversion History</h3>
        <div className="toolbar-actions">
          {selectedIds.size > 0 && (
            <button className="btn btn-primary btn-sm" onClick={downloadSelected}>
              Download ({selectedIds.size})
            </button>
          )}
          <button className="btn btn-outline btn-sm" onClick={fetchJobs} disabled={isLoading}>
            Refresh
          </button>
        </div>
      </div>

      {error && <div className="jobs-error">{error}</div>}

      <div className="jobs-table-wrapper">
        <table className="jobs-table">
          <thead>
            <tr>
              <th className="col-checkbox">
                <input
                  type="checkbox"
                  checked={allCompletedSelected}
                  onChange={toggleSelectAll}
                  disabled={completedJobs.length === 0}
                />
              </th>
              <th className="col-name">Name</th>
              <th className="col-format">Format</th>
              <th className="col-size">Size</th>
              <th className="col-date">Created</th>
              <th className="col-status">Status</th>
              <th className="col-action"></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map(job => (
              <tr key={job.id} className={selectedIds.has(job.id) ? 'selected' : ''}>
                <td className="col-checkbox">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(job.id)}
                    onChange={() => toggleSelect(job.id)}
                    disabled={job.status !== 'completed'}
                  />
                </td>
                <td className="col-name">
                  <span className="job-filename" title={job.filename}>{job.filename}</span>
                </td>
                <td className="col-format">
                  <span className="format-badge">{CONVERSION_LABELS[job.conversion_type] || job.conversion_type}</span>
                </td>
                <td className="col-size">{formatSize(job.original_size)}</td>
                <td className="col-date">{formatDate(job.created_at)}</td>
                <td className="col-status">
                  <span className={`status-badge status-${job.status}`}>
                    {job.status === 'completed' ? 'Done' : 
                     job.status === 'processing' ? 'Converting' :
                     job.status === 'pending' ? 'Queued' : 'Failed'}
                  </span>
                </td>
                <td className="col-action">
                  {job.status === 'completed' && (
                    <a 
                      href={`${process.env.REACT_APP_API_URL || 'http://localhost'}/api/download/${job.id}`}
                      className="download-link"
                      download
                    >
                      Download
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          <button
            className="page-btn"
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
          >
            Previous
          </button>
          <span className="page-info">
            Page {currentPage} of {totalPages}
          </span>
          <button
            className="page-btn"
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};

export default JobsList;
