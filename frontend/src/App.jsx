import { useState, useEffect, useRef } from 'react'
import Markdown from 'react-markdown'
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
      <p className="issue-title"><Markdown>{data.title}</Markdown></p>
      {data.body && (
        <div className="issue-body">
          <Markdown>{data.body.slice(0, 300) + (data.body.length > 300 ? '…' : '')}</Markdown>
        </div>
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

// ─── Mock pipeline preview (animated, landing page only) ─────────────────────

const STEP_DURATIONS  = [2500, 4000, 3000, 5000, 3500, 3200, 5000] // ms per step

const STEP_RUNNING_MSGS = [
  'parsing issue body',
  'embedding 2,847 chunks',
  'querying vector index',
  'generating JSON plan',
  'writing AuthMiddleware.java',
  'diffing 1 file',
  'pushing autopr/issue-42',
]

const STEP_DONE_MSGS = [
  'classified: bug_fix',
  '2,847 chunks indexed',
  '4 files · score 0.91',
  'high confidence',
  '1 file patched',
  '+14 −4 · 3 hunks',
  'PR #47 opened',
]

const MOCK_DIFF_LINES = [
  { cls: 'mock-diff-meta', g: null, text: '--- a/src/auth/AuthMiddleware.java' },
  { cls: 'mock-diff-meta', g: null, text: '+++ b/src/auth/AuthMiddleware.java' },
  { cls: 'mock-diff-hunk', g: null, text: '@@ -38,9 +38,15 @@ AuthMiddleware {' },
  { cls: 'mock-diff-ctx',  g: ' ',  text: '  public Response handle(Request req) {' },
  { cls: 'mock-diff-del',  g: '-',  text: '    User user = sessions.get(req.token());' },
  { cls: 'mock-diff-del',  g: '-',  text: '    if (user.getSession() == null) {' },
  { cls: 'mock-diff-add',  g: '+',  text: '    if (req.token() == null) {' },
  { cls: 'mock-diff-add',  g: '+',  text: '      log.warn("missing auth token");' },
  { cls: 'mock-diff-add',  g: '+',  text: '      return Response.unauthorized();' },
  { cls: 'mock-diff-add',  g: '+',  text: '    }' },
  { cls: 'mock-diff-add',  g: '+',  text: '    User user = sessions.get(req.token());' },
  { cls: 'mock-diff-add',  g: '+',  text: '    if (user == null || user.getSession() == null) {' },
  { cls: 'mock-diff-add',  g: '+',  text: '      log.warn("null user or session");' },
  { cls: 'mock-diff-ctx',  g: ' ',  text: '      return Response.unauthorized();' },
  { cls: 'mock-diff-ctx',  g: ' ',  text: '    }' },
  { cls: 'mock-diff-ctx',  g: ' ',  text: '    return chain.next(req.withUser(user));' },
]

const ANIM02_FILES = [
  'src/auth/AuthMiddleware.java',
  'src/api/UserController.java',
  'src/models/User.java',
  'src/session/SessionManager.java',
  'src/utils/Logger.java',
  'src/config/AppConfig.java',
  'tests/AuthMiddlewareTest.java',
]

const ANIM03_RESULTS = [
  { file: 'src/auth/AuthMiddleware.java',    pct: 94 },
  { file: 'src/api/UserController.java',     pct: 87 },
  { file: 'src/session/SessionManager.java', pct: 71 },
  { file: 'src/models/User.java',            pct: 58 },
]

const ANIM04_JSON = `{
  "files_to_modify": [
    {
      "path": "src/auth/AuthMiddleware.java",
      "change_summary": "add null session check"
    }
  ],
  "confidence": "high"
}`

const ANIM07_L1 = '$ git commit -m "fix: add null session check"'
const ANIM07_L2 = '$ git push origin autopr/issue-42'
const ANIM07_L3 = '✓ https://github.com/vxm52/wireflow/pull/9'
const ANIM07_CHAR_MS = 18

function MockPipelinePanel() {
  const [stepStates, setStepStates] = useState(PIPELINE_STEPS.map(() => 'pending'))
  const [stepMsgs,   setStepMsgs]   = useState(PIPELINE_STEPS.map(() => ''))
  const [showPlan,   setShowPlan]   = useState(false)
  const [diffCount,  setDiffCount]  = useState(0)
  const [prDone,     setPrDone]     = useState(false)
  const [anim02Files,  setAnim02Files]  = useState(0)
  const [anim02Pct,    setAnim02Pct]    = useState(0)
  const [anim02Chunks,  setAnim02Chunks]  = useState(0)
  const [anim03Visible, setAnim03Visible] = useState(0)
  const [anim03Bars,    setAnim03Bars]    = useState([0, 0, 0, 0])
  const [anim04CharIdx, setAnim04CharIdx] = useState(0)
  const [anim04Fading,  setAnim04Fading]  = useState(false)
  const [anim01ScanKey, setAnim01ScanKey] = useState(0)
  const [anim01BadgeOn, setAnim01BadgeOn] = useState(false)
  const [anim06ScanKey, setAnim06ScanKey] = useState(0)
  const [anim06BadgeOn, setAnim06BadgeOn] = useState(false)
  const [anim06Fading,  setAnim06Fading]  = useState(false)
  const [anim07Line1,      setAnim07Line1]      = useState('')
  const [anim07Line2,      setAnim07Line2]      = useState('')
  const [anim07Line3,      setAnim07Line3]      = useState('')
  const [anim07PulseActive, setAnim07PulseActive] = useState(false)
  const [anim07Fading,     setAnim07Fading]     = useState(false)

  const doneCount     = stepStates.filter(s => s === 'done').length
  const activeStepIdx = stepStates.findIndex(s => s === 'running')

  useEffect(() => {
    let cancelled = false
    const timers  = []

    function go(fn, delay) {
      const t = setTimeout(() => { if (!cancelled) fn() }, delay)
      timers.push(t)
    }

    function runCycle() {
      if (cancelled) return
      setStepStates(PIPELINE_STEPS.map(() => 'pending'))
      setStepMsgs(PIPELINE_STEPS.map(() => ''))
      setShowPlan(false)
      setDiffCount(0)
      setPrDone(false)

      let delay = 600
      const startAt = []

      PIPELINE_STEPS.forEach((_, i) => {
        startAt.push(delay)
        const s = delay, e = delay + STEP_DURATIONS[i]

        go(() => {
          setStepStates(p => { const n=[...p]; n[i]='running'; return n })
          setStepMsgs(p   => { const n=[...p]; n[i]=STEP_RUNNING_MSGS[i]; return n })
        }, s)

        go(() => {
          setStepStates(p => { const n=[...p]; n[i]='done'; return n })
          setStepMsgs(p   => { const n=[...p]; n[i]=STEP_DONE_MSGS[i]; return n })
          if (i === 3) go(() => setShowPlan(true), 200)
          if (i === PIPELINE_STEPS.length - 1) go(() => setPrDone(true), 350)
        }, e)

        delay = e
      })

      // Diff lines reveal during code_generator (step 4)
      const diffStart = startAt[4] + 200
      MOCK_DIFF_LINES.forEach((_, i) => go(() => setDiffCount(i + 1), diffStart + i * 120))

      // Loop: hold success state 4s then restart
      go(() => { setPrDone(false); setShowPlan(false); setDiffCount(0); go(runCycle, 600) }, delay + 4200)
    }

    runCycle()
    return () => { cancelled = true; timers.forEach(clearTimeout) }
  }, [])

  useEffect(() => {
    if (activeStepIdx !== 0) return
    let cancelled = false
    const timers = []

    setAnim01BadgeOn(false)

    // Kick off scan — 150ms delay lets the container fade-in settle first
    const ts = setTimeout(() => { if (!cancelled) setAnim01ScanKey(k => k + 1) }, 150)
    timers.push(ts)

    // Scan sweep takes 850ms; badge appears 100ms after scan completes
    const tb = setTimeout(() => { if (!cancelled) setAnim01BadgeOn(true) }, 1100)
    timers.push(tb)

    return () => { cancelled = true; timers.forEach(clearTimeout) }
  }, [activeStepIdx])

  useEffect(() => {
    if (activeStepIdx !== 1) return
    let cancelled = false
    const timers = []

    function runAnim02() {
      if (cancelled) return
      setAnim02Files(0)
      setAnim02Pct(0)
      setAnim02Chunks(0)

      ANIM02_FILES.forEach((_, i) => {
        const t = setTimeout(() => { if (!cancelled) setAnim02Files(i + 1) }, i * 350)
        timers.push(t)
      })

      const PROG_START = ANIM02_FILES.length * 250  // 1750ms after last file
      const PROG_DUR   = 2000
      const TICKS      = 48
      for (let i = 0; i <= TICKS; i++) {
        const t = setTimeout(() => {
          if (!cancelled) {
            setAnim02Pct(Math.round((i / TICKS) * 100))
            setAnim02Chunks(Math.round((i / TICKS) * 2847))
          }
        }, PROG_START + (i / TICKS) * PROG_DUR)
        timers.push(t)
      }

      const t = setTimeout(() => { if (!cancelled) runAnim02() }, PROG_START + PROG_DUR + 2000)
      timers.push(t)
    }

    runAnim02()
    return () => { cancelled = true; timers.forEach(clearTimeout) }
  }, [activeStepIdx])

  useEffect(() => {
    if (activeStepIdx !== 2) return
    let cancelled = false
    const timers = []

    function runAnim03() {
      if (cancelled) return
      setAnim03Visible(0)
      setAnim03Bars([0, 0, 0, 0])

      const ROW_TICKS = 15  // ticks per bar over 300ms
      ANIM03_RESULTS.forEach((r, i) => {
        const rowStart = i * 300

        // Row appears
        const tv = setTimeout(() => { if (!cancelled) setAnim03Visible(i + 1) }, rowStart)
        timers.push(tv)

        // Bar fills over 300ms
        for (let t = 0; t <= ROW_TICKS; t++) {
          const delay  = rowStart + Math.round((t / ROW_TICKS) * 500)
          const barPct = Math.round((t / ROW_TICKS) * r.pct)
          const tb = setTimeout(() => {
            if (!cancelled) setAnim03Bars(prev => {
              const next = [...prev]; next[i] = barPct; return next
            })
          }, delay)
          timers.push(tb)
        }
      })

      // Hold 1500ms after last bar finishes, then loop
      const loopAt = (ANIM03_RESULTS.length - 1) * 300 + 500 + 2000
      const tl = setTimeout(() => { if (!cancelled) runAnim03() }, loopAt)
      timers.push(tl)
    }

    runAnim03()
    return () => { cancelled = true; timers.forEach(clearTimeout) }
  }, [activeStepIdx])

  useEffect(() => {
    if (activeStepIdx !== 3) return
    let cancelled = false
    const timers = []

    function runAnim04() {
      if (cancelled) return
      setAnim04CharIdx(0)
      setAnim04Fading(false)

      const N       = ANIM04_JSON.length
      const CHAR_MS = 30

      for (let i = 1; i <= N; i++) {
        const t = setTimeout(() => { if (!cancelled) setAnim04CharIdx(i) }, i * CHAR_MS)
        timers.push(t)
      }

      // Hold 1500ms after last char, then fade out
      const fadeAt = N * CHAR_MS + 2500
      const tf = setTimeout(() => { if (!cancelled) setAnim04Fading(true) }, fadeAt)
      timers.push(tf)

      // After fade (350ms), reset and loop
      const tl = setTimeout(() => { if (!cancelled) runAnim04() }, fadeAt + 400)
      timers.push(tl)
    }

    runAnim04()
    return () => { cancelled = true; timers.forEach(clearTimeout) }
  }, [activeStepIdx])

  useEffect(() => {
    if (activeStepIdx !== 5) return
    let cancelled = false
    const timers = []

    function runAnim06() {
      if (cancelled) return
      setAnim06BadgeOn(false)
      setAnim06Fading(false)

      // 1000ms pre-scan delay, then remount scan element → restarts CSS animation
      const ts = setTimeout(() => { if (!cancelled) setAnim06ScanKey(k => k + 1) }, 1000)
      timers.push(ts)

      // Badge fades in after pre-scan (1000ms) + scan (800ms) + delay (300ms) = 2100ms
      const tb = setTimeout(() => { if (!cancelled) setAnim06BadgeOn(true) }, 2100)
      timers.push(tb)

      // Hold 2000ms after badge appears, then fade inner content
      const tf = setTimeout(() => { if (!cancelled) setAnim06Fading(true) }, 4100)
      timers.push(tf)

      // After fade (300ms), loop
      const tl = setTimeout(() => { if (!cancelled) runAnim06() }, 4400)
      timers.push(tl)
    }

    runAnim06()
    return () => { cancelled = true; timers.forEach(clearTimeout) }
  }, [activeStepIdx])

  useEffect(() => {
    if (activeStepIdx !== 6) return
    let cancelled = false
    const timers = []

    function runAnim07() {
      if (cancelled) return
      setAnim07Line1('')
      setAnim07Line2('')
      setAnim07Line3('')
      setAnim07PulseActive(false)
      setAnim07Fading(false)

      const t1End = ANIM07_L1.length * ANIM07_CHAR_MS
      const t2End = t1End + ANIM07_L2.length * ANIM07_CHAR_MS
      const t3End = t2End + ANIM07_L3.length * ANIM07_CHAR_MS

      for (let i = 1; i <= ANIM07_L1.length; i++) {
        const t = setTimeout(() => { if (!cancelled) setAnim07Line1(ANIM07_L1.slice(0, i)) }, i * ANIM07_CHAR_MS)
        timers.push(t)
      }
      for (let i = 1; i <= ANIM07_L2.length; i++) {
        const t = setTimeout(() => { if (!cancelled) setAnim07Line2(ANIM07_L2.slice(0, i)) }, t1End + i * ANIM07_CHAR_MS)
        timers.push(t)
      }
      for (let i = 1; i <= ANIM07_L3.length; i++) {
        const t = setTimeout(() => { if (!cancelled) setAnim07Line3(ANIM07_L3.slice(0, i)) }, t2End + i * ANIM07_CHAR_MS)
        timers.push(t)
      }

      // Pulse URL once after all lines typed
      const tp = setTimeout(() => { if (!cancelled) setAnim07PulseActive(true) }, t3End)
      timers.push(tp)

      // Hold 2000ms then fade out
      const tf = setTimeout(() => { if (!cancelled) setAnim07Fading(true) }, t3End + 2000)
      timers.push(tf)

      // Loop after fade — large gap ensures it never fires mid-step (step is 5000ms, this fires at ~5714ms)
      const tl = setTimeout(() => { if (!cancelled) runAnim07() }, t3End + 2000 + 1500)
      timers.push(tl)
    }

    runAnim07()
    return () => { cancelled = true; timers.forEach(clearTimeout) }
  }, [activeStepIdx])

  return (
    <div className="mock-panel">
      <div className="mock-titlebar">
        <div className="mock-lights">
          <span className="mock-light mock-light-red" />
          <span className="mock-light mock-light-yellow" />
          <span className="mock-light mock-light-green" />
        </div>
        <span className="mock-title">autopr-run · issue #42</span>
        <span className="mock-counter">{doneCount}/{PIPELINE_STEPS.length}</span>
      </div>

      <div className="mock-steps">
        {PIPELINE_STEPS.map((step, i) => {
          const state = stepStates[i]
          const msg   = stepMsgs[i]
          return (
            <div key={i} className={`mock-step mock-step-${state}`}>
              <span className="mock-step-icon">
                {state === 'done'    && <IconCheck />}
                {state === 'running' && <span className="mock-running-dot" />}
                {state === 'pending' && <span className="mock-pending-circle" />}
              </span>
              <span className="mock-step-num">{String(i + 1).padStart(2, '0')}</span>
              <span className="mock-step-label">{step.label}</span>
              <span className="mock-step-msg">
                {state === 'running'
                  ? <>{msg}<span className="mock-cursor">▋</span></>
                  : msg}
              </span>
            </div>
          )
        })}
      </div>

      <div className="mock-panel-content">
        {/* Step animations — absolutely positioned, overlay content area when active */}
        <div className="step-anim-container" style={{ opacity: activeStepIdx === 0 ? 1 : 0 }}>
          <div className="anim01-card">
            <div className="anim01-meta-row">
              <span className="anim01-issue-num">#42</span>
              <span className="anim01-state-open">open</span>
            </div>
            <div className="anim01-header">
              <span className="anim01-title">Fix null session handling</span>
              <span className={`anim01-badge${anim01BadgeOn ? ' anim01-badge-on' : ''}`}>bug_fix</span>
            </div>
            <div className="anim01-body">
              <span>Sessions return null when token expires...</span>
              <span>causing NPE in AuthMiddleware on line 42</span>
            </div>
            <div key={anim01ScanKey} className="anim01-scan" />
          </div>
        </div>
        <div className="step-anim-container" style={{ opacity: activeStepIdx === 1 ? 1 : 0 }}>
          <div className="anim02-wrap">
            <div className="anim02-tree">
              {ANIM02_FILES.map((f, i) => (
                <div key={i} className={`anim02-file${anim02Files > i ? ' anim02-file-on' : ''}`}>
                  <span className="anim02-arrow">›</span>{f}
                </div>
              ))}
            </div>
            <div className="anim02-progress-wrap">
              <div className="anim02-bar">
                <div className="anim02-fill" style={{ width: `${anim02Pct}%` }} />
              </div>
              <span className="anim02-counter">indexing… {anim02Chunks.toLocaleString()} / 2,847 chunks</span>
            </div>
          </div>
        </div>
        <div className="step-anim-container" style={{ opacity: activeStepIdx === 2 ? 1 : 0 }}>
          <div className="anim03-wrap">
            {ANIM03_RESULTS.map((r, i) => (
              <div
                key={i}
                className={`anim03-row${i === 0 ? ' anim03-row-top' : ''}${anim03Visible > i ? ' anim03-row-on' : ''}`}
              >
                <div className="anim03-row-header">
                  <span className="anim03-file">{r.file}</span>
                  <span className="anim03-pct">{anim03Bars[i]}%</span>
                </div>
                <div className="anim03-bar">
                  <div className="anim03-fill" style={{ width: `${anim03Bars[i]}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="step-anim-container" style={{ opacity: activeStepIdx === 3 ? 1 : 0 }}>
          <div className={`anim04-wrap${anim04Fading ? ' anim04-fading' : ''}`}>
            <pre className="anim04-pre">{ANIM04_JSON.slice(0, anim04CharIdx)}<span className="mock-cursor">▋</span></pre>
          </div>
        </div>
        <div className="step-anim-container anim06-overlay" style={{ opacity: activeStepIdx === 4 ? 1 : 0 }} />
        <div className="step-anim-container anim06-overlay" style={{ opacity: activeStepIdx === 5 ? 1 : 0 }}>
          <div className={`anim06-inner${anim06Fading ? ' anim06-fading' : ''}`}>
            <div key={anim06ScanKey} className="anim06-scan" />
            <span className={`anim06-badge${anim06BadgeOn ? ' anim06-badge-on' : ''}`}>✓ validated</span>
          </div>
        </div>
        <div className="step-anim-container" style={{ opacity: activeStepIdx === 6 || doneCount === PIPELINE_STEPS.length ? 1 : 0 }}>
          <div className="anim07-terminal">
            <div className="anim07-terminal-hd">
              <div className="anim07-terminal-lights">
                <span className="mock-light mock-light-red" />
                <span className="mock-light mock-light-yellow" />
                <span className="mock-light mock-light-green" />
              </div>
              <span className="anim07-terminal-title">autopr/issue-42 — bash</span>
            </div>
            <div className="anim07-terminal-body">
              <div className={`anim07-wrap${anim07Fading ? ' anim07-fading' : ''}`}>
                {anim07Line1 && (
                  <span className="anim07-line">
                    {anim07Line1}{!anim07Line2 && <span className="mock-cursor">▋</span>}
                  </span>
                )}
                {anim07Line2 && (
                  <span className="anim07-line">
                    {anim07Line2}{!anim07Line3 && <span className="mock-cursor">▋</span>}
                  </span>
                )}
                {anim07Line3 && (
                  <span className={`anim07-line anim07-url${anim07PulseActive ? ' anim07-url-pulse' : ''}`}>
                    {anim07Line3}{!anim07Fading && <span className="mock-cursor">▋</span>}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Underlying content — plan and diff blocks */}
        <div className="mock-plan-block" style={{ opacity: showPlan ? 1 : 0, transition: 'opacity 0.25s ease' }}>
          <span className="mock-plan-title">plan</span>
          <div className="mock-plan-line">
            <span className="mock-plan-sig">modify</span>
            <span className="mock-plan-path">src/auth/AuthMiddleware.java</span>
          </div>
          <div className="mock-plan-desc">add null check before getSession() call</div>
        </div>

        <div className="mock-diff-block" style={{ opacity: diffCount > 0 ? 1 : 0, transition: 'opacity 0.14s ease' }}>
          {MOCK_DIFF_LINES.map((line, i) => (
            <div key={i} className={`mock-diff-line ${line.cls}`} style={{ opacity: i < diffCount ? 1 : 0, transition: 'opacity 0.14s ease' }}>
              {line.g !== null && <span className="mock-diff-g">{line.g}</span>}
              {line.text}
            </div>
          ))}
          <div className="mock-pr-success" style={{ opacity: prDone ? 1 : 0, transition: 'opacity 0.3s ease' }}>
            <IconCheck />
            <span>autopr/issue-42</span>
            <span className="mock-pr-arrow">→</span>
            <span className="mock-pr-url">github.com/org/repo/pull/47</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── How it works — 3-phase overview ─────────────────────────────────────────

function HowItWorks() {
  return (
    <section className="how">
      <div className="how-phase">
        <span className="how-phase-num">01</span>
        <span className="how-phase-label">Submit an issue</span>
        <p className="how-phase-desc">Paste a GitHub repo and issue number. AutoPR fetches the issue and classifies the task type.</p>
      </div>
      <span className="how-arrow" aria-hidden="true">→</span>
      <div className="how-phase">
        <span className="how-phase-num">02</span>
        <span className="how-phase-label">Agent runs the pipeline</span>
        <p className="how-phase-desc">7 steps: index the repo, retrieve relevant files, plan the changes, generate patches, and validate diffs.</p>
      </div>
      <span className="how-arrow" aria-hidden="true">→</span>
      <div className="how-phase">
        <span className="how-phase-num">03</span>
        <span className="how-phase-label">Review your PR</span>
        <p className="how-phase-desc">AutoPR commits the changes to a new branch and opens a pull request on GitHub for you to review.</p>
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
