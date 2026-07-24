export interface DocumentItem {
  id: string
  knowledge_base_id: string
  name: string
  status: string
  original_filename: string
  mime_type: string
  file_size: number
  file_hash: string
  version_number: number
  ingestion_job_id: string
  ingestion_status: string
  ingestion_stage: string | null
  ingestion_progress: number
  ingestion_error_code: string | null
  ingestion_error_message: string | null
  created_at: string
}

export interface DocumentParsedContent {
  document_id: string
  original_filename: string
  parser_name: string | null
  parser_version: string | null
  character_count: number
  block_count: number
  page_count: number | null
  page_kinds: string[]
  ocr_processed_pages: number[]
  native_block_count: number
  ocr_block_count: number
  plain_text: string
}
