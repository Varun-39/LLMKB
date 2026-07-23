const modules = import.meta.glob('../sample_alerts/*.json', { eager: true })
export const SAMPLE_ALERTS = Object.entries(modules)
  .map(([path, mod]) => ({ id: path, alert: mod.default }))
  .sort((a, b) => a.alert.search_name.localeCompare(b.alert.search_name))

export default function TriggerStrip({ selectedId, onSelect, onAnalyze, generation, onGenerationChange, busy }) {
  return (
    <div className="mx-auto max-w-[880px] px-6 -mt-px">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-hairline bg-surface px-4 py-3 shadow-sm">
        <select
          value={selectedId}
          onChange={(e) => onSelect(e.target.value)}
          className="flex-1 min-w-[220px] rounded-lg border border-hairline bg-page px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-coral/40"
        >
          {SAMPLE_ALERTS.map(({ id, alert }) => (
            <option key={id} value={id}>
              {alert.search_name} — {alert.result.host}
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={onAnalyze}
          disabled={busy}
          className="rounded-lg bg-coral px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-coral-deep disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {busy ? 'Analyzing…' : 'Analyze'}
        </button>

        <label className="flex shrink-0 items-center gap-2 text-xs font-medium text-muted select-none whitespace-nowrap">
          Generation
          <button
            type="button"
            role="switch"
            aria-checked={generation}
            onClick={() => onGenerationChange(!generation)}
            className={`relative h-5 w-9 shrink-0 rounded-full transition-colors duration-150 ${generation ? 'bg-navy' : 'bg-hairline'}`}
          >
            <span
              className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform duration-150 ${generation ? 'translate-x-4' : 'translate-x-0'}`}
            />
          </button>
          {generation ? 'on' : 'off'}
        </label>
      </div>
    </div>
  )
}
