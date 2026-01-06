import React, { useState, useEffect, useRef } from 'react';
import './App.css';

const API_URL = process.env.REACT_APP_API_URL || '/monitor';
const MAX_HISTORY = 60; // Keep 60 data points (30 seconds at 0.5s refresh)

function App() {
  const [metrics, setMetrics] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  const fetchMetrics = async () => {
    try {
      const response = await fetch(`${API_URL}/api/metrics`);
      if (!response.ok) throw new Error('Failed to fetch metrics');
      const data = await response.json();
      setMetrics(data);
      setHistory(prev => {
        const newHistory = [...prev, { ...data, time: Date.now() }];
        return newHistory.slice(-MAX_HISTORY);
      });
      setLastUpdate(new Date().toLocaleTimeString());
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 500);
    return () => clearInterval(interval);
  }, []);

  if (loading && !metrics) {
    return <div className="loading">Loading cluster metrics...</div>;
  }

  const totalQueueJobs = Object.values(metrics?.queues || {}).reduce((a, b) => a + b, 0);
  const queueHistory = history.map(h => 
    Object.values(h.queues || {}).reduce((a, b) => a + b, 0)
  );
  const cpuHistory = history.map(h => h.cpu?.cluster_usage_percent || 0);
  const memHistory = history.map(h => h.memory?.percent || 0);

  return (
    <div className="dashboard">
      <header className="header">
        <div className="header-left">
          <h1>File Converter Cluster Monitor</h1>
          <span className="mode-badge">{metrics?.storage?.note || 'Unknown Mode'}</span>
        </div>
        <div className="header-right">
          <span className="update-time">Last update: {lastUpdate}</span>
          {error && <span className="error-badge">{error}</span>}
        </div>
      </header>

      <div className="grid">
        {/* Cluster Overview with Node Details */}
        <div className="card wide">
          <div className="card-header">
            <h2>Cluster Overview</h2>
          </div>
          <div className="cluster-stats">
            <div className="stat-box">
              <span className="stat-number">{metrics?.nodes?.length || 0}</span>
              <span className="stat-label">Nodes</span>
            </div>
            <div className="stat-box">
              <span className="stat-number">{metrics?.pods?.total || 0}</span>
              <span className="stat-label">Running Pods</span>
            </div>
            <div className="stat-box">
              <span className="stat-number">{metrics?.services?.length || 0}</span>
              <span className="stat-label">Services</span>
            </div>
            <div className="stat-box">
              <span className="stat-number">{totalQueueJobs}</span>
              <span className="stat-label">Queued Jobs</span>
            </div>
          </div>
        </div>

        {/* Per-Node Metrics */}
        <div className="card wide">
          <div className="card-header">
            <h2>Node Resources</h2>
            <span className="card-value">Real-time from node-exporter</span>
          </div>
          <div className="nodes-grid">
            {Object.entries(metrics?.node_metrics || {}).map(([nodeIp, nodeData]) => {
              if (!nodeData) return (
                <div key={nodeIp} className="node-card offline">
                  <div className="node-card-header">
                    <span className="node-ip">{nodeIp}</span>
                    <span className="node-status offline">Offline</span>
                  </div>
                </div>
              );
              return (
                <div key={nodeIp} className="node-card">
                  <div className="node-card-header">
                    <span className="node-ip">{nodeIp}</span>
                    <span className="node-status online">Online</span>
                  </div>
                  <div className="node-metrics">
                    <div className="node-metric">
                      <div className="node-metric-header">
                        <span className="node-metric-label">CPU</span>
                        <span className="node-metric-value">{nodeData.cpu_percent}%</span>
                      </div>
                      <div className="node-bar-container">
                        <div 
                          className={`node-bar ${nodeData.cpu_percent > 80 ? 'critical' : nodeData.cpu_percent > 50 ? 'warning' : 'normal'}`}
                          style={{ width: `${nodeData.cpu_percent}%` }} 
                        />
                      </div>
                      <span className="node-metric-detail">{nodeData.cpu_count} cores • Load: {nodeData.load_1m || 0}</span>
                    </div>
                    <div className="node-metric">
                      <div className="node-metric-header">
                        <span className="node-metric-label">Memory</span>
                        <span className="node-metric-value">{nodeData.memory_percent}%</span>
                      </div>
                      <div className="node-bar-container">
                        <div 
                          className={`node-bar ${nodeData.memory_percent > 80 ? 'critical' : nodeData.memory_percent > 50 ? 'warning' : 'normal'}`}
                          style={{ width: `${nodeData.memory_percent}%` }} 
                        />
                      </div>
                      <span className="node-metric-detail">{nodeData.memory_used_gb} / {nodeData.memory_total_gb} GB</span>
                    </div>
                    {nodeData.disk_percent !== undefined && (
                      <div className="node-metric">
                        <div className="node-metric-header">
                          <span className="node-metric-label">Disk</span>
                          <span className="node-metric-value">{nodeData.disk_percent}%</span>
                        </div>
                        <div className="node-bar-container">
                          <div 
                            className={`node-bar ${nodeData.disk_percent > 80 ? 'critical' : nodeData.disk_percent > 50 ? 'warning' : 'normal'}`}
                            style={{ width: `${nodeData.disk_percent}%` }} 
                          />
                        </div>
                        <span className="node-metric-detail">{nodeData.disk_used_gb} / {nodeData.disk_total_gb} GB</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          
          <div className="nodes-table">
            <table>
              <thead>
                <tr>
                  <th>Node</th>
                  <th>Status</th>
                  <th>Pods</th>
                  <th>Distribution</th>
                </tr>
              </thead>
              <tbody>
                {metrics?.nodes?.map((node, i) => {
                  const podCount = metrics?.pods?.by_node?.[node.name] || 0;
                  const totalPods = metrics?.pods?.total || 1;
                  const percentage = Math.round((podCount / totalPods) * 100);
                  return (
                    <tr key={i}>
                      <td className="node-name">{node.name}</td>
                      <td>
                        <span className={`status-badge ${node.status === 'Ready' ? 'ready' : 'not-ready'}`}>
                          {node.status}
                        </span>
                      </td>
                      <td className="pod-count">{podCount}</td>
                      <td>
                        <div className="mini-bar-container">
                          <div className="mini-bar" style={{ width: `${percentage}%` }} />
                          <span className="mini-bar-label">{percentage}%</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Queue Graph */}
        <div className="card">
          <div className="card-header">
            <h2>Queue Activity</h2>
            <span className="card-value">{totalQueueJobs} jobs</span>
          </div>
          <div className="graph-container">
            <MiniGraph data={queueHistory} color="#3b82f6" />
          </div>
          <div className="queue-grid">
            {Object.entries(metrics?.queues || {}).map(([name, count]) => (
              <div key={name} className={`queue-item ${count > 0 ? 'active' : ''}`}>
                <span className="queue-name">{name.replace(/_/g, ' ')}</span>
                <span className="queue-count">{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* CPU Usage */}
        <div className="card">
          <div className="card-header">
            <h2>CPU Usage</h2>
            <span className="card-value">{metrics?.cpu?.cpu_count || 0} cores</span>
          </div>
          <div className="resource-visual">
            <div className="resource-gauge">
              <svg viewBox="0 0 100 50">
                <path d="M 10 45 A 35 35 0 0 1 90 45" fill="none" stroke="#1e293b" strokeWidth="8" strokeLinecap="round" />
                <path 
                  d="M 10 45 A 35 35 0 0 1 90 45" 
                  fill="none" 
                  stroke={metrics?.cpu?.cluster_usage_percent > 80 ? '#ef4444' : metrics?.cpu?.cluster_usage_percent > 50 ? '#f59e0b' : '#22c55e'}
                  strokeWidth="8" 
                  strokeLinecap="round"
                  strokeDasharray={`${(metrics?.cpu?.cluster_usage_percent || 0) * 1.1} 110`}
                />
              </svg>
              <div className="resource-value">
                <span className="resource-number">{metrics?.cpu?.cluster_usage_percent || 0}</span>
                <span className="resource-unit">%</span>
              </div>
            </div>
          </div>
          <div className="graph-container small">
            <MiniGraph data={cpuHistory} color="#22c55e" />
          </div>
        </div>

        {/* RAM Usage */}
        <div className="card">
          <div className="card-header">
            <h2>Memory Usage</h2>
            <span className="card-value">{metrics?.memory?.total_gb || 0} GB total</span>
          </div>
          <div className="resource-visual">
            <div className="resource-gauge">
              <svg viewBox="0 0 100 50">
                <path d="M 10 45 A 35 35 0 0 1 90 45" fill="none" stroke="#1e293b" strokeWidth="8" strokeLinecap="round" />
                <path 
                  d="M 10 45 A 35 35 0 0 1 90 45" 
                  fill="none" 
                  stroke={metrics?.memory?.percent > 80 ? '#ef4444' : metrics?.memory?.percent > 50 ? '#f59e0b' : '#8b5cf6'}
                  strokeWidth="8" 
                  strokeLinecap="round"
                  strokeDasharray={`${(metrics?.memory?.percent || 0) * 1.1} 110`}
                />
              </svg>
              <div className="resource-value">
                <span className="resource-number">{metrics?.memory?.percent || 0}</span>
                <span className="resource-unit">%</span>
              </div>
            </div>
          </div>
          <div className="memory-details">
            <div className="memory-stat">
              <span className="memory-stat-value">{metrics?.memory?.used_gb || 0}</span>
              <span className="memory-stat-label">GB Used</span>
            </div>
            <div className="memory-stat">
              <span className="memory-stat-value">{metrics?.memory?.available_gb || 0}</span>
              <span className="memory-stat-label">GB Free</span>
            </div>
          </div>
          <div className="graph-container small">
            <MiniGraph data={memHistory} color="#8b5cf6" />
          </div>
        </div>

        {/* Services Status */}
        <div className="card">
          <div className="card-header">
            <h2>Services</h2>
            <span className="card-value">{metrics?.services?.length || 0} active</span>
          </div>
          <div className="services-list">
            {metrics?.services?.map((svc, i) => (
              <div key={i} className="service-row">
                <div className="service-info">
                  <span className="service-name">{svc.name}</span>
                  <span className={`status-dot ${svc.status === 'Running' ? 'running' : 'stopped'}`} />
                </div>
                <div className="replica-badges">
                  {[...Array(svc.replicas)].map((_, j) => (
                    <span key={j} className="replica-badge" />
                  ))}
                </div>
                <span className="replica-count">{svc.replicas}</span>
              </div>
            ))}
          </div>
        </div>

        {/* MinIO Storage */}
        <div className="card">
          <div className="card-header">
            <h2>Object Storage</h2>
            <span className="card-value">{metrics?.minio?.bucket}</span>
          </div>
          <div className="storage-visual">
            <div className="storage-ring">
              <svg viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="40" fill="none" stroke="#1e293b" strokeWidth="12" />
                <circle 
                  cx="50" cy="50" r="40" 
                  fill="none" 
                  stroke="#3b82f6" 
                  strokeWidth="12"
                  strokeDasharray={`${Math.min((metrics?.minio?.total_size_gb || 0) * 10, 251)} 251`}
                  strokeLinecap="round"
                  transform="rotate(-90 50 50)"
                />
              </svg>
              <div className="storage-center">
                <span className="storage-value">{metrics?.minio?.total_size_gb || 0}</span>
                <span className="storage-unit">GB</span>
              </div>
            </div>
          </div>
          <div className="storage-details">
            <div className="storage-stat">
              <span className="storage-stat-value">{metrics?.minio?.object_count?.toLocaleString() || 0}</span>
              <span className="storage-stat-label">Objects</span>
            </div>
            <div className="storage-stat">
              <span className="storage-stat-value">{metrics?.minio?.total_size_mb?.toLocaleString() || 0}</span>
              <span className="storage-stat-label">MB Total</span>
            </div>
          </div>
        </div>

        {/* Pods by Deployment - Grid Layout */}
        <div className="card wide">
          <div className="card-header">
            <h2>Pod Distribution</h2>
            <span className="card-value">{metrics?.pods?.total || 0} total pods</span>
          </div>
          <div className="pod-grid">
            {Object.entries(metrics?.pods?.by_deployment || {}).map(([name, count]) => (
              <div key={name} className="pod-card">
                <div className="pod-card-header">
                  <span className="pod-card-name">{name}</span>
                  <span className={`pod-status-indicator ${count > 0 ? 'active' : 'inactive'}`} />
                </div>
                <div className="pod-card-count">{count}</div>
                <div className="pod-card-label">replica{count !== 1 ? 's' : ''}</div>
                <div className="pod-card-dots">
                  {[...Array(Math.min(count, 5))].map((_, j) => (
                    <span key={j} className="pod-dot" />
                  ))}
                  {count > 5 && <span className="pod-more">+{count - 5}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <footer className="footer">
        <span>File Converter K3s Cluster</span>
        <span>Refresh: 500ms</span>
      </footer>
    </div>
  );
}

// Mini sparkline graph component
function MiniGraph({ data, color }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || data.length < 2) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const padding = 4;

    ctx.clearRect(0, 0, width, height);

    const max = Math.max(...data, 1);
    const min = 0;
    const range = max - min || 1;

    const points = data.map((value, i) => ({
      x: padding + (i / (data.length - 1)) * (width - padding * 2),
      y: height - padding - ((value - min) / range) * (height - padding * 2)
    }));

    // Draw area
    ctx.beginPath();
    ctx.moveTo(points[0].x, height - padding);
    points.forEach(p => ctx.lineTo(p.x, p.y));
    ctx.lineTo(points[points.length - 1].x, height - padding);
    ctx.closePath();
    ctx.fillStyle = color + '20';
    ctx.fill();

    // Draw line
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    points.forEach(p => ctx.lineTo(p.x, p.y));
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();

  }, [data, color]);

  return <canvas ref={canvasRef} width={300} height={80} className="mini-graph" />;
}

export default App;
