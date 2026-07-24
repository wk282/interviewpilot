from __future__ import annotations

import argparse
import json
from pathlib import Path

from .metrics import character_error_rate, route_accuracy
from .ocr_backends import PaddleOCRBackend
from .parser import PdfExperimentParser
from .quality import build_quality_report


def run_manifest(manifest_path: Path, *, enable_ocr: bool) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    parser = PdfExperimentParser(
        ocr_backend=PaddleOCRBackend() if enable_ocr else None
    )
    cases: list[dict] = []
    for item in manifest.get("cases", []):
        pdf_path = root / item["pdf"]
        expected_text = (root / item["expected_text"]).read_text(encoding="utf-8")
        parsed = parser.parse(pdf_path)
        actual_routes = [page.kind.value for page in parsed.pages]
        expected_routes = list(item.get("page_kinds", []))
        case = {
            "case_id": item["case_id"],
            "pdf": item["pdf"],
            "character_error_rate": round(
                character_error_rate(expected_text, parsed.plain_text), 6
            ),
            "quality": build_quality_report(parsed),
            "actual_page_kinds": actual_routes,
        }
        if expected_routes:
            case["route_accuracy"] = round(
                route_accuracy(expected_routes, actual_routes), 6
            )
        cases.append(case)
    return {"manifest": str(manifest_path), "case_count": len(cases), "cases": cases}


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="Benchmark isolated PDF parsing")
    argument_parser.add_argument("manifest", type=Path)
    argument_parser.add_argument("--enable-ocr", action="store_true")
    argument_parser.add_argument("--output", type=Path, required=True)
    args = argument_parser.parse_args()
    report = run_manifest(args.manifest, enable_ocr=args.enable_ocr)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
