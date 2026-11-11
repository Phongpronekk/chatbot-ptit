import { afterEach, describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import MessageBubble from '../../src/features/chat/components/MessageBubble.vue'
import type { Message, Source } from '../../src/features/chat/chat.types'

const wrappers: VueWrapper[] = []
function bubble(url: string) {
  const source: Source = { source_file: 'fixture.md', source_url: url, fetched_date: '2026-10-29',
    topic_group: 'Fixture', title: 'Nguồn fixture', content: 'Đoạn trích fixture', note: '', score: 1 }
  const message: Message = { id: 'fixture', role: 'assistant', text: 'Nội dung fixture',
    created_at: '2026-11-10T17:00:00Z', mode: 'retrieval_only', sources: [source], attachments: [] }
  const wrapper = mount(MessageBubble, { props: { message } })
  wrappers.push(wrapper)
  return wrapper
}
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()) })

describe('MessageBubble official source URL safety', () => {
  it('FE-BUBBLE-001 | Cho phép https và bảo vệ tab mới', () => {
    const link = bubble('https://ptit.edu.vn/').get('a')
    expect(link.attributes('href')).toBe('https://ptit.edu.vn/')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toBe('noopener noreferrer')
  })
  it('FE-BUBBLE-002 | Cho phép http', () => {
    expect(bubble('http://lib.ptit.edu.vn/').get('a').attributes('href')).toBe('http://lib.ptit.edu.vn/')
  })
  it('FE-BUBBLE-003 | Chặn javascript kể cả hoa thường và khoảng trắng', () => {
    for (const url of ['javascript:alert(1)', 'JaVaScRiPt:alert(1)', '  javascript:alert(1)']) {
      expect(bubble(url).find('a').exists()).toBe(false)
    }
  })
  it('FE-BUBBLE-004 | Chặn data/file/ftp/mailto và URL tương đối/sai', () => {
    for (const url of ['data:text/html,<script>alert(1)</script>', 'file:///etc/passwd',
      'ftp://example.org/', 'mailto:a@example.org', '/relative', '//example.org/', '', '%%%']) {
      expect(bubble(url).find('a').exists()).toBe(false)
    }
  })
})
