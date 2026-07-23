import { useEffect, useRef, useState } from 'react'
import Header from './components/Header'
import TriggerStrip, { SAMPLE_ALERTS } from './components/TriggerStrip'
import Card from './components/Card'
import { analyzeAlert, getHealth, ApiError } from './api'
import { MOCK_MEDIUM, MOCK_LOW } from './mockCards'

const STAGES = ['Fingerprinting alert…', 'Retrieving evidence…', 'Scoring confidence…', 'Assembling card…']

function useProgressStages(active) {
  const [stage, setStage] = useState(0)
  useEffect(() => {
    if (!active) {
      setStage(0)
      return
    }
    const id = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 900)
    return () => clearInterval(id)
  }, [active])
  return STAGES[stage]
}

export default function App() {
  const [selectedId, setSelectedId] = useState(SAMPLE_ALERTS[0]?.id)
  const [generation, setGeneration] = useState(true)
  const [status, setStatus] = useState('idle') // idle | loading | success | error
  const [card, setCard] = useState(null)
  const [mock, setMock] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [health, setHealth] = useState('checking')
  const requestSeq = useRef(0)

  const stageLabel = useProgressStages(status === 'loading')

  useEffect(() => {
    let cancelled = false
    getHealth()
      .then((h) => !cancelled && setHealth(h.status === 'ok' ? 'ok' : 'degraded'))
      .catch(() => !cancelled && setHealth('down'))
    return () => {
      cancelled = true
    }
  }, [])

  const runAnalysis = async () => {
    const sample = SAMPLE_ALERTS.find((s) => s.id === selectedId)
    if (!sample) return
    const seq = ++requestSeq.current
    setStatus('loading')
    setErrorMsg('')
    setMock(false)
    try {
      const result = await analyzeAlert(sample.alert, generation)
      if (seq !== requestSeq.current) return
      setCard(result)
      setStatus('success')
    } catch (e) {
      if (seq !== requestSeq.current) return
      setErrorMsg(e instanceof ApiError ? e.detail || e.message : String(e))
      setStatus('error')
    }
  }

  const viewMock = (which) => {
    requestSeq.current++ // invalidate any in-flight analysis
    setCard(which === 'medium' ? MOCK_MEDIUM : MOCK_LOW)
    setMock(true)
    setStatus('success')
    setErrorMsg('')
  }

  return (
    <>
      <Header health={health} />

      <TriggerStrip
        selectedId={selectedId}
        onSelect={setSelectedId}
        onAnalyze={runAnalysis}
        generation={generation}
        onGenerationChange={setGeneration}
        busy={status === 'loading'}
      />

      <div className="mx-auto max-w-[880px] px-6 pb-3 pt-2 flex gap-4 text-xs text-muted">
        <span>Dev only — verify State 5 (medium/low confidence, rarely seen live):</span>
        <button type="button" onClick={() => viewMock('medium')} className="font-medium text-navy hover:text-coral-deep">
          view medium-confidence mock
        </button>
        <button type="button" onClick={() => viewMock('low')} className="font-medium text-navy hover:text-coral-deep">
          view low-confidence mock
        </button>
      </div>

      <main className="mx-auto max-w-[880px] px-6 pb-16">
        {status === 'loading' && (
          <div className="rounded-xl border border-hairline bg-surface p-10 text-center shadow-sm">
            <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-navy/20 border-t-navy" />
            <p className="text-sm font-medium text-ink">{stageLabel}</p>
          </div>
        )}

        {status === 'error' && (
          <div className="rounded-xl border-2 border-danger/40 bg-danger-tint p-6">
            <p className="text-sm font-semibold text-danger">Analysis failed</p>
            <p className="mt-1 text-sm text-ink">{errorMsg}</p>
            <button
              type="button"
              onClick={runAnalysis}
              className="mt-3 rounded-lg bg-danger px-3.5 py-1.5 text-xs font-semibold text-white hover:opacity-90"
            >
              Retry
            </button>
          </div>
        )}

        {status === 'success' && card && <Card card={card} mock={mock} />}

        {status === 'idle' && (
          <div className="rounded-xl border border-dashed border-hairline p-10 text-center text-sm text-muted">
            Pick a sample alert above and click Analyze.
          </div>
        )}
      </main>
    </>
  )
}
