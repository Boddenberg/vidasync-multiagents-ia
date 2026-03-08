import json
import re
from pathlib import Path
from typing import Any

from vidasync_multiagents_ia.rag.models import RagSourceDocument


class NutritionKnowledgeLoader:
    SUPPORTED_SUFFIXES = {".md", ".txt", ".json"}

    def load_sources(self, *, docs_dir: str) -> list[RagSourceDocument]:
        root = Path(docs_dir)
        if not root.exists() or not root.is_dir():
            return []

        sources: list[RagSourceDocument] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in self.SUPPORTED_SUFFIXES:
                continue
            if path.suffix.lower() in {".md", ".txt"}:
                loaded = _load_text_file(path)
            else:
                loaded = _load_json_file(path)
            sources.extend(loaded)
        return sources


def _load_text_file(path: Path) -> list[RagSourceDocument]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    source_id = _slugify(path.stem)
    return [
        RagSourceDocument(
            source_id=source_id,
            source_path=str(path),
            title=path.stem.replace("_", " ").strip() or "documento",
            content=cleaned,
            metadata={"source_type": path.suffix.lower().replace(".", ""), "source_path": str(path)},
        )
    ]


def _load_json_file(path: Path) -> list[RagSourceDocument]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []

    rows = _normalize_json_rows(payload)
    sources: list[RagSourceDocument] = []
    for index, row in enumerate(rows, start=1):
        title = _to_clean_string(row.get("title") or row.get("titulo") or row.get("name")) or f"{path.stem}_{index}"
        content = _to_clean_string(
            row.get("text")
            or row.get("content")
            or row.get("conteudo")
            or row.get("descricao")
            or row.get("description")
        )
        if not content:
            continue
        source_id = f"{_slugify(path.stem)}_{index}"
        sources.append(
            RagSourceDocument(
                source_id=source_id,
                source_path=str(path),
                title=title,
                content=_clean_text(content),
                metadata={"source_type": "json", "source_path": str(path)},
            )
        )
    return sources


def _normalize_json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if "items" in payload and isinstance(payload["items"], list):
            return [item for item in payload["items"] if isinstance(item, dict)]
        return [payload]
    return []


def _to_clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_text(value: str) -> str:
    # /**** Limpeza leve para preservar contexto sem carregar ruido de OCR/formatacao. ****/
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _slugify(value: str) -> str:
    compact = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_")
    return compact.lower() or "source"
