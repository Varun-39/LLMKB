// Minimal markdown-lite block parser for runbook text (recommended_action,
// evidence snippets). Recognizes fenced code blocks, headings, list items,
// and paragraphs — enough structure to satisfy Rule 3 (commands rendered as
// code, never body prose) without pulling in a markdown dependency.

export function parseBlocks(text) {
  if (!text) return []
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks = []
  let i = 0
  let paragraph = []
  let list = []

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ type: 'p', content: paragraph.join(' ').trim() })
      paragraph = []
    }
  }
  const flushList = () => {
    if (list.length) {
      blocks.push({ type: 'list', items: list })
      list = []
    }
  }

  while (i < lines.length) {
    const line = lines[i]

    // ponytail: fences nested under a list item (indented ```) are recognized
    // but flattened out of the list rather than rendered nested — simplest
    // thing that still satisfies Rule 3 (commands always rendered as code).
    const fence = line.match(/^(\s*)```(\w*)\s*$/)
    if (fence) {
      flushParagraph()
      flushList()
      const indent = fence[1]
      const lang = fence[2] || ''
      const closeRe = new RegExp(`^${indent}\`\`\`\\s*$`)
      const dedent = new RegExp(`^${indent}`)
      const code = []
      i++
      while (i < lines.length && !closeRe.test(lines[i])) {
        code.push(lines[i].replace(dedent, ''))
        i++
      }
      i++ // skip closing fence
      blocks.push({ type: 'code', lang, content: code.join('\n') })
      continue
    }

    // Pipe table: a "| ... |" row followed by a "|---|---|" separator row.
    const tableRow = (l) => /^\s*\|.*\|\s*$/.test(l)
    const splitRow = (l) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
    if (tableRow(line) && i + 1 < lines.length && /^\s*\|?[\s:-]+\|[\s:|-]*\|?\s*$/.test(lines[i + 1])) {
      flushParagraph()
      flushList()
      const header = splitRow(line)
      i += 2 // skip header + separator
      const rows = []
      while (i < lines.length && tableRow(lines[i])) {
        rows.push(splitRow(lines[i]))
        i++
      }
      blocks.push({ type: 'table', header, rows })
      continue
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/)
    if (heading) {
      flushParagraph()
      flushList()
      blocks.push({ type: 'heading', level: heading[1].length, content: heading[2].trim() })
      i++
      continue
    }

    const listItem = line.match(/^\s*(?:[-*]|\d+\.)\s+(.*)$/)
    if (listItem) {
      flushParagraph()
      list.push(listItem[1].trim())
      i++
      continue
    }

    if (line.trim() === '') {
      flushParagraph()
      flushList()
      i++
      continue
    }

    flushList()
    paragraph.push(line.trim())
    i++
  }
  flushParagraph()
  flushList()
  return blocks
}

// Splits inline text on `code` spans and **bold** spans into
// [{kind:'text'|'code'|'bold', text}, ...]
export function splitInline(text) {
  const tokens = []
  const re = /`([^`]+)`|\*\*([^*]+)\*\*/g
  let last = 0
  let m
  while ((m = re.exec(text))) {
    if (m.index > last) tokens.push({ kind: 'text', text: text.slice(last, m.index) })
    if (m[1] !== undefined) tokens.push({ kind: 'code', text: m[1] })
    else tokens.push({ kind: 'bold', text: m[2] })
    last = re.lastIndex
  }
  if (last < text.length) tokens.push({ kind: 'text', text: text.slice(last) })
  return tokens
}
