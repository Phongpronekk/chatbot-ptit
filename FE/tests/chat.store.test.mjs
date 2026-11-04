import assert from 'node:assert/strict'
import { after, before, beforeEach, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createPinia, setActivePinia } from 'pinia'
import { createServer } from 'vite'

let server, useChatStore, api, store, calls, saved
const timestamp = new Date().toISOString()
const conversation = (id = 'chat-a') => ({
  id, title: 'Chat', created_at: timestamp, updated_at: timestamp, messages: [], documents: [],
})
const file = (name = 'report.pdf') => new File(['test document'], name, { type: 'application/pdf' })
const metadata = name => ({
  id: crypto.randomUUID(), filename: name, size: 13, characters: 13, chunk_count: 1,
  created_at: timestamp, expires_at: new Date(Date.now() + 7_200_000).toISOString(),
})

before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('..', import.meta.url)), configFile: false, appType: 'custom',
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
  })
  api = (await server.ssrLoadModule('/src/features/chat/chat.service.ts')).chatApi
  useChatStore = (await server.ssrLoadModule('/src/features/chat/chat.store.ts')).useChatStore
})
after(async () => { await server?.close() })

beforeEach(() => {
  setActivePinia(createPinia())
  store = useChatStore()
  store.active = conversation()
  calls = []
  saved = null
  api.create = async () => { calls.push(['create']); return conversation() }
  api.upload = async (id, uploaded) => {
    calls.push(['upload', id, uploaded.name])
    return metadata(uploaded.name)
  }
  api.send = async (id, text, requestId, documentIds, attachmentIds, scope) => {
    calls.push(['send', id, text, requestId, documentIds, attachmentIds, scope])
    const current = JSON.parse(JSON.stringify(store.active))
    saved = { ...current, messages: [...current.messages, {
      id: crypto.randomUUID(), role: 'user', text, created_at: timestamp, mode: 'user', sources: [],
      attachments: current.documents.filter(doc => attachmentIds.includes(doc.id))
        .map(({ id, filename, size }) => ({ id, filename, size })),
    }, {
      id: crypto.randomUUID(), role: 'assistant', text: 'Answer', created_at: timestamp,
      mode: 'llm', sources: [], attachments: [],
    }] }
    return saved
  }
  api.list = async () => [saved ?? conversation()]
  api.get = async () => saved ?? conversation('chat-b')
  api.health = async () => ({ status: 'ok', source_count: 0, retrieval: 'lexical', llm_configured: false })
})

test('selecting and removing a draft file performs no upload or chat creation', async () => {
  store.active = null
  store.queueFiles([file()])
  assert.equal(store.draftAttachments.length, 1)
  assert.equal(store.active, null)
  assert.deepEqual(calls, [])
  await store.removeDraftAttachment(store.draftAttachments[0].id)
  assert.equal(store.draftAttachments.length, 0)
  assert.deepEqual(calls, [])
})

test('sending moves the file into the pending bubble and keeps it with the saved user message', async () => {
  let finishUpload
  api.upload = async () => new Promise(resolve => { finishUpload = () => resolve(metadata('report.pdf')) })
  store.queueFiles([file()])
  const operation = store.send('Summarize this report')
  assert.equal(store.draftAttachments.length, 0)
  assert.equal(store.pendingMessage.attachments[0].filename, 'report.pdf')
  assert.equal(store.uploadingName, 'report.pdf')
  finishUpload()
  await operation
  assert.equal(store.pendingMessage, null)
  assert.equal(store.draftAttachments.length, 0)
  assert.equal(store.active.messages[0].attachments[0].filename, 'report.pdf')
  assert.equal(store.contextDocuments.length, 1)
  await store.load()
  assert.equal(store.active.messages[0].attachments.length, 1)
  assert.equal(store.draftAttachments.length, 0)
})

test('a file can be sent without typing a question', async () => {
  store.queueFiles([file()])
  await store.send('')
  const sent = calls.find(call => call[0] === 'send')
  assert.match(sent[2], /Tóm tắt/)
  assert.equal(sent[5].length, 1)
  assert.equal(store.active.messages[0].attachments.length, 1)
})

