from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
EVALUATION_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = EVALUATION_ROOT / "manifests" / "corpus_v1.json"
FIXTURE_ROOT = EVALUATION_ROOT / "fixtures" / "documents"
QUESTION_HEADING = re.compile(r"^###\s+Q(?P<number>\d+)\.\s*(?P<title>.+?)\s*$")


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def source_path(source: dict, repository_root: Path = REPOSITORY_ROOT) -> Path:
    return repository_root / Path(*source["source_path"].split("/"))


def fixture_path(source: dict, fixture_root: Path = FIXTURE_ROOT) -> Path:
    return fixture_root / source["fixture_filename"]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sources(manifest: dict, repository_root: Path = REPOSITORY_ROOT) -> list[str]:
    errors: list[str] = []
    for source in manifest["sources"]:
        path = source_path(source, repository_root)
        if not path.is_file():
            errors.append(f"missing source: {source['source_path']}")
            continue
        actual = file_sha256(path)
        if actual != source["sha256"]:
            errors.append(
                f"hash mismatch: {source['source_id']} expected={source['sha256']} actual={actual}"
            )
    return errors


def verify_fixtures(
    manifest: dict,
    fixture_root: Path = FIXTURE_ROOT,
) -> list[str]:
    errors: list[str] = []
    expected_names = {source["fixture_filename"] for source in manifest["sources"]}
    actual_names = {path.name for path in fixture_root.glob("*.md")}
    unexpected_names = sorted(actual_names - expected_names)
    if unexpected_names:
        errors.append(f"unexpected fixtures: {unexpected_names}")
    for source in manifest["sources"]:
        path = fixture_path(source, fixture_root)
        if not path.is_file():
            errors.append(f"missing fixture: {source['fixture_filename']}")
            continue
        actual = file_sha256(path)
        if actual != source["sha256"]:
            errors.append(
                f"fixture hash mismatch: {source['source_id']} "
                f"expected={source['sha256']} actual={actual}"
            )
    return errors


def freeze_sources(
    manifest: dict,
    repository_root: Path = REPOSITORY_ROOT,
    fixture_root: Path = FIXTURE_ROOT,
) -> None:
    errors = verify_sources(manifest, repository_root)
    if errors:
        raise ValueError("\n".join(errors))
    fixture_root.mkdir(parents=True, exist_ok=True)
    expected_names = {source["fixture_filename"] for source in manifest["sources"]}
    for existing in fixture_root.glob("*.md"):
        if existing.name not in expected_names:
            existing.unlink()
    for source in manifest["sources"]:
        shutil.copy2(source_path(source, repository_root), fixture_path(source, fixture_root))


def extract_question_blocks(text: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    current_id: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        match = QUESTION_HEADING.match(line)
        if match:
            if current_id is not None:
                blocks[current_id] = "\n".join(current_lines).strip()
            current_id = f"q{int(match.group('number')):02d}"
            current_lines = [line]
        elif current_id is not None:
            current_lines.append(line)
    if current_id is not None:
        blocks[current_id] = "\n".join(current_lines).strip()
    return blocks


def corpus_question_index(
    manifest: dict,
    fixture_root: Path = FIXTURE_ROOT,
) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for source in manifest["sources"]:
        path = fixture_path(source, fixture_root)
        for question_id, content in extract_question_blocks(path.read_text(encoding="utf-8")).items():
            canonical_id = f"{source['source_id']}:{question_id}"
            index[canonical_id] = {
                "source_id": source["source_id"],
                "question_id": question_id,
                "content": content,
            }
    return index


def resolve_canonical_id(
    source_id: str | None,
    child_content: str,
    context: str,
    question_index: dict[str, dict],
) -> str | None:
    if not source_id:
        return None
    candidates = [
        (canonical_id, item)
        for canonical_id, item in question_index.items()
        if item["source_id"] == source_id
    ]
    for content in (child_content, context):
        for canonical_id, item in candidates:
            heading = item["content"].splitlines()[0].strip()
            if heading and heading in content:
                return canonical_id
    normalized_content = child_content.strip()
    best: tuple[str, int] | None = None
    for canonical_id, item in candidates:
        block = item["content"]
        score = len(normalized_content) if normalized_content and normalized_content in block else 0
        if best is None or score > best[1]:
            best = (canonical_id, score)
    return best[0] if best and best[1] > 0 else None
