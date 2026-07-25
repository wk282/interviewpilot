CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE app_user (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CONSTRAINT ck_app_user_status CHECK (status IN ('ACTIVE', 'DISABLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_app_user_email UNIQUE (email),
    CONSTRAINT ck_app_user_email_lowercase CHECK (email = LOWER(email))
);

CREATE TABLE workspace (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(20) NOT NULL
        CONSTRAINT ck_workspace_type CHECK (type IN ('PERSONAL', 'ORGANIZATION')),
    created_by UUID NOT NULL REFERENCES app_user(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_workspace_personal_creator
    ON workspace(created_by) WHERE type = 'PERSONAL';
CREATE INDEX idx_workspace_created_by ON workspace(created_by);

CREATE TABLE workspace_member (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'MEMBER'
        CONSTRAINT ck_workspace_member_role
        CHECK (role IN ('OWNER', 'ADMIN', 'HR', 'INTERVIEWER', 'VIEWER', 'MEMBER')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_workspace_member UNIQUE (workspace_id, user_id)
);

CREATE INDEX idx_workspace_member_user_id ON workspace_member(user_id);
CREATE INDEX idx_workspace_member_workspace_role ON workspace_member(workspace_id, role);

CREATE TABLE knowledge_base (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    purpose VARCHAR(50) NOT NULL
        CONSTRAINT ck_knowledge_base_purpose
        CHECK (
            purpose IN (
                'RESUME',
                'PERSONAL_LEARNING',
                'PUBLIC_QUESTION_BANK',
                'ENTERPRISE_QUESTION_BANK',
                'JOB_SPECIFIC',
                'SCORING_RUBRIC',
                'TECHNICAL_STANDARD'
            )
        ),
    visibility VARCHAR(20) NOT NULL DEFAULT 'PRIVATE'
        CONSTRAINT ck_knowledge_base_visibility
        CHECK (visibility IN ('PRIVATE', 'WORKSPACE', 'PUBLIC')),
    created_by UUID NOT NULL REFERENCES app_user(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_knowledge_base_workspace_name UNIQUE (workspace_id, name)
);

CREATE INDEX idx_knowledge_base_workspace_purpose
    ON knowledge_base(workspace_id, purpose);
CREATE INDEX idx_knowledge_base_created_by ON knowledge_base(created_by);
CREATE INDEX idx_knowledge_base_workspace_visibility
    ON knowledge_base(workspace_id, visibility);

CREATE TABLE document (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    knowledge_base_id UUID NOT NULL REFERENCES knowledge_base(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    uploaded_by UUID NOT NULL REFERENCES app_user(id),
    status VARCHAR(20) NOT NULL DEFAULT 'UPLOADED'
        CONSTRAINT ck_document_status
        CHECK (status IN ('UPLOADED', 'PROCESSING', 'READY', 'FAILED', 'DELETED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT ck_document_deleted_at
        CHECK (status = 'DELETED' OR deleted_at IS NULL)
);

CREATE INDEX idx_document_knowledge_base ON document(knowledge_base_id);
CREATE INDEX idx_document_knowledge_base_status
    ON document(knowledge_base_id, status);
CREATE INDEX idx_document_uploaded_by ON document(uploaded_by);
CREATE INDEX idx_document_active_in_knowledge_base
    ON document(knowledge_base_id, created_at DESC)
    WHERE status <> 'DELETED';

CREATE TABLE document_version (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL
        CONSTRAINT ck_document_version_number CHECK (version_number > 0),
    original_filename VARCHAR(255) NOT NULL,
    storage_key VARCHAR(500) NOT NULL,
    mime_type VARCHAR(150) NOT NULL,
    file_size BIGINT NOT NULL
        CONSTRAINT ck_document_version_file_size CHECK (file_size >= 0),
    file_hash VARCHAR(64) NOT NULL,
    parser_name VARCHAR(100),
    parser_version VARCHAR(50),
    parsed_content_key VARCHAR(500),
    quality_report JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'UPLOADED'
        CONSTRAINT ck_document_version_status
        CHECK (status IN ('UPLOADED', 'PROCESSING', 'READY', 'FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_document_version_number UNIQUE (document_id, version_number),
    CONSTRAINT ck_document_version_file_hash
        CHECK (file_hash ~ '^[0-9a-fA-F]{64}$')
);

CREATE INDEX idx_document_version_document_hash
    ON document_version(document_id, file_hash);
CREATE INDEX idx_document_version_status ON document_version(status);
CREATE INDEX idx_document_version_latest
    ON document_version(document_id, version_number DESC);

CREATE TABLE ingestion_job (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_version_id UUID NOT NULL
        REFERENCES document_version(id) ON DELETE CASCADE,
    requested_by UUID NOT NULL REFERENCES app_user(id),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CONSTRAINT ck_ingestion_job_status
        CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    current_stage VARCHAR(50)
        CONSTRAINT ck_ingestion_job_current_stage
        CHECK (
            current_stage IS NULL
            OR current_stage IN (
                'VALIDATION',
                'PARSING',
                'QUALITY_CHECK',
                'CLEANING',
                'CHUNKING',
                'EMBEDDING',
                'INDEXING'
            )
        ),
    progress SMALLINT NOT NULL DEFAULT 0
        CONSTRAINT ck_ingestion_job_progress CHECK (progress BETWEEN 0 AND 100),
    retry_count INTEGER NOT NULL DEFAULT 0
        CONSTRAINT ck_ingestion_job_retry_count CHECK (retry_count >= 0),
    error_code VARCHAR(100),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_ingestion_job_time
        CHECK (
            completed_at IS NULL
            OR started_at IS NULL
            OR completed_at >= started_at
        ),
    CONSTRAINT ck_ingestion_job_completed_progress
        CHECK (status <> 'COMPLETED' OR progress = 100)
);

CREATE INDEX idx_ingestion_job_document_version
    ON ingestion_job(document_version_id, created_at DESC);
CREATE INDEX idx_ingestion_job_status_created
    ON ingestion_job(status, created_at);
CREATE INDEX idx_ingestion_job_requested_by ON ingestion_job(requested_by);
CREATE INDEX idx_ingestion_job_status_stage
    ON ingestion_job(status, current_stage);

CREATE TABLE ingestion_stage_run (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ingestion_job_id UUID NOT NULL REFERENCES ingestion_job(id) ON DELETE CASCADE,
    stage VARCHAR(50) NOT NULL
        CONSTRAINT ck_ingestion_stage_run_stage
        CHECK (
            stage IN (
                'VALIDATION',
                'PARSING',
                'QUALITY_CHECK',
                'CLEANING',
                'CHUNKING',
                'EMBEDDING',
                'INDEXING'
            )
        ),
    attempt_no INTEGER NOT NULL DEFAULT 1
        CONSTRAINT ck_ingestion_stage_run_attempt CHECK (attempt_no > 0),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CONSTRAINT ck_ingestion_stage_run_status
        CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED')),
    metrics JSONB,
    error_code VARCHAR(100),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ingestion_stage_attempt
        UNIQUE (ingestion_job_id, stage, attempt_no),
    CONSTRAINT ck_ingestion_stage_run_time
        CHECK (
            completed_at IS NULL
            OR started_at IS NULL
            OR completed_at >= started_at
        )
);

CREATE INDEX idx_ingestion_stage_run_status ON ingestion_stage_run(status);
CREATE INDEX idx_ingestion_stage_run_job_created
    ON ingestion_stage_run(ingestion_job_id, created_at);
