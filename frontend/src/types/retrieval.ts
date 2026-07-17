export type RetrievalProfile =
  | 'VECTOR'
  | 'VECTOR_TRIGRAM'
  | 'VECTOR_RERANK'
  | 'VECTOR_TRIGRAM_RERANK'
  | 'VECTOR_BM25'
  | 'VECTOR_BM25_RERANK'
  | 'VECTOR_TRIGRAM_BM25'
  | 'VECTOR_TRIGRAM_BM25_RERANK'

export interface RetrievalResult {
  chunk_id: string
  parent_chunk_id: string | null
  document_id: string
  document_version_id: string
  filename: string
  child_content: string
  context: string
  fusion_score: number
  fusion_rank: number
  vector_similarity: number | null
  trigram_similarity: number | null
  bm25_score: number | null
  rerank_score: number | null
  rerank_rank: number | null
  retrieval_sources: Array<'VECTOR' | 'TRIGRAM' | 'BM25'>
  chunk_index: number
  metadata: Record<string, unknown>
}

export interface RetrievalResponse {
  query: string
  embedding_model: string
  retrieval_profile: RetrievalProfile
  result_count: number
  results: RetrievalResult[]
}
