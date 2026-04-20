import { useState, useEffect, useRef } from 'react'
import './App.css'

// ─── Pipeline metadata ────────────────────────────────────────────────────────

const PIPELINE_STEPS = [
  { id: 'issue_parser',   label: 'Issue Parser',    desc: 'Classifies issue as bug fix, feature, or refactor' },
  { id: 'repo_indexer',   label: 'Repo Indexer',    desc: 'Builds a FAISS semantic index of the codebase' },
  { id: 'retriever',      label: 'Retriever',       desc: 'Retrieves the most relevant code chunks' },
  { id: 'planner',        label: 'Planner',         desc: 'Produces a structured JSON change plan via LLM' },
  { id: 'code_generator', label: 'Code Generator',  desc: 'Applies changes file-by-file via LLM' },
  { id: 'diff_generator', label: 'Diff Generator',  desc: 'Computes unified diffs with dry-run validation' },
  { id: 'pr_creator',     label: 'PR Creator',      desc: 'Commits, pushes, and opens a GitHub pull request' },
]

// ─── Utilities ────────────────────────────────────────────────────────────────

function parseStepStates(stepLog, pipelineStatus) {
  const states = {}
  const warned = new Set()

  for (const line of stepLog) {
    const u = line.toUpperCase()
    for (const step of PIPELINE_STEPS) {
      if (!line.includes(step.id)) continue
      if (u.startsWith('OK')) {
        // Green wins on completion; amber overlay if there were earlier warnings.
        states[step.id] = warned.has(step.id) ? 'ok-warn' : 'ok'
        break
      }
      if (u.startsWith('WARN')) {
        warned.add(step.id)
        // Only downgrade to amber if not already settled green.
        if (states[step.id] !== 'ok' && states[step.id] !== 'ok-warn') states[step.id] = 'warn'
        break
      }
      if (u.startsWith('ERR')) { states[step.id] = 'err'; break }
    }
  }

  if (pipelineStatus === 'running' || pipelineStatus === 'pending') {
    for (const step of PIPELINE_STEPS) {
      if (!states[step.id]) { states[step.id] = 'active'; break }
    }
  }
  return states
}

function countDone(states) {
  return PIPELINE_STEPS.filter(s => ['ok', 'ok-warn', 'warn'].includes(states[s.id])).length
}

// ─── Icons ────────────────────────────────────────────────────────────────────

const IconCheck = () => (
  <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="2 6 5 9 10 3"/>
  </svg>
)
const IconX = () => (
  <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <line x1="3" y1="3" x2="9" y2="9"/><line x1="9" y1="3" x2="3" y2="9"/>
  </svg>
)
const IconBranch = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="6" y1="3" x2="6" y2="15"/>
    <circle cx="18" cy="6" r="3"/>
    <circle cx="6" cy="18" r="3"/>
    <path d="M18 9a9 9 0 0 1-9 9"/>
  </svg>
)
const IconExternal = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
    <polyline points="15 3 21 3 21 9"/>
    <line x1="10" y1="14" x2="21" y2="3"/>
  </svg>
)
const IconArrowLeft = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="19" y1="12" x2="5" y2="12"/>
    <polyline points="12 19 5 12 12 5"/>
  </svg>
)
const IconChevron = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="9 18 15 12 9 6"/>
  </svg>
)

// ─── Navbar ───────────────────────────────────────────────────────────────────

function Navbar() {
  return (
    <nav className="navbar">
      <span className="navbar-logo"><IconBranch />AutoPR</span>
    </nav>
  )
}

// ─── Progress bar ─────────────────────────────────────────────────────────────

function ProgressBar({ states, status }) {
  const done = countDone(states)
  const pct  = status === 'done' ? 100 : (done / PIPELINE_STEPS.length) * 100
  const indeterminate = (status === 'running' || status === 'pending') && done === 0

  return (
    <div className="progress-bar">
      {indeterminate
        ? <div className="progress-indeterminate" />
        : <div
            className={`progress-fill ${status === 'failed' ? 'progress-fill-failed' : ''}`}
            style={{ width: `${pct}%` }}
          />
      }
    </div>
  )
}

// ─── Pipeline visualizer ─────────────────────────────────────────────────────

