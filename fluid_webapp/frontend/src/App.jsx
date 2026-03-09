import React, { useState } from 'react';
import './App.css';

export default function App() {
  const [events, setEvents] = useState([]);
  const [ticketKey, setTicketKey] = useState('');
  const [repoUrl, setRepoUrl] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [demoDescription, setDemoDescription] = useState('');
  const [demoCode, setDemoCode] = useState('');
  const [demoLoading, setDemoLoading] = useState(false);

  const handleTriggerAutomation = async () => {
    if (!ticketKey || !repoUrl || !description) {
      alert('Please fill all fields');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('http://localhost:8080/api/webhook/trigger-automation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticketKey,
          repoUrl,
          description,
          branch: 'main',
        }),
      });
      const result = await response.json();
      setEvents([{ ...result, createdAt: new Date() }, ...events]);
      setTicketKey('');
      setRepoUrl('');
      setDescription('');
    } catch (error) {
      alert('Error: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDemoGenerate = async () => {
    if (!demoDescription.trim()) {
      alert('Please enter a description');
      return;
    }

    setDemoLoading(true);
    try {
      const response = await fetch('http://localhost:8080/api/webhook/demo/generate-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: demoDescription }),
      });
      const result = await response.json();
      if (result.status === 'success') {
        setDemoCode(result.generatedCode);
      } else {
        alert('Error: ' + result.message);
      }
    } catch (error) {
      alert('Error: ' + error.message);
    } finally {
      setDemoLoading(false);
    }
  };

  return (
    <div className="container">
      <header className="header">
        <h1>🚀 Fluid Webapp - Jira-to-Code Automation</h1>
        <p>Automatically generate and deploy code fixes from Jira tickets</p>
      </header>

      <main className="main">
        <section className="panel demo">
          <h2>🚀 Demo: AI Code Generation</h2>
          <p>Generate code from a ticket description (no external services required)</p>

          <div className="field">
            <label>Ticket Description</label>
            <textarea
              rows={4}
              placeholder="Describe the issue or feature to implement..."
              value={demoDescription}
              onChange={(e) => setDemoDescription(e.target.value)}
            />
          </div>

          <button
            className="primary"
            onClick={handleDemoGenerate}
            disabled={demoLoading}
          >
            {demoLoading ? 'Generating...' : 'Generate Code'}
          </button>

          {demoCode && (
            <div className="code-output">
              <h3>Generated Code:</h3>
              <pre>{demoCode}</pre>
            </div>
          )}
        </section>

        <section className="panel controls">
          <h2>Trigger Automation</h2>

          <div className="field">
            <label>Ticket Key</label>
            <input
              type="text"
              placeholder="e.g., PROJ-123"
              value={ticketKey}
              onChange={(e) => setTicketKey(e.target.value)}
            />
          </div>

          <div className="field">
            <label>Repository URL</label>
            <input
              type="text"
              placeholder="https://github.com/user/repo.git"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
            />
          </div>

          <div className="field">
            <label>Description / Fix Details</label>
            <textarea
              rows={4}
              placeholder="Fix: Update method signature..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <button
            className="primary"
            onClick={handleTriggerAutomation}
            disabled={loading}
          >
            {loading ? 'Processing...' : 'Trigger Automation'}
          </button>
        </section>

        <section className="panel events">
          <h2>Automation History</h2>
          {events.length === 0 ? (
            <p className="empty">No events yet. Trigger an automation to get started.</p>
          ) : (
            <div className="events-list">
              {events.map((event, idx) => (
                <div key={idx} className={`event event-${event.status?.toLowerCase() || 'pending'}`}>
                  <h3>{event.ticketKey || 'Unknown'}</h3>
                  <p>
                    <strong>Status:</strong> {event.status || 'PENDING'}
                  </p>
                  {event.branch && <p><strong>Branch:</strong> {event.branch}</p>}
                  {event.message && <p><strong>Message:</strong> {event.message}</p>}
                  {event.error && <p className="error"><strong>Error:</strong> {event.error}</p>}
                  <small>{new Date(event.createdAt).toLocaleString()}</small>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
