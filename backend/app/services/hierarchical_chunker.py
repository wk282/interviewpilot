import hashlib
import uuid
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter


@dataclass(frozen=True)
class ChunkRecord:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    chunk_type: str
    chunk_index: int
    content: str
    content_hash: str
    metadata: dict


class HierarchicalChunker:
    def __init__(
        self,
        parent_chunk_size: int = 1200,
        parent_overlap: int = 120,
        child_chunk_size: int = 350,
        child_overlap: int = 50,
    ) -> None:
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "heading_1"),
                ("##", "heading_2"),
                ("###", "heading_3"),
                ("####", "heading_4"),
            ],
            strip_headers=False,
        )
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=parent_chunk_size,
            chunk_overlap=parent_overlap,
            length_function=len,
        )
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=child_chunk_size,
            chunk_overlap=child_overlap,
            length_function=len,
        )

    def chunk(self, text: str, source_name: str, is_markdown: bool) -> list[ChunkRecord]:
        logical_documents = (
            self.markdown_splitter.split_text(text)
            if is_markdown
            else [Document(page_content=text, metadata={})]
        )
        parent_documents = self.parent_splitter.split_documents(logical_documents)
        records: list[ChunkRecord] = []
        child_index = 0

        for parent_index, parent_document in enumerate(parent_documents):
            parent_content = parent_document.page_content.strip()
            if not parent_content:
                continue
            parent_id = uuid.uuid4()
            metadata = {**parent_document.metadata, "source": source_name}
            records.append(
                ChunkRecord(
                    id=parent_id,
                    parent_id=None,
                    chunk_type="PARENT",
                    chunk_index=parent_index,
                    content=parent_content,
                    content_hash=hashlib.sha256(parent_content.encode("utf-8")).hexdigest(),
                    metadata=metadata,
                )
            )

            for child_content in self.child_splitter.split_text(parent_content):
                child_content = child_content.strip()
                if not child_content:
                    continue
                records.append(
                    ChunkRecord(
                        id=uuid.uuid4(),
                        parent_id=parent_id,
                        chunk_type="CHILD",
                        chunk_index=child_index,
                        content=child_content,
                        content_hash=hashlib.sha256(child_content.encode("utf-8")).hexdigest(),
                        metadata=metadata,
                    )
                )
                child_index += 1

        return records
