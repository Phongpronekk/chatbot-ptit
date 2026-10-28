export interface Source {
  source_file: string
  source_url: string
  publish_date?: string
  score_type?: 'cosine_similarity' | 'bm25'
  semantic_score?: number | null
  lexical_score?: number | null
  fusion_score?: number | null
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
  llm_provider?: string
  llm_model?: string
  embedding_model?: string | null
  indexed_chunks?: number
  retrieval_warning?: string | null
}
