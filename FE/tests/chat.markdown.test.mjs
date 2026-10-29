import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import vue from '@vitejs/plugin-vue'
import { createServer } from 'vite'

let server, renderMarkdown, MessageBubble
before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('..', import.meta.url)), configFile: false, appType: 'custom',
    plugins: [vue()], server: { middlewareMode: true, hmr: false, ws: false, watch: null },
  })
  renderMarkdown = (await server.ssrLoadModule('/src/features/chat/chat.markdown.ts')).renderMarkdown
  MessageBubble = (await server.ssrLoadModule('/src/features/chat/components/MessageBubble.vue')).default
})
after(async () => { await server?.close() })

test('renders lists, emphasis, code, tables and exported space entities', () => {
  const html = renderMarkdown('**Ký túc xá**&#x20;\n\n* **Đăng ký:** theo thông báo.\n&#x20;   * Xem `ktx.md`.\n\n| Mục | Số lượng |\n| --- | --- |\n| Bài | 3 |')
  assert.match(html, /<strong>Ký túc xá<\/strong>/)
  assert.match(html, /<ul>/)
  assert.match(html, /<code>ktx.md<\/code>/)
  assert.match(html, /<table>/)
  assert.doesNotMatch(html, /&#x20;/)
})

test('raw HTML, entity-obfuscated script links and images never become active content', () => {
  for (const input of [
    '<script>alert(1)</script>', '<img src=x onerror=alert(1)>',
    '[click](javascript:alert%281%29)', '[click](jav&#x61;script:alert%281%29)',
    '[local](file:///C:/Windows/win.ini)', '[data](data:text/html,hello)',
    '![remote](https://example.org/track?private=data)',
    '&#x3c;img src=x onerror=alert(1)&#x3e;',
  ]) {
    const html = renderMarkdown(input)
    assert.doesNotMatch(html, /<(script|img|iframe|object)\b/i)
    assert.doesNotMatch(html, /href="(?:javascript|file|data):/i)
  }
})

test('safe links use protected new tabs and code stays escaped', () => {
  const html = renderMarkdown('[Nguồn](https://ptit.edu.vn/example)\n\n```html\n<script>test</script>\n```')
  assert.match(html, /href="https:\/\/ptit.edu.vn\/example"/)
  assert.match(html, /target="_blank"/)
  assert.match(html, /rel="noopener noreferrer"/)
  assert.match(html, /&lt;script&gt;test&lt;\/script&gt;/)
  assert.match(renderMarkdown('```text\n&#x20;* literal\n```'), /&amp;#x20;\* literal/)
})

test('file sources are grouped once while preserving individual citation numbers', async () => {
  const source = { document_id: 'file', source_file: 'report.docx', source_url: '', title: 'Report',
    location: 'Đoạn 1', content: '**KTX** là từ khóa.', note: 'File tải lên', fetched_date: '2026-10-29',
    topic_group: 'File tải lên', score: 1 }
  const message = { id: 'message', role: 'assistant', text: '**Thông tin** [1], [2].',
    created_at: '2026-10-29T00:00:00Z', mode: 'llm', attachments: [],
    sources: [source, { ...source, location: 'Đoạn 2' }] }
  const html = await renderToString(createSSRApp(MessageBubble, { message }))
  assert.match(html, /<strong>Thông tin<\/strong>/)
  assert.match(html, /\[1, 2\] report.docx/)
  assert.equal((html.match(/report.docx/g) ?? []).length, 1)
  assert.match(html, /\[1\] Đoạn 1/)
  assert.match(html, /\[2\] Đoạn 2/)
  assert.match(html, /Nguồn trả lời: File đã tải lên/)
})

test('user text is kept literal even when assistant text supports Markdown', async () => {
  const message = { id: 'message', role: 'user', text: '**literal** <script>unsafe</script>',
    created_at: '2026-10-29T00:00:00Z', mode: 'user', sources: [], attachments: [] }
  const html = await renderToString(createSSRApp(MessageBubble, { message }))
  assert.match(html, /\*\*literal\*\*/)
  assert.doesNotMatch(html, /<script>/)
})
