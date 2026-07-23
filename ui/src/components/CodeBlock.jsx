import { useState } from 'react'

// Rule 3: commands are never body text. Rule 4: copy-to-clipboard is the
// maximum affordance — this never executes anything.
export default function CodeBlock({ content }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard API unavailable — silently no-op, button remains a no-cost affordance
    }
  }

  return (
    <div className="relative group my-3 rounded-lg bg-navy-deep overflow-hidden">
      <pre className="overflow-x-auto p-4 pr-16 text-[13px] leading-relaxed font-mono text-slate-100">
        {content}
      </pre>
      <button
        type="button"
        onClick={copy}
        className="absolute top-2.5 right-2.5 rounded-md border border-white/15 bg-white/5 px-2.5 py-1 text-xs font-medium text-slate-200 hover:bg-white/15 transition-colors duration-150"
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}