function PipelineDot({ state }) {
  return (
    <div className={`pip-dot pip-dot-${state}`}>
      {(state === 'ok' || state === 'ok-warn') && <IconCheck />}
      {state === 'err' && <IconX />}
      {state === 'ok-warn' && <span className="pip-warn-dot" />}
    </div>
  )
}

function PipelineVisualizer({ stepLog, status }) {
  const states = parseStepStates(stepLog, status)

  return (
    <div className="pip-block">
      <div className="block-titlebar">
        <span className="titlebar-dot" /><span className="titlebar-dot" /><span className="titlebar-dot" />
        <span className="block-title">pipeline</span>
      </div>
      <div className="pip-body">
        {PIPELINE_STEPS.map((step, i) => {
          const state   = states[step.id] || 'idle'
          const isLast  = i === PIPELINE_STEPS.length - 1
          const lineFilled = !!states[PIPELINE_STEPS[i + 1]?.id]

          return (
            <div key={step.id} className="pip-step">
              <div className="pip-track">
                <PipelineDot state={state} />
                {!isLast && <div className={`pip-line ${lineFilled ? 'pip-line-on' : ''}`} />}
              </div>
              <div className={`pip-info ${state === 'active' ? 'pip-info-active' : ''}`}>
                <span className={`pip-label pip-label-${state === 'ok-warn' ? 'ok' : state}`}>{step.label}</span>
                <span className="pip-desc">{step.desc}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Issue preview ────────────────────────────────────────────────────────────

function IssuePreview({ repo, issueNumber }) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  useEffect(() => {
    setData(null); setError(null)
    if (!repo.includes('/') || !issueNumber) return

    const [owner, name] = repo.split('/', 2)
    const num = parseInt(issueNumber, 10)
    if (!name || !num || num < 1) return

    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const res = await fetch(`https://api.github.com/repos/${owner}/${name}/issues/${num}`)
        if (res.status === 404) throw new Error('Issue not found')
        if (res.status === 403) throw new Error('GitHub API rate limit — try again shortly')
        if (!res.ok) throw new Error(`GitHub returned ${res.status}`)
        setData(await res.json())
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }, 650)

    return () => clearTimeout(t)
  }, [repo, issueNumber])

  if (!repo.includes('/') || !issueNumber) return null

  if (loading) return (
    <div className="issue-card issue-card-loading">
      <div className="skeleton" />
      <div className="skeleton skeleton-sm" />
    </div>
  )

  if (error) return (
    <div className="issue-card issue-card-error">
      <span className="error-dot" />{error}
    </div>
  )

  if (!data) return null

  return (
    <div className="issue-card">
      <div className="issue-meta-row">
        <span className="issue-num">#{data.number}</span>
        <span className={`issue-state ${data.state === 'open' ? 'state-open' : 'state-closed'}`}>
          {data.state}
        </span>
        {data.labels?.slice(0, 3).map(l => (
          <span key={l.id} className="issue-lbl"
            style={{ background: `#${l.color}22`, color: `#${l.color}`, borderColor: `#${l.color}44` }}>
            {l.name}
          </span>
        ))}
      </div>
      <p className="issue-title">{data.title}</p>
      {data.body && (
        <p className="issue-body">
          {data.body.slice(0, 300)}{data.body.length > 300 ? '…' : ''}
        </p>
      )}
    </div>
  )
}

// ─── Diff viewer ──────────────────────────────────────────────────────────────

function parseDiff(raw) {
  const lines  = raw.split('\n')
  let toFile   = 'unknown'
  const hunks  = []
  let cur      = null

  for (const ln of lines) {
    if (ln.startsWith('+++ '))      { toFile = ln.slice(4).replace(/^b\//, ''); continue }
    if (ln.startsWith('--- '))      { continue }
    if (ln.startsWith('@@'))        { cur = { header: ln, lines: [] }; hunks.push(cur); continue }
    if (cur && ln.length > 0)       cur.lines.push(ln)
  }
  return { toFile, hunks }
}

function DiffViewer({ diffs }) {
  const [open, setOpen] = useState(true)
  if (!diffs?.length) return null

  const parsed = diffs.map(parseDiff).filter(d => d.hunks.length)
  if (!parsed.length) return null

  return (
    <div className="diff-wrap">
      <button className="diff-toggle" onClick={() => setOpen(o => !o)}>
        <span>Changed files <span className="diff-count">{parsed.length}</span></span>
        <span className={`diff-chevron ${open ? 'diff-chevron-open' : ''}`}><IconChevron /></span>
      </button>

      {open && parsed.map((file, fi) => (
        <div key={fi} className="diff-file">
          <div className="diff-file-hd">
            <span className="diff-fname">{file.toFile}</span>
          </div>
          <div className="diff-body">
            {file.hunks.map((hunk, hi) => (
              <div key={hi}>
                <div className="diff-hunk-hd">{hunk.header}</div>
                {hunk.lines.map((ln, li) => {
                  const kind = ln[0] === '+' ? 'add' : ln[0] === '-' ? 'del' : 'ctx'
                  return (
                    <div key={li} className={`diff-line diff-${kind}`}>
                      <span className="diff-gutter">{ln[0] === '+' ? '+' : ln[0] === '-' ? '-' : ' '}</span>
                      <span className="diff-content">{ln.slice(1)}</span>
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── PR links bar ─────────────────────────────────────────────────────────────

function PrLinksBar({ prUrl, repo, issueNumber }) {
  const issueUrl = `https://github.com/${repo}/issues/${issueNumber}`
  return (
    <div className="pr-links-bar">
      {prUrl
        ? <a className="pr-cta" href={prUrl} target="_blank" rel="noopener noreferrer">
            View Pull Request <IconExternal />
          </a>
        : <span className="pr-cta-idle" aria-disabled="true">
            View Pull Request <IconExternal />
          </span>
      }
      <a className="issue-link" href={issueUrl} target="_blank" rel="noopener noreferrer">
        View Issue on GitHub <IconExternal />
      </a>
    </div>
  )
}

// ─── Status badge ─────────────────────────────────────────────────────────────

const STATUS_LABEL = { pending: 'Pending', running: 'Running', done: 'Complete', failed: 'Failed' }

function StatusBadge({ status }) {
  return (
    <span className={`badge badge-${status}`}>
      <span className="badge-dot" />
      {STATUS_LABEL[status] ?? status}
    </span>
  )
}

// ─── Mock pipeline preview (static visual, landing page only) ─────────────────

const MOCK_STEPS_DATA = [
  { label: 'Issue Parser',   status: 'done',    msg: '' },
  { label: 'Repo Indexer',   status: 'done',    msg: '' },
  { label: 'Retriever',      status: 'done',    msg: '' },
  { label: 'Planner',        status: 'done',    msg: '' },
  { label: 'Code Generator', status: 'running', msg: 'Writing AuthMiddleware.java' },
  { label: 'Diff Generator', status: 'pending', msg: 'Pending' },
  { label: 'PR Creator',     status: 'pending', msg: 'Pending' },
]

const MOCK_DONE_MSGS = [
  'Classified as bug_fix',
  '2,847 chunks indexed',
  '4 relevant files found',
  'Plan ready · high confidence',
]

const MOCK_DIFF_LINES = [
  { cls: 'mock-diff-meta', g: null, text: '--- a/src/auth/AuthMiddleware.java' },
  { cls: 'mock-diff-meta', g: null, text: '+++ b/src/auth/AuthMiddleware.java' },
  { cls: 'mock-diff-hunk', g: null, text: '@@ -42,6 +42,8 @@ public class AuthMiddleware' },
  { cls: 'mock-diff-del',  g: '-',  text: '  if (user.getSession() == null) {' },
  { cls: 'mock-diff-add',  g: '+',  text: '  if (user == null || user.getSession() == null) {' },
  { cls: 'mock-diff-add',  g: '+',  text: '    log.warn("null user encountered");' },
  { cls: 'mock-diff-ctx',  g: ' ',  text: '    return Response.unauthorized();' },
]

function MockPipelinePanel() {
  const [typed,       setTyped]       = useState(MOCK_DONE_MSGS.map(() => ''))
  const [diffVisible, setDiffVisible] = useState(MOCK_DIFF_LINES.map(() => false))

  // Typewriter: type each done-step message in sequence, 40ms/char, 500ms start delay
  useEffect(() => {
    let cancelled = false
    const timers = []
    let delay = 500
    MOCK_DONE_MSGS.forEach((msg, i) => {
      for (let c = 1; c <= msg.length; c++) {
        const chars = c, idx = i
        timers.push(setTimeout(() => {
          if (cancelled) return
          setTyped(prev => { const n = [...prev]; n[idx] = msg.slice(0, chars); return n })
        }, delay))
        delay += 40
      }
    })
    return () => { cancelled = true; timers.forEach(clearTimeout) }
  }, [])

  // Diff staggered reveal loop: reveal one line every 300ms, hold 2s, fade all out, repeat
  useEffect(() => {
    let cancelled = false
    const timers = []

    function runCycle() {
      if (cancelled) return
      setDiffVisible(MOCK_DIFF_LINES.map(() => false))
      MOCK_DIFF_LINES.forEach((_, i) => {
        timers.push(setTimeout(() => {
          if (cancelled) return
          setDiffVisible(prev => { const n = [...prev]; n[i] = true; return n })
        }, i * 300))
      })
      timers.push(setTimeout(() => {
        if (cancelled) return
        setDiffVisible(MOCK_DIFF_LINES.map(() => false))
        timers.push(setTimeout(runCycle, 400))
      }, (MOCK_DIFF_LINES.length - 1) * 300 + 2000))
    }

    runCycle()
    return () => { cancelled = true; timers.forEach(clearTimeout) }
  }, [])

  return (
    <div className="mock-panel">
      <div className="mock-titlebar">
        <div className="mock-lights">
          <span className="mock-light mock-light-red" />
          <span className="mock-light mock-light-yellow" />
          <span className="mock-light mock-light-green" />
        </div>
        <span className="mock-title">autopr-run · issue #42</span>
      </div>

      <div className="mock-steps">
        {MOCK_STEPS_DATA.map((step, i) => (
          <div key={i} className={`mock-step mock-step-${step.status}`}>
            <span className="mock-step-icon">
              {step.status === 'done'    && <IconCheck />}
              {step.status === 'running' && <span className="mock-running-dot" />}
              {step.status === 'pending' && <span className="mock-pending-circle" />}
            </span>
            <span className="mock-step-num">{String(i + 1).padStart(2, '0')}</span>
            <span className="mock-step-label">{step.label}</span>
            <span className="mock-step-msg">
              {step.status === 'done'
                ? typed[i]
                : step.status === 'running'
                  ? <>{step.msg}<span className="mock-cursor">▋</span></>
                  : step.msg}
            </span>
          </div>
        ))}
      </div>

      <div className="mock-diff-block">
        {MOCK_DIFF_LINES.map((line, i) => (
          <div
            key={i}
            className={`mock-diff-line ${line.cls}`}
            style={{ opacity: diffVisible[i] ? 1 : 0, transition: 'opacity 200ms' }}
          >
            {line.g !== null && <span className="mock-diff-g">{line.g}</span>}
            {line.text}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── How it works — animated pipeline ticker ─────────────────────────────────

const HOW_ROWS = [PIPELINE_STEPS.slice(0, 4), PIPELINE_STEPS.slice(4)]

const HOW_DESCS = [
  'Classifies issue as bug fix, feature, or refactor',
  'Builds a FAISS semantic index of the codebase',
  'Finds the most relevant code chunks via vector search',
  'Produces a structured JSON change plan via LLM',
  'Writes updated files based on the plan',
  'Computes unified diffs with dry-run validation',
  'Commits, pushes, and opens a GitHub pull request',
]

function HowItWorks() {
  const [activeStep,  setActiveStep]  = useState(0)
  const [pulsingConn, setPulsingConn] = useState(null)
  const prefersReduced = useRef(
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )

  useEffect(() => {
    const ACTIVE_MS = 1500
    const PULSE_MS  = 400
    const total     = PIPELINE_STEPS.length
    let mounted     = true
    let t1 = null
    let t2 = null

    function tick(step) {
      if (!mounted) return
      setActiveStep(step)
      setPulsingConn(null)

      t1 = setTimeout(() => {
        if (!mounted) return
        const next = (step + 1) % total
        if (!prefersReduced.current) setPulsingConn(step)
        const delay = prefersReduced.current ? 0 : PULSE_MS
        t2 = setTimeout(() => tick(next), delay)
      }, ACTIVE_MS)
    }

    tick(0)
    return () => { mounted = false; clearTimeout(t1); clearTimeout(t2) }
  }, [])

  return (
    <section className="how">
      <p className="how-title">How it works</p>
      <div className="how-rows">
        {HOW_ROWS.map((rowSteps, rowIdx) => (
          <div key={rowIdx} className="how-ticker">
            {rowSteps.map((step, j) => {
              const i           = rowIdx === 0 ? j : j + 4
              const isActive    = activeStep === i
              const isPulsing   = pulsingConn === i
              const isLastInRow = j === rowSteps.length - 1
              return (
                <div key={step.id} className="hw-node">
                  <div className={`hw-step${isActive ? ' hw-step-active' : ''}`}>
                    <span className="hw-num">{String(i + 1).padStart(2, '0')}</span>
                    <span className="hw-label">{step.label}</span>
                    <span className="hw-underline" />
                    <span className="hw-desc">{HOW_DESCS[i]}</span>
                  </div>
                  {!isLastInRow && (
                    <div className="hw-conn">
                      <div className="hw-conn-track">
                        <div className="hw-conn-line" />
                        {isPulsing && <div className="hw-pulse" />}
                      </div>
                      <span className="hw-conn-arrow">→</span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </section>
  )
}

// ─── Step log ─────────────────────────────────────────────────────────────────

function LogLine({ line, idx }) {
  const u      = line.toUpperCase()
  const kind   = u.startsWith('OK') ? 'ok' : u.startsWith('WARN') ? 'warn' : u.startsWith('ERR') ? 'err' : 'info'
  const space  = line.indexOf(' ')
  const prefix = space > -1 ? line.slice(0, space) : line
  const rest   = space > -1 ? line.slice(space + 1) : ''
  return (
    <div className={`log-line log-${kind}`} style={{ animationDelay: `${idx * 25}ms` }}>
      <span className="log-prefix">{prefix}</span>
      <span className="log-msg">{rest}</span>
    </div>
  )
}

function LogBlock({ lines }) {
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [lines.length])

  return (
    <div className="log-block">
      <div className="block-titlebar">
        <span className="titlebar-dot" /><span className="titlebar-dot" /><span className="titlebar-dot" />
        <span className="block-title">step log</span>
      </div>
      <div className="log-body">
        {lines.length === 0
          ? <span className="log-empty">Waiting for pipeline…</span>
          : lines.map((ln, i) => <LogLine key={ln} line={ln} idx={i} />)
        }
        <div ref={endRef} />
      </div>
    </div>
  )
}

// ─── Home page ────────────────────────────────────────────────────────────────

function HomePage({ onRunStarted }) {
  const [repo, setRepo]    = useState('')
  const [num, setNum]      = useState('')
  const [loading, setLoad] = useState(false)
  const [error, setError]  = useState('')
  const [shimmer,    setShimmer]  = useState(false)
  const shimmerTimer = useRef(null)
  const wasReady     = useRef(false)

  useEffect(() => {
    const ready = !!repo && !!num
    if (ready && !wasReady.current) {
      wasReady.current = true
      setShimmer(true)
      clearTimeout(shimmerTimer.current)
      shimmerTimer.current = setTimeout(() => setShimmer(false), 750)
    } else if (!ready) {
      wasReady.current = false
    }
  }, [repo, num])

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (!repo.includes('/')) { setError('Repo must be in owner/name format'); return }
    const n = parseInt(num, 10)
    if (!n || n < 1) { setError('Issue number must be a positive integer'); return }

    setLoad(true)
    try {
      const res = await fetch('/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo, issue_number: n }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.detail ?? `Server error ${res.status}`)
      }
      const d = await res.json()
      onRunStarted(d.run_id, repo, n)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoad(false)
    }
  }

  return (
    <>
      <div className="hero">
        <div className="hero-glow" aria-hidden="true" />
        <div className="hero-scanlines" aria-hidden="true" />
        <div className="hero-divider" aria-hidden="true" />

        <div className="hero-left">
          <div className="hero-badge">
            <span className="hero-badge-dot" />
            AUTONOMOUS AGENT
          </div>
          <h1 className="hero-headline">AutoPR</h1>
          <p className="hero-subline">
            Point it at a GitHub issue.<br />Get a pull request back.
          </p>

          <form className="terminal-form" onSubmit={submit}>
            <div className="t-line">
              <span className="t-prompt">$</span>
              <span className="t-cmd"> autopr </span>
              <span className="t-flag">--repo </span>
              <input
                id="repo" type="text" className="t-input"
                placeholder="owner/repo"
                value={repo} onChange={e => setRepo(e.target.value)}
                disabled={loading} autoFocus autoComplete="off" spellCheck={false}
              />
            </div>
            <div className="t-line">
              <span className="t-prompt">$</span>
              <span className="t-cmd"> autopr </span>
              <span className="t-flag">--issue </span>
              <input
                id="num" type="number" className="t-input t-input-num"
                placeholder="#42" min="1"
                value={num} onChange={e => setNum(e.target.value)}
                disabled={loading}
              />
            </div>
            {error && <p className="form-error">{error}</p>}
            <button className={`btn-run${shimmer ? ' btn-run-shimmer' : ''}`} type="submit" disabled={loading}>
              {loading ? '▶ starting…' : 'Run →'}
            </button>
          </form>

          <div className="issue-preview-slot">
            <IssuePreview repo={repo} issueNumber={num} />
          </div>
        </div>

        <div className="hero-right">
          <MockPipelinePanel />
        </div>
      </div>

      <HowItWorks />
    </>
  )
}

// ─── Status page ──────────────────────────────────────────────────────────────

function StatusPage({ runId, repo, issueNumber, onBack }) {
  const [run, setRun]  = useState({ status: 'pending', step_log: [], errors: [], pr_url: null, diffs: [] })
  const pollRef        = useRef(null)
  const states         = parseStepStates(run.step_log, run.status)
  const settled        = run.status === 'done' || run.status === 'failed'
  const active         = run.status === 'running' || run.status === 'pending'

  useEffect(() => {
    let cancelled = false

    async function poll() {
      if (cancelled) return
      try {
        const res = await fetch(`/status/${runId}`)
        if (!res.ok) return
        const d = await res.json()
        console.log('[poll]', d.status, 'step_log:', d.step_log)
        if (cancelled) return
        setRun(d)
        if (d.status === 'done' || d.status === 'failed') return
      } catch (_) {}
      if (!cancelled) pollRef.current = setTimeout(poll, 500)
    }

    poll()
    return () => { cancelled = true; clearTimeout(pollRef.current) }
  }, [runId])

  return (
    <>
      {active && <ProgressBar states={states} status={run.status} />}

      <main className={`page page-status ${active ? 'page-nudged' : ''}`}>
        <div className="status-card">

          <div className="status-hd">
            <div className="status-hd-row">
              <h2 className="status-title">{repo} <span className="status-issue">#{issueNumber}</span></h2>
              <StatusBadge status={run.status} />
            </div>
            <p className="status-meta">run/{runId}</p>
          </div>

          <div className="divider" />

          <PipelineVisualizer stepLog={run.step_log} status={run.status} />

          <PrLinksBar prUrl={run.pr_url} repo={repo} issueNumber={issueNumber} />

          <LogBlock lines={run.step_log} />

          {run.diffs?.length > 0 && <DiffViewer diffs={run.diffs} />}

          {run.status === 'failed' && run.errors.length > 0 && (
            <div className="errors-block">
              <p className="errors-title">Errors</p>
              {run.errors.map((e, i) => <p key={i} className="errors-msg">{e}</p>)}
            </div>
          )}

          {settled && (
            <button className="back-link" onClick={onBack}>
              <IconArrowLeft /> Run another issue
            </button>
          )}

        </div>
      </main>
    </>
  )
}

// ─── App shell ────────────────────────────────────────────────────────────────

export default function App() {
  const [view, setView] = useState('home')
  const [runId, setId]  = useState(null)
  const [repo, setRepo] = useState('')
  const [issue, setIss] = useState(null)

  function onRunStarted(id, r, n) {
    setId(id); setRepo(r); setIss(n); setView('status')
  }

  return (
    <>
      <Navbar />
      {view === 'home'
        ? <HomePage onRunStarted={onRunStarted} />
        : <StatusPage runId={runId} repo={repo} issueNumber={issue} onBack={() => setView('home')} />
      }
    </>
  )
}
