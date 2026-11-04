import MarkdownIt from 'markdown-it'

// Model/document HTML and remote images never become active page content.
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false, maxNesting: 30 })
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

export function renderMarkdown(text: string): string {
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
  return markdown.render(normalized)
}