test('partial upload failure restores files and text and retries only the failed upload', async () => {
  const upload = api.upload
  let failed = false
  api.upload = async (id, uploaded) => {
    if (uploaded.name === 'second.pdf' && !failed) {
      failed = true
      calls.push(['failed-upload', id, uploaded.name])
      throw new Error('Upload failed')
    }
    return upload(id, uploaded)
  }
  store.queueFiles([file('first.pdf'), file('second.pdf')])
  await store.send('Compare the files')
  assert.equal(store.draftAttachments.length, 2)
  assert.equal(store.draftToRestore.text, 'Compare the files')
  assert.equal(store.active.messages.length, 0)
  assert.equal(store.contextDocuments.length, 0)
  await store.send('Compare the files')
  assert.equal(calls.filter(call => call[0] === 'upload' && call[2] === 'first.pdf').length, 1)
  assert.equal(store.active.messages[0].attachments.length, 2)
  assert.equal(store.draftAttachments.length, 0)
})

test('retry after a message failure reuses the uploaded file and request ID', async () => {
  const send = api.send
  let failedRequest
  api.send = async (...args) => {
    if (!failedRequest) {
      failedRequest = args[2]
      throw new Error('LLM unavailable')
    }
    return send(...args)
  }
  store.queueFiles([file()])
  await store.send('A question')
  assert.equal(store.draftAttachments.length, 1)
  await store.send('A question')
  assert.equal(calls.filter(call => call[0] === 'upload').length, 1)
  assert.equal(calls.find(call => call[0] === 'send')[3], failedRequest)
  assert.equal(store.draftAttachments.length, 0)
})

test('follow-up questions reuse context without reattaching the file or pinning it to the input', async () => {
  store.queueFiles([file()])
  await store.send('Read this file')
  await store.send('What about the eligibility?')
  const sends = calls.filter(call => call[0] === 'send')
  assert.deepEqual(sends[1][4], sends[0][4])
  assert.deepEqual(sends[1][5], [])
  assert.equal(sends[0][6], 'documents')
  assert.equal(sends[1][6], 'auto')
  assert.equal(store.sourceScope, 'auto')
  assert.equal(store.active.messages[2].attachments.length, 0)
  assert.equal(store.draftAttachments.length, 0)
  store.sourceScope = 'knowledge'
  await store.send('A PTIT question')
  assert.deepEqual(calls.filter(call => call[0] === 'send')[2][4], [])
  assert.equal(store.sourceScope, 'auto')
})

test('new uploads replace the active file batch rather than mixing every previously uploaded file', async () => {
  store.queueFiles([file('first.pdf')])
  await store.send('Summarize first file')
  const firstId = store.active.messages[0].attachments[0].id
  store.queueFiles([file('second.pdf')])
  await store.send('Summarize second file')
  const secondId = store.active.messages[2].attachments[0].id
  assert.notEqual(firstId, secondId)
  const sends = calls.filter(call => call[0] === 'send')
  assert.deepEqual(sends[1][4], [secondId])
  assert.deepEqual(store.contextDocuments.map(doc => doc.id), [secondId])
  await store.send('ktx')
  assert.equal(calls.filter(call => call[0] === 'send')[2][6], 'auto')
})

test('switching conversations clears unsent files and does not use files from the previous chat', async () => {
  store.queueFiles([file()])
  await store.select('chat-b')
  assert.equal(store.draftAttachments.length, 0)
  await store.send('New question')
  const sent = calls.find(call => call[0] === 'send')
  assert.equal(sent[1], 'chat-b')
  assert.deepEqual(sent[4], [])
  assert.deepEqual(sent[5], [])
})

test('invalid selections leave existing drafts intact and never upload', () => {
  store.queueFiles([file()])
  store.queueFiles([file('program.exe')])
  assert.equal(store.draftAttachments.length, 1)
  assert.ok(store.error)
  assert.deepEqual(calls, [])
})
