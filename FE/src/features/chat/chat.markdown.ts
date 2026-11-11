import MarkdownIt from 'markdown-it'
import type { Source } from './chat.types'

// Model/document HTML and remote images never become active page content.
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: true, maxNesting: 30 })
markdown.linkify.set({ fuzzyLink: false, fuzzyEmail: false })
const validateLink = markdown.validateLink.bind(markdown)
markdown.validateLink = value => {
  if (!validateLink(value)) return false
  try { return ['https:', 'http:', 'mailto:'].includes(new URL(value).protocol) }
  catch { return false }
}
markdown.renderer.rules.link_open = (tokens, index, options, _env, renderer) => {
  tokens[index]!.attrSet('target', '_blank')
  tokens[index]!.attrSet('rel', 'noopener noreferrer')
  return renderer.renderToken(tokens, index, options)
}
markdown.renderer.rules.image = (tokens, index) => markdown.utils.escapeHtml(tokens[index]?.content ?? '')

type AnswerLinks = {
  citations: (string | undefined)[]
  files: Map<string, string | null>
  mentions: RegExp
}

function httpUrl(value: string) {
  if (!/^https?:\/\//i.test(value)) return undefined
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined
  } catch { return undefined }
}

function answerLinks(sources: readonly Source[]): AnswerLinks {
  const files = new Map<string, string | null>()
  function addFile(value: string) {
    const href = httpUrl(value)
    if (!href) return
    try {
      const filename = decodeURIComponent(new URL(href).pathname.split('/').pop() ?? '').toLowerCase()
      if (!/\.(?:pdf|docx?|xlsx?|pptx?|csv|txt|zip|rar)$/i.test(filename)) return
      if (!files.has(filename)) files.set(filename, href)
      else if (files.get(filename) !== href) files.set(filename, null)
    } catch { /* An invalid percent escape cannot identify a filename. */ }
  }
  for (const source of sources) {
    addFile(source.source_url)
    for (const token of markdown.parse(source.content, {})) {
      for (const child of token.children ?? []) {
        if (child.type === 'link_open') addFile(String(child.attrGet('href') ?? ''))
      }
    }
  }
  const names = [...files.keys()].sort((a, b) => b.length - a.length)
    .map(name => name.replace(/[.*+?^$(){}|[\]\\]/g, '\\$&'))
  const filenames = names.length
    ? '|(?<![\\p{L}\\p{N}_.-])(?:' + names.join('|') + ')(?![\\p{L}\\p{N}_-]|\\.[\\p{L}\\p{N}])'
    : ''
  const mentions = new RegExp('\\[(\\d+)\\]' + filenames, 'giu')
  return { citations: sources.map(source => httpUrl(source.source_url)), files, mentions }
}

markdown.core.ruler.push('answer_links', state => {
  const links = state.env?.answerLinks as AnswerLinks | undefined
  for (const token of state.tokens) {
    if (!token.children) continue
    let linkDepth = 0
    token.children = token.children.flatMap(child => {
      if (child.type === 'link_open') linkDepth++
      if (child.type === 'link_close') linkDepth--
      if (linkDepth || !['text', 'code_inline'].includes(child.type)) return [child]

      const result: (typeof child)[] = []
      function link(label: typeof child, href: string) {
        const open = new state.Token('link_open', 'a', 1)
        open.attrSet('href', href)
        result.push(open, label, new state.Token('link_close', 'a', -1))
      }
      if (child.type === 'code_inline') {
        const href = httpUrl(child.content) ?? links?.files.get(child.content.toLowerCase())
        if (href) link(child, href)
        return href ? result : [child]
      }
      if (!links) return [child]

      function plain(content: string) {
        const label = new state.Token('text', '', 0)
        label.content = content
        return label
      }
      let end = 0
      for (const match of child.content.matchAll(links.mentions)) {
        const href = match[1] ? links.citations[Number(match[1]) - 1] : links.files.get(match[0].toLowerCase())
        if (!href) continue
        if (match.index > end) result.push(plain(child.content.slice(end, match.index)))
        link(plain(match[0]), href)
        end = match.index + match[0].length
      }
      if (!end) return [child]
      if (end < child.content.length) result.push(plain(child.content.slice(end)))
      return result
    })
  }
})

export function renderMarkdown(text: string, sources: readonly Source[] = []): string {
  // Normalize exported list indentation while preserving fenced code verbatim.
  let fence = ''
  const normalized = text.split('\n').map(line => {
    const marker = line.match(/^ {0,3}(`{3,}|~{3,})/)
    if (marker) {
      if (!fence) fence = marker[1]!
      else if (marker[1]![0] === fence[0] && marker[1]!.length >= fence.length && !line.slice(marker[0].length).trim()) fence = ''
      return line
    }
    return fence ? line : line.replace(/^(?:(?:&#x20;|&#32;|&nbsp;)|[ \t])+(?=[*\-\d>])/gi,
      indent => indent.replace(/&#x20;|&#32;|&nbsp;/gi, ' '))
  }).join('\n')
  return markdown.render(normalized, sources.length ? { answerLinks: answerLinks(sources) } : {})
}
