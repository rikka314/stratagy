export function safeMarkdownHref(value) {
  const href = String(value).trim()
  return /^(https?:|mailto:|#|\.\.?\/|\/)/i.test(href) ? href : null
}

export function markdownBlocks(text) {
  const lines = String(text).replace(/\r/g, '').split('\n')
  const blocks = []
  const beginsBlock = (line, next = '') => !line.trim() || /^```/.test(line) || /^#{1,6}\s+/.test(line) || /^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line) || /^>\s?/.test(line) || (/\|/.test(line) && /^\s*\|?\s*:?-{3,}/.test(next))
  for (let index = 0; index < lines.length;) {
    if (!lines[index].trim()) { index += 1; continue }
    if (/^```/.test(lines[index])) {
      const language = lines[index].slice(3).trim()
      const body = []
      index += 1
      while (index < lines.length && !/^```/.test(lines[index])) body.push(lines[index++])
      if (index < lines.length) index += 1
      blocks.push({ type: 'code', language, body: body.join('\n') })
      continue
    }
    const heading = lines[index].match(/^(#{1,6})\s+(.+)$/)
    if (heading) { blocks.push({ type: 'heading', level: heading[1].length, body: heading[2] }); index += 1; continue }
    if (/\|/.test(lines[index]) && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1] || '')) {
      const cells = (line) => line.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim())
      const head = cells(lines[index]); index += 2
      const rows = []
      while (index < lines.length && /\|/.test(lines[index]) && lines[index].trim()) rows.push(cells(lines[index++]))
      blocks.push({ type: 'table', head, rows })
      continue
    }
    const list = lines[index].match(/^([-*]|\d+\.)\s+(.+)$/)
    if (list) {
      const ordered = /\d+\./.test(list[1]); const items = []
      while (index < lines.length) {
        const item = lines[index].match(ordered ? /^\d+\.\s+(.+)$/ : /^[-*]\s+(.+)$/)
        if (!item) break
        items.push(item[1]); index += 1
      }
      blocks.push({ type: ordered ? 'ol' : 'ul', items })
      continue
    }
    if (/^>\s?/.test(lines[index])) {
      const quote = []
      while (index < lines.length && /^>\s?/.test(lines[index])) quote.push(lines[index++].replace(/^>\s?/, ''))
      blocks.push({ type: 'quote', body: quote.join(' ') })
      continue
    }
    const paragraph = [lines[index++].trim()]
    while (index < lines.length && !beginsBlock(lines[index], lines[index + 1])) paragraph.push(lines[index++].trim())
    blocks.push({ type: 'paragraph', body: paragraph.join(' ') })
  }
  return blocks
}
