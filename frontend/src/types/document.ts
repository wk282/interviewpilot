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
  created_at: string
}
