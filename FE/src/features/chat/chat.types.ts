export interface Source {
  source_file: string
  source_url: string
  fetched_date: string
  topic_group: string
  title: string
  content: string
  note: string
  score: number
}
export interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  created_at: string
  mode: 'user' | 'retrieval_only' | 'llm'
  sources: Source[]
}
export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
}
export interface Conversation extends ConversationSummary {
  messages: Message[]
}
export interface Health {
  status: string
  source_count: number
  retrieval: string
  llm_configured: boolean
}
