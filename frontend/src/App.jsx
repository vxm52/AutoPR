import { useState, useEffect, useRef } from 'react'
import './App.css'

// ── Icons ──────────────────────────────────────────────────────────────────

function GitBranchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="6" y1="3" x2="6" y2="15" />
      <circle cx="18" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M18 9a9 9 0 0 1-9 9" />
    </svg>
  )
}

function ExternalLinkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  )
}

function ArrowLeftIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
    </svg>
  )
}

// ── Navbar ─────────────────────────────────────────────────────────────────

function Navbar() {
  return (
    <nav className="navbar">
      <span className="navbar-logo">
        <GitBranchIcon />
        AutoPR
      </span>
    </nav>
  )
}

// ── Status badge ───────────────────────────────────────────────────────────

const STATUS_LABEL = {
  pending: 'Pending',
  running: 'Running',
  done:    'Complete',
  failed:  'Failed',
}

function StatusBadge({ status }) {
  return (
    <span className={`badge badge-${status}`}>
      <span className="badge-dot" />
      {STATUS_LABEL[status] ?? status}
    </span>
  )
}

// ── Step log ───────────────────────────────────────────────────────────────

function classifyLine(line) {
  const u = line.toUpperCase()
  if (u.startsWith('OK'))   return 'ok'
  if (u.startsWith('WARN')) return 'warn'
  if (u.startsWith('ERR'))  return 'err'
  return 'info'
}

function LogLine({ line, index }) {
  const kind = classifyLine(line)
  const spaceIdx = line.indexOf(' ')
  const prefix = spaceIdx > -1 ? line.slice(0, spaceIdx) : line
  const rest   = spaceIdx > -1 ? line.slice(spaceIdx + 1) : ''

  return (
    <div
      className={`log-line log-${kind}`}
      style={{ animationDelay: `${index * 40}ms` }}
    >
      <span className="log-prefix">{prefix}</span>
      <span className="log-msg">{rest}</span>
    </div>
  )
}

function LogBlock({ lines }) {
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  return (
    <div className="log-block">
      <div className="log-titlebar">
        <span className="log-dot" />
        <span className="log-dot" />
        <span className="log-dot" />
        <span className="log-title">step log</span>
      </div>
      <div className="log-body">
        {lines.length === 0
          ? <span className="log-empty">Waiting for pipeline to start…</span>
          : lines.map((line, i) => <LogLine key={i} line={line} index={i} />)
        }
        <div ref={endRef} />
      </div>
    </div>
  )
}

// ── Home page ──────────────────────────────────────────────────────────────

function HomePage({ onRunStarted }) {
  const [repo, setRepo]               = useState('')
  const [issueNumber, setIssueNumber] = useState('')
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    if (!repo.includes('/')) {
      setError('Repo must be in owner/name format')
      return
    }
    const num = parseInt(issueNumber, 10)
    if (!num || num < 1) {
      setError('Issue number must be a positive integer')
      return
    }

    setLoading(true)
    try {
      const res = await fetch('/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo, issue_number: num }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? `Server error ${res.status}`)
      }
      const data = await res.json()
      onRunStarted(data.run_id, repo, num)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="page">
      <div className="home-card">
        <header className="home-header">
          <h1>AutoPR</h1>
          <p>
            Point it at a GitHub issue.<br />
            Get a pull request back.
          </p>
        </header>

        <form className="form" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="repo">Repository</label>
            <input
              id="repo"
              type="text"
              placeholder="owner/repo"
              value={repo}
              onChange={e => setRepo(e.target.value)}
              disabled={loading}
              autoFocus
              autoComplete="off"
              spellCheck={false}
            />
          </div>

          <div className="field">
            <label htmlFor="issue">Issue number</label>
            <input
              id="issue"
              type="number"
              placeholder="42"
              min="1"
              value={issueNumber}
              onChange={e => setIssueNumber(e.target.value)}
              disabled={loading}
            />
          </div>

          {error && <p className="form-error">{error}</p>}

          <button className="btn-primary" type="submit" disabled={loading || !repo || !issueNumber}>
            {loading ? 'Starting…' : 'Run AutoPR →'}
          </button>
        </form>
      </div>
    </main>
  )
}

// ── Status page ────────────────────────────────────────────────────────────

function StatusPage({ runId, repo, issueNumber, onBack }) {
  const [run, setRun] = useState({ status: 'pending', step_log: [], errors: [], pr_url: null })
  const intervalRef = useRef(null)

  useEffect(() => {
    async function poll() {
      try {
        const res = await fetch(`/status/${runId}`)
        if (!res.ok) return
        const data = await res.json()
        setRun(data)
        if (data.status === 'done' || data.status === 'failed') {
          clearInterval(intervalRef.current)
        }
      } catch (_) {}
    }

    poll()
    intervalRef.current = setInterval(poll, 2000)
    return () => clearInterval(intervalRef.current)
  }, [runId])

  const isDone   = run.status === 'done'
  const isFailed = run.status === 'failed'
  const isSettled = isDone || isFailed

  return (
    <main className="page">
      <div className="status-card">
        <div className="status-header">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <h2>{repo} #{issueNumber}</h2>
            <StatusBadge status={run.status} />
          </div>
          <p className="status-meta">run/{runId}</p>
        </div>

        <div className="divider" />

        <LogBlock lines={run.step_log} />

        {isFailed && run.errors.length > 0 && (
          <div className="errors-block">
            <p className="errors-title">Errors</p>
            {run.errors.map((e, i) => (
              <p key={i} className="errors-msg">{e}</p>
            ))}
          </div>
        )}

        {isDone && run.pr_url && (
          <a className="pr-cta" href={run.pr_url} target="_blank" rel="noopener noreferrer">
            View Pull Request <ExternalLinkIcon />
          </a>
        )}

        {isSettled && (
          <button className="back-link" onClick={onBack}>
            <ArrowLeftIcon /> Run another issue
          </button>
        )}
      </div>
    </main>
  )
}

// ── App shell ──────────────────────────────────────────────────────────────

export default function App() {
  const [view, setView]   = useState('home')    // 'home' | 'status'
  const [runId, setRunId] = useState(null)
  const [repo, setRepo]   = useState('')
  const [issue, setIssue] = useState(null)

  function handleRunStarted(id, r, n) {
    setRunId(id)
    setRepo(r)
    setIssue(n)
    setView('status')
  }

  return (
    <>
      <Navbar />
      {view === 'home'
        ? <HomePage onRunStarted={handleRunStarted} />
        : <StatusPage
            runId={runId}
            repo={repo}
            issueNumber={issue}
            onBack={() => setView('home')}
          />
      }
    </>
  )
}
