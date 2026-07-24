"""Add PDF OCR waiting states.

Revision ID: 0017_pdf_ocr_pending_status
Revises: 0016_plan_revision_snapshots
"""

from alembic import op


revision = "0017_pdf_ocr_pending_status"
down_revision = "0016_plan_revision_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_document_status"), "document", type_="check")
    op.create_check_constraint(
        op.f("ck_document_status"),
        "document",
        "status IN ('UPLOADED', 'PROCESSING', 'OCR_PENDING', 'READY', 'FAILED', 'DELETED')",
    )
    op.drop_constraint(
        op.f("ck_document_version_status"), "document_version", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_document_version_status"),
        "document_version",
        "status IN ('UPLOADED', 'PROCESSING', 'OCR_PENDING', 'READY', 'FAILED')",
    )
    op.drop_constraint(
        op.f("ck_ingestion_job_status"), "ingestion_job", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_ingestion_job_status"),
        "ingestion_job",
        "status IN ('PENDING', 'RUNNING', 'WAITING_OCR', 'COMPLETED', 'FAILED', 'CANCELLED')",
    )
    op.drop_constraint(
        op.f("ck_ingestion_job_current_stage"), "ingestion_job", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_ingestion_job_current_stage"),
        "ingestion_job",
        "current_stage IS NULL OR current_stage IN ('VALIDATION', 'PARSING', "
        "'QUALITY_CHECK', 'OCR', 'CLEANING', 'CHUNKING', 'EMBEDDING', 'INDEXING')",
    )
    op.drop_constraint(
        op.f("ck_ingestion_stage_run_stage"), "ingestion_stage_run", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_ingestion_stage_run_stage"),
        "ingestion_stage_run",
        "stage IN ('VALIDATION', 'PARSING', 'QUALITY_CHECK', 'OCR', 'CLEANING', "
        "'CHUNKING', 'EMBEDDING', 'INDEXING')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ingestion_job SET status = 'FAILED', current_stage = 'PARSING', "
        "error_code = 'OCR_WORKER_UNAVAILABLE', "
        "error_message = 'OCR waiting state removed by migration downgrade' "
        "WHERE status = 'WAITING_OCR' OR current_stage = 'OCR'"
    )
    op.execute("UPDATE document_version SET status = 'FAILED' WHERE status = 'OCR_PENDING'")
    op.execute("UPDATE document SET status = 'FAILED' WHERE status = 'OCR_PENDING'")
    op.execute("UPDATE ingestion_stage_run SET stage = 'PARSING' WHERE stage = 'OCR'")

    op.drop_constraint(
        op.f("ck_ingestion_stage_run_stage"), "ingestion_stage_run", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_ingestion_stage_run_stage"),
        "ingestion_stage_run",
        "stage IN ('VALIDATION', 'PARSING', 'QUALITY_CHECK', 'CLEANING', "
        "'CHUNKING', 'EMBEDDING', 'INDEXING')",
    )
    op.drop_constraint(
        op.f("ck_ingestion_job_current_stage"), "ingestion_job", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_ingestion_job_current_stage"),
        "ingestion_job",
        "current_stage IS NULL OR current_stage IN ('VALIDATION', 'PARSING', "
        "'QUALITY_CHECK', 'CLEANING', 'CHUNKING', 'EMBEDDING', 'INDEXING')",
    )
    op.drop_constraint(
        op.f("ck_ingestion_job_status"), "ingestion_job", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_ingestion_job_status"),
        "ingestion_job",
        "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
    )
    op.drop_constraint(
        op.f("ck_document_version_status"), "document_version", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_document_version_status"),
        "document_version",
        "status IN ('UPLOADED', 'PROCESSING', 'READY', 'FAILED')",
    )
    op.drop_constraint(op.f("ck_document_status"), "document", type_="check")
    op.create_check_constraint(
        op.f("ck_document_status"),
        "document",
        "status IN ('UPLOADED', 'PROCESSING', 'READY', 'FAILED', 'DELETED')",
    )
