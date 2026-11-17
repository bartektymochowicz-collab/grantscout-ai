import { useCallback, useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  ExternalLink,
  History,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  TriangleAlert,
} from 'lucide-react'
import './App.css'

// Dev (Vite, port 5173): backend na osobnym porcie. Produkcja: ten sam origin co FastAPI.
const API_URL = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''

const EXAMPLES = [
  'Aplikacja AI do nauki języków dla seniorów',
  'Platforma do wymiany nadwyżek żywności między restauracjami',
  'Inteligentny system nawadniania dla małych gospodarstw',
]

function formatDate(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('pl-PL', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function hostname(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

async function readError(response) {
  try {
    const data = await response.json()
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join(', ')
  } catch {
    /* odpowiedź nie jest JSON-em */
  }
  return `Serwer zwrócił błąd ${response.status}`
}

function App() {
  const [topic, setTopic] = useState('')
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    setHistoryError('')
    try {
      const response = await fetch(`${API_URL}/api/history`)
      if (!response.ok) throw new Error(await readError(response))
      setHistory(await response.json())
    } catch (err) {
      setHistoryError(
        err instanceof TypeError
          ? 'Brak połączenia z backendem'
          : err.message,
      )
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  async function handleAnalyze(event) {
    event.preventDefault()
    const trimmed = topic.trim()
    if (!trimmed || loading) return

    setLoading(true)
    setError('')
    setResult(null)
    try {
      const response = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: trimmed }),
      })
      if (!response.ok) throw new Error(await readError(response))
      const data = await response.json()
      setResult(data)
      setHistory((prev) => [data, ...prev.filter((item) => item.id !== data.id)])
    } catch (err) {
      setError(
        err instanceof TypeError
          ? `Nie udało się połączyć z backendem (${API_URL}). Czy serwer FastAPI jest uruchomiony?`
          : err.message,
      )
    } finally {
      setLoading(false)
    }
  }

  function openFromHistory(item) {
    if (loading) return
    setResult(item)
    setTopic(item.topic)
    setError('')
  }

  function startNew() {
    if (loading) return
    setResult(null)
    setTopic('')
    setError('')
  }

  return (
    <div className="gs-app">
      <aside className="gs-sidebar">
        <div className="gs-brand">
          <div className="gs-logo">
            <Sparkles size={18} />
          </div>
          <div>
            <div className="gs-brand-name">GrantScout AI</div>
            <div className="gs-brand-tag">Weryfikacja pomysłów</div>
          </div>
        </div>

        <button className="gs-new-btn" onClick={startNew} disabled={loading}>
          <Plus size={16} /> Nowa analiza
        </button>

        <div className="gs-history-header">
          <span>
            <History size={14} /> Historia
          </span>
          <button
            className="gs-icon-btn"
            onClick={loadHistory}
            title="Odśwież historię"
            aria-label="Odśwież historię"
          >
            <RefreshCw size={14} className={historyLoading ? 'gs-spin' : ''} />
          </button>
        </div>

        <nav className="gs-history">
          {historyLoading && history.length === 0 && (
            <>
              <div className="gs-skeleton" />
              <div className="gs-skeleton" />
              <div className="gs-skeleton" />
            </>
          )}
          {historyError && <div className="gs-history-empty gs-text-error">{historyError}</div>}
          {!historyLoading && !historyError && history.length === 0 && (
            <div className="gs-history-empty">Brak analiz. Zacznij od pierwszego pomysłu!</div>
          )}
          {history.map((item) => (
            <button
              key={item.id}
              className={`gs-history-item ${result?.id === item.id ? 'is-active' : ''}`}
              onClick={() => openFromHistory(item)}
              title={item.topic}
            >
              <span className="gs-history-topic">{item.topic}</span>
              <span className="gs-history-date">{formatDate(item.created_at)}</span>
            </button>
          ))}
        </nav>

        <div className="gs-sidebar-footer">Tavily × Gemini</div>
      </aside>

      <main className="gs-main">
        <div className="gs-container">
          <header className="gs-hero">
            <span className="gs-badge">
              <span className="gs-dot" /> Analiza konkurencji w czasie rzeczywistym
            </span>
            <h1 className="gs-title">
              Sprawdź swój pomysł <span className="gs-gradient">zanim złożysz wniosek</span>
            </h1>
            <p className="gs-subtitle">
              Opisz temat projektu, a GrantScout przeszuka sieć w poszukiwaniu istniejących
              rozwiązań i przygotuje rzetelną ocenę od AI-mentora.
            </p>
          </header>

          <form className="gs-form" onSubmit={handleAnalyze}>
            <div className="gs-input-wrap">
              <Search size={18} className="gs-input-icon" />
              <textarea
                className="gs-input"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) handleAnalyze(e)
                }}
                placeholder="Np. aplikacja mobilna łącząca wolontariuszy z lokalnymi schroniskami…"
                rows={2}
                maxLength={500}
                disabled={loading}
              />
            </div>
            <div className="gs-form-footer">
              <span className="gs-counter">{topic.length}/500</span>
              <button className="gs-primary-btn" type="submit" disabled={loading || !topic.trim()}>
                {loading ? (
                  <>
                    <Loader2 size={16} className="gs-spin" /> Analizuję…
                  </>
                ) : (
                  <>
                    <Sparkles size={16} /> Analizuj pomysł
                  </>
                )}
              </button>
            </div>
          </form>

          {!result && !loading && !error && (
            <div className="gs-examples">
              <span>Spróbuj:</span>
              {EXAMPLES.map((ex) => (
                <button key={ex} className="gs-chip" onClick={() => setTopic(ex)}>
                  {ex}
                </button>
              ))}
            </div>
          )}

          {error && (
            <div className="gs-alert" role="alert">
              <TriangleAlert size={18} />
              <div>
                <strong>Coś poszło nie tak</strong>
                <p>{error}</p>
              </div>
            </div>
          )}

          {loading && (
            <section className="gs-card gs-loading" aria-live="polite">
              <div className="gs-loader">
                <span />
                <span />
                <span />
              </div>
              <p className="gs-loading-text">Przeszukuję sieć z Tavily i analizuję z Gemini...</p>
              <p className="gs-loading-hint">To może potrwać kilkanaście sekund.</p>
              <div className="gs-steps">
                <div className="gs-step">1. Wyszukiwanie konkurencji</div>
                <div className="gs-step">2. Zbieranie źródeł</div>
                <div className="gs-step">3. Ocena przez AI-mentora</div>
              </div>
            </section>
          )}

          {result && !loading && (
            <div className="gs-result">
              <section className="gs-card">
                <div className="gs-card-head">
                  <div>
                    <div className="gs-label">Analiza</div>
                    <h2 className="gs-result-topic">{result.topic}</h2>
                  </div>
                  <div className="gs-meta">
                    {result.model && <span className="gs-pill">{result.model}</span>}
                    <span className="gs-meta-date">{formatDate(result.created_at)}</span>
                  </div>
                </div>
                <div className="gs-markdown">
                  <ReactMarkdown
                    components={{
                      a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" />,
                    }}
                  >
                    {result.summary || '_Brak podsumowania._'}
                  </ReactMarkdown>
                </div>
              </section>

              {result.sources?.length > 0 && (
                <section className="gs-card">
                  <div className="gs-label">Źródła ({result.sources.length})</div>
                  <ul className="gs-sources">
                    {result.sources.map((src, i) => (
                      <li key={`${src.url}-${i}`}>
                        <a
                          className="gs-source"
                          href={src.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <span className="gs-source-index">{i + 1}</span>
                          <span className="gs-source-body">
                            <span className="gs-source-title">{src.title || src.url}</span>
                            <span className="gs-source-host">{hostname(src.url)}</span>
                          </span>
                          <ExternalLink size={16} className="gs-source-icon" />
                        </a>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default App
