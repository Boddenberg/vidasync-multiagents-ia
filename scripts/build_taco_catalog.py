#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vidasync_multiagents_ia.core import ServiceError  # noqa: E402
from vidasync_multiagents_ia.services import TacoOnlineService  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build local TACO catalog by fetching one item at a time from tabelatacoonline.com.br."
    )
    parser.add_argument(
        "--input",
        default="knowledge/banco.json",
        help="Path to source index JSON (default: knowledge/banco.json).",
    )
    parser.add_argument(
        "--output",
        default="knowledge/taco_catalog_full.json",
        help="Path to output JSON (default: knowledge/taco_catalog_full.json).",
    )
    parser.add_argument(
        "--grams",
        type=float,
        default=100.0,
        help="Grams used in TacoOnlineService.get_food (default: 100).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of items to process (0 means all).",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.25,
        help="Delay between requests in seconds (default: 0.25).",
    )
    parser.add_argument(
        "--flush-every",
        type=int,
        default=10,
        help="Flush output to disk every N processed items (default: 10).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Ignore previous output file and rebuild from scratch.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately on first error.",
    )
    return parser


def _read_source_items(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    items = payload.get("serverData", {}).get("taco")
    if not isinstance(items, list):
        raise ValueError("Invalid source file: expected serverData.taco as a list.")
    return [item for item in items if isinstance(item, dict)]


def _read_existing_results(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    entries = payload.get("items")
    if not isinstance(entries, list):
        return {}

    by_slug: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source_item = entry.get("source_item")
        if not isinstance(source_item, dict):
            continue
        slug = str(source_item.get("slug") or "").strip()
        if not slug:
            continue
        by_slug[slug] = entry
    return by_slug


def _entry_error(
    *,
    source_item: dict[str, Any],
    error_type: str,
    message: str,
    status_code: int | None,
    duration_ms: float,
) -> dict[str, Any]:
    return {
        "source_item": source_item,
        "status": "error",
        "duration_ms": round(duration_ms, 4),
        "error": {
            "type": error_type,
            "message": message,
            "status_code": status_code,
        },
    }


def _entry_ok(
    *,
    source_item: dict[str, Any],
    response: dict[str, Any],
    duration_ms: float,
) -> dict[str, Any]:
    return {
        "source_item": source_item,
        "status": "ok",
        "duration_ms": round(duration_ms, 4),
        "response": response,
    }


def _write_output(
    *,
    output_path: Path,
    source_items: list[dict[str, Any]],
    by_slug: dict[str, dict[str, Any]],
    grams: float,
    started_at: datetime,
) -> None:
    ordered_items: list[dict[str, Any]] = []
    ok_count = 0
    error_count = 0
    missing_count = 0

    for source_item in source_items:
        slug = str(source_item.get("slug") or "").strip()
        if not slug:
            missing_count += 1
            continue
        entry = by_slug.get(slug)
        if not entry:
            missing_count += 1
            continue
        ordered_items.append(entry)
        if entry.get("status") == "ok":
            ok_count += 1
        else:
            error_count += 1

    payload = {
        "metadata": {
            "started_at": started_at.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_total_items": len(source_items),
            "output_total_items": len(ordered_items),
            "ok_count": ok_count,
            "error_count": error_count,
            "missing_count": missing_count,
            "grams": grams,
        },
        "items": ordered_items,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def main() -> int:
    args = _build_parser().parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    if args.grams <= 0:
        print("Error: --grams must be > 0.", file=sys.stderr)
        return 2
    if args.delay_seconds < 0:
        print("Error: --delay-seconds must be >= 0.", file=sys.stderr)
        return 2
    if args.flush_every <= 0:
        print("Error: --flush-every must be > 0.", file=sys.stderr)
        return 2
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 2

    source_items = _read_source_items(input_path)
    if args.limit > 0:
        source_items = source_items[: args.limit]

    results_by_slug: dict[str, dict[str, Any]]
    if args.overwrite:
        results_by_slug = {}
    else:
        results_by_slug = _read_existing_results(output_path)

    service = TacoOnlineService()
    started_at = datetime.now(timezone.utc)

    processed = 0
    skipped = 0
    failed = 0

    try:
        for idx, source_item in enumerate(source_items, start=1):
            slug = str(source_item.get("slug") or "").strip()
            if not slug:
                failed += 1
                results_by_slug[f"_missing_slug_{idx}"] = _entry_error(
                    source_item=source_item,
                    error_type="InvalidSourceItem",
                    message="Missing slug in source item.",
                    status_code=None,
                    duration_ms=0.0,
                )
                continue

            if slug in results_by_slug and results_by_slug[slug].get("status") == "ok":
                skipped += 1
                continue

            started = time.perf_counter()
            try:
                response = service.get_food(slug=slug, grams=args.grams)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                results_by_slug[slug] = _entry_ok(
                    source_item=source_item,
                    response=response.model_dump(mode="json", exclude_none=True),
                    duration_ms=elapsed_ms,
                )
            except ServiceError as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                failed += 1
                results_by_slug[slug] = _entry_error(
                    source_item=source_item,
                    error_type=exc.__class__.__name__,
                    message=exc.message,
                    status_code=exc.status_code,
                    duration_ms=elapsed_ms,
                )
                if args.fail_fast:
                    raise
            except Exception as exc:  # noqa: BLE001
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                failed += 1
                results_by_slug[slug] = _entry_error(
                    source_item=source_item,
                    error_type=exc.__class__.__name__,
                    message=str(exc),
                    status_code=None,
                    duration_ms=elapsed_ms,
                )
                if args.fail_fast:
                    raise

            processed += 1
            if processed % args.flush_every == 0:
                _write_output(
                    output_path=output_path,
                    source_items=source_items,
                    by_slug=results_by_slug,
                    grams=args.grams,
                    started_at=started_at,
                )
                print(
                    f"[flush] processed={processed} skipped={skipped} failed={failed} output={output_path}",
                    flush=True,
                )

            if args.delay_seconds > 0:
                time.sleep(args.delay_seconds)

    except KeyboardInterrupt:
        print("\nInterrupted by user. Writing partial output...", file=sys.stderr)
    finally:
        _write_output(
            output_path=output_path,
            source_items=source_items,
            by_slug=results_by_slug,
            grams=args.grams,
            started_at=started_at,
        )

    print(
        (
            f"Done. total_source={len(source_items)} processed={processed} "
            f"skipped={skipped} failed={failed} output={output_path}"
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
