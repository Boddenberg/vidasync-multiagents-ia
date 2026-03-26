#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vidasync_multiagents_ia.config import get_settings  # noqa: E402
from vidasync_multiagents_ia.observability import setup_logging  # noqa: E402
from vidasync_multiagents_ia.rag.service import NutritionRagService  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest nutrition knowledge documents into the local RAG index.",
    )
    parser.add_argument(
        "--docs-dir",
        default="knowledge",
        help="Directory containing the nutrition knowledge documents (default: knowledge).",
    )
    parser.add_argument(
        "--query",
        default="",
        help="Optional validation query to run after ingestion.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=4,
        help="Maximum number of context documents when validating with --query (default: 4).",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    docs_dir = Path(args.docs_dir).resolve()
    if not docs_dir.exists() or not docs_dir.is_dir():
        print(f"Error: docs dir not found: {docs_dir}", file=sys.stderr)
        return 2
    if args.top_k <= 0:
        print("Error: --top-k must be greater than zero.", file=sys.stderr)
        return 2

    base_settings = get_settings()
    settings = base_settings.model_copy(update={"vidasync_docs_dir": str(docs_dir)})
    setup_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        json_pretty=settings.log_json_pretty,
    )
    logger = logging.getLogger(__name__)

    logger.info(
        "rag.cli.started",
        extra={
            "emoji": "🚀",
            "docs_dir": str(docs_dir),
            "query_present": bool(args.query.strip()),
            "top_k": args.top_k,
        },
    )

    service = NutritionRagService(settings=settings)
    summary = service.ingest(force_rebuild=True)
    summary_payload = {
        "docs_dir": str(docs_dir),
        "total_sources": summary.total_sources,
        "total_chunks": summary.total_chunks,
        "embedder_name": summary.embedder_name,
        "vector_dimensions": summary.vector_dimensions,
    }
    logger.info(
        "rag.cli.ingest.completed",
        extra={"emoji": "✅", **summary_payload},
    )
    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))

    query = args.query.strip()
    if not query:
        return 0

    context, docs = service.build_context(query=query, top_k=args.top_k)
    validation_payload = {
        "query": query,
        "top_k": args.top_k,
        "documents_found": len(docs),
        "context_chars": len(context),
        "source_paths": [str(doc.metadata.get("source_path") or "") for doc in docs],
    }
    logger.info(
        "rag.cli.validation.completed",
        extra={"emoji": "🔎", **validation_payload},
    )
    print(json.dumps(validation_payload, ensure_ascii=False, indent=2))
    if context:
        print("\n=== CONTEXT PREVIEW ===")
        print(context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
