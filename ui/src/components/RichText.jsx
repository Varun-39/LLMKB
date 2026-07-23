import { parseBlocks, splitInline } from '../lib/markdown'
import CodeBlock from './CodeBlock'

function Inline({ text }) {
  return splitInline(text).map((part, i) => {
    if (part.kind === 'code')
      return (
        <code key={i} className="rounded bg-navy/[0.06] px-1.5 py-0.5 font-mono text-[0.9em] text-navy">
          {part.text}
        </code>
      )
    if (part.kind === 'bold')
      return (
        <strong key={i} className="font-semibold text-ink">
          {part.text}
        </strong>
      )
    return <span key={i}>{part.text}</span>
  })
}

const headingClass = {
  1: 'text-lg font-semibold text-ink mt-4 mb-2',
  2: 'text-base font-semibold text-ink mt-4 mb-2',
  3: 'text-sm font-semibold uppercase tracking-wide text-muted mt-4 mb-1.5',
  4: 'text-sm font-semibold text-ink mt-3 mb-1',
}

// Renders runbook markdown-lite text: fenced code as CodeBlock, headings,
// lists, and paragraphs as plain prose. Never uses dangerouslySetInnerHTML.
export default function RichText({ text, className = '' }) {
  const blocks = parseBlocks(text)
  return (
    <div className={className}>
      {blocks.map((block, i) => {
        if (block.type === 'code') return <CodeBlock key={i} content={block.content} />
        if (block.type === 'heading')
          return (
            <p key={i} className={headingClass[block.level] || headingClass[4]}>
              <Inline text={block.content} />
            </p>
          )
        if (block.type === 'list')
          return (
            <ul key={i} className="list-disc pl-5 my-2 space-y-1 text-[15px] leading-relaxed">
              {block.items.map((item, j) => (
                <li key={j}>
                  <Inline text={item} />
                </li>
              ))}
            </ul>
          )
        if (block.type === 'table')
          return (
            <div key={i} className="my-3 overflow-x-auto rounded-lg border border-hairline">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-page">
                    {block.header.map((cell, j) => (
                      <th key={j} className="border-b border-hairline px-3 py-2 text-left font-semibold text-ink whitespace-nowrap">
                        <Inline text={cell} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, r) => (
                    <tr key={r} className="border-b border-hairline last:border-0">
                      {row.map((cell, c) => (
                        <td key={c} className="px-3 py-2 align-top text-ink/90">
                          <Inline text={cell} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        return (
          <p key={i} className="text-[15px] leading-relaxed my-2 first:mt-0">
            <Inline text={block.content} />
          </p>
        )
      })}
    </div>
  )
}
