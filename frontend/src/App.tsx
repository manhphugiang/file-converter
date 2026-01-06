import React, { Component, ErrorInfo, ReactNode, useState } from 'react';
import UploadComponent from './components/UploadComponent';
import JobsList from './components/JobsList';
import Header from './components/Header';
import Footer from './components/Footer';
import './App.css';

// Error Boundary
interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <div className="error-content">
            <h2>Something went wrong</h2>
            <p>Please try refreshing the page.</p>
            <button onClick={() => window.location.reload()} className="btn btn-primary">
              Refresh Page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  const [refreshKey, setRefreshKey] = useState(0);

  const handleUploadComplete = () => {
    setRefreshKey(prev => prev + 1);
  };

  const scrollToSection = (e: React.MouseEvent<HTMLAnchorElement>, id: string) => {
    e.preventDefault();
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <ErrorBoundary>
      <div className="app">
        <Header />
        <main className="main-content">
          <div className="container">
            <section className="hero-section">
              <h1>Convert Your Files</h1>
              <p className="hero-subtitle">
                Fast, secure, and free file conversion. Support for documents, images, and videos.
              </p>
            </section>
            
            <section id="upload-section" className="upload-section">
              <UploadComponent onUploadComplete={handleUploadComplete} />
            </section>
            
            <section className="jobs-section">
              <JobsList key={refreshKey} />
            </section>

            <section id="features" className="features-section">
              <h2>Features</h2>
              <div className="features-grid">
                <div className="feature-card">
                  <h3>Tech Stack</h3>
                  <p>My local Raspberry pi cluster that scale with Kubernetes, Docker, Redis, Minio, PostgreSQL</p>
                </div>
                <div className="feature-card">
                  <h3>Image and Docx Processing</h3>
                  <p>I used Pandoc to convert </p>
                </div>
                <div className="feature-card">
                  <h3>Video Conversion</h3>
                  <p>Convert with FFmpeg</p>
                </div>
                <div className="feature-card">
                  <h3>Markdown Support</h3>
                  <p>Convert Markdown files to PDF or HTML documents</p>
                </div>
              </div>
            </section>

            <section id="formats" className="formats-section">
              <h2>Supported Formats</h2>
              <div className="formats-grid">
                <div className="format-category">
                  <h3>Documents</h3>
                  <ul>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>DOCX → PDF</a></li>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>PDF → DOCX</a></li>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>DOCX → HTML</a></li>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>HTML → PDF</a></li>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>HTML → DOCX</a></li>
                  </ul>
                </div>
                <div className="format-category">
                  <h3>Images</h3>
                  <ul>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>PDF → JPG</a></li>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>PDF → PNG</a></li>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>JPG → PDF</a></li>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>PNG → PDF</a></li>
                  </ul>
                </div>
                <div className="format-category">
                  <h3>Video & Audio</h3>
                  <ul>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>MOV → MP4</a></li>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>MP4 → MOV</a></li>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>MP4 → MP3</a></li>
                  </ul>
                </div>
                <div className="format-category">
                  <h3>Markdown</h3>
                  <ul>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>MD → PDF</a></li>
                    <li><a href="#upload-section" onClick={(e) => scrollToSection(e, 'upload-section')}>MD → HTML</a></li>
                  </ul>
                </div>
              </div>
            </section>

            <section id="faq" className="faq-section">
              <h2>FAQ</h2>
              <div className="faq-list">
                <div className="faq-item">
                  <h3>What's the maximum file size?</h3>
                  <p>Documents and images: 10MB. Videos: 100MB.</p>
                </div>
                <div className="faq-item">
                  <h3>How long are files stored?</h3>
                  <p>Converted files are stored in my local cluster - don't worry, this is a small project and I don't have resources to keep the file anyway</p>
                </div>
                <div className="faq-item">
                  <h3>Is my data secure?</h3>
                  <p>Yes, all files are processed and tag with your sessions ID, will be deleted after 24 hours.</p>
                </div>
              </div>
            </section>
          </div>
        </main>
        <Footer />
      </div>
    </ErrorBoundary>
  );
}

export default App;
