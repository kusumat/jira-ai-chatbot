import React, { useEffect, useMemo, useState } from "react";

const defaultIndexDir = "";
const P1_INTENT_REGEX = /\bp1\b|\bpriority\s*1\b|\bpriority\s*one\b/i;
const EXEC_SUMMARY_REGEX = /executive summary/i;

const quickPrompts = [
  "Why was Sprint 24 delayed?",
  "Any P1?",
  "What changed in last sprint?",
  "Top blockers from comments",
];

export default function App() {
  const [apiBase, setApiBase] = useState("http://127.0.0.1:8000");
  const [indexDir, setIndexDir] = useState(defaultIndexDir);
  const [question, setQuestion] = useState("Why was Sprint 24 delayed?");
  const [project, setProject] = useState("KAN");
  const [llmProvider, setLlmProvider] = useState("none");
  const [p1Only, setP1Only] = useState(false);
  const [executiveMode, setExecutiveMode] = useState(true);
  const [loading, setLoading] = useState(false);
  const [loadingIndex, setLoadingIndex] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const buildQuestion = () => {
    let q = question.trim();
    if (p1Only && !P1_INTENT_REGEX.test(q)) {
      q = `${q} Any P1?`;
    }
    if (executiveMode && !EXEC_SUMMARY_REGEX.test(q)) {
      q = `${q} executive summary`;
    }
    return q.trim();
  };

  const canAsk = useMemo(() => question.trim().length > 1 && indexDir.trim().length > 0, [question, indexDir]);
  const effectiveQuestionPreview = useMemo(() => buildQuestion(), [question, p1Only, executiveMode]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", "dark");
  }, []);

  useEffect(() => {
    const loadLatestIndex = async () => {
      setLoadingIndex(true);
      try {
        const response = await fetch(`${apiBase}/index/latest`);
        const payload = await response.json();
        if (response.ok && payload.index_dir) {
          setIndexDir(payload.index_dir);
        }
      } catch (_e) {
      } finally {
        setLoadingIndex(false);
      }
    };
    loadLatestIndex();
  }, [apiBase]);

  const onAsk = async () => {
    if (!canAsk) return;
    setLoading(true);
    setError("");
    setResult(null);
    const effectiveQuestion = buildQuestion();
    try {
      const response = await fetch(`${apiBase}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: effectiveQuestion,
          index_dir: indexDir,
          project,
          llm_provider: llmProvider,
          chunk_types: ["issue", "comment", "changelog"],
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Failed to get answer");
      }
      setResult(payload);
    } catch (e) {
      setError(e.message || "Unexpected error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="shell flux">
      <div className="bgOrb orb1" />
      <div className="bgOrb orb2" />
      <div className="bgOrb orb3" />
      <header className="hero">
        <div>
          <p className="kicker">Jira AI Copilot</p>
          <h1>Ask your sprint. Get instant insight.</h1>
          <p className="sub">React UI → FastAPI backend → chatbot_cli retrieval engine</p>
        </div>
      </header>

      <main className="layout">
        <section className="panel controls">
          <h2>Ask</h2>

          <div className="field">
            <label>Question</label>
            <textarea rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} />
          </div>

          <div className="chips">
            {quickPrompts.map((prompt) => (
              <button key={prompt} type="button" className="chip" onClick={() => setQuestion(prompt)}>
                {prompt}
              </button>
            ))}
          </div>

          <div className="toggles">
            <button
              type="button"
              className={`toggle ${p1Only ? "active" : ""}`}
              onClick={() => setP1Only((prev) => !prev)}
              aria-pressed={p1Only}
            >
              P1 only
            </button>
            <button
              type="button"
              className={`toggle ${executiveMode ? "active" : ""}`}
              onClick={() => setExecutiveMode((prev) => !prev)}
              aria-pressed={executiveMode}
            >
              Executive summary
            </button>
          </div>

          <div className="questionPreview">
            <span>Effective query</span>
            <p>{effectiveQuestionPreview}</p>
          </div>

          <div className="grid2">
            <div className="field">
              <label>Project</label>
              <input value={project} onChange={(e) => setProject(e.target.value)} />
            </div>
            <div className="field">
              <label>LLM</label>
              <select value={llmProvider} onChange={(e) => setLlmProvider(e.target.value)}>
                <option value="none">none (extractive)</option>
                <option value="openai">openai</option>
                <option value="claude">claude</option>
              </select>
            </div>
          </div>

          <div className="field">
            <label>API Base URL</label>
            <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} />
          </div>

          <div className="field">
            <label>Index Directory</label>
            <input value={indexDir} onChange={(e) => setIndexDir(e.target.value)} />
            {loadingIndex && <small>Resolving latest index...</small>}
          </div>

          <button className="primary" disabled={!canAsk || loading} onClick={onAsk}>
            {loading ? "Analyzing Jira..." : "Ask Jira Copilot"}
          </button>

          {error && <div className="error">{error}</div>}
        </section>

        <section className="panel answer">
          <h2>Response</h2>
          {!result && <p className="empty">Ask a question to see summary, citations, and retrieval evidence.</p>}

          {result && (
            <>
              <div className="statsRow">
                <div className="statPill">Citations: {result.citations?.length || 0}</div>
                <div className="statPill">Evidence rows: {result.retrieval?.length || 0}</div>
                <div className="statPill">Mode: {llmProvider}</div>
              </div>

              <div className="answerBlock">
                <h3>Answer</h3>
                <pre>{result.answer}</pre>
              </div>

              <div className="answerBlock">
                <h3>Citations</h3>
                {result.citations?.length ? (
                  <div className="citationWrap">
                    {result.citations.map((citation) => (
                      <span key={citation} className="citationPill">
                        {citation}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p>None</p>
                )}
              </div>

              <div className="answerBlock">
                <h3>Index Used</h3>
                <p>{result.index_dir_used || indexDir}</p>
              </div>

              <details className="answerBlock">
                <summary>Retrieval details</summary>
                <pre>{JSON.stringify(result.retrieval, null, 2)}</pre>
              </details>
            </>
          )}
        </section>
      </main>
    </div>
  );
}
