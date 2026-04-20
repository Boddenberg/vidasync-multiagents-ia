import json
import re
from pathlib import Path
from typing import Any

from vidasync_multiagents_ia.rag.models import RagSourceDocument

_JSON_BATCH_SIZE = 100
_JSON_BATCH_THRESHOLD = 25


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
    if len(rows) > _JSON_BATCH_THRESHOLD:
        return _load_json_batches(path=path, rows=rows)

    sources: list[RagSourceDocument] = []
    for index, row in enumerate(rows, start=1):
        title = _extract_json_row_title(row, fallback=f"{path.stem}_{index}")
        content = _extract_json_row_content(row)
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


def _load_json_batches(*, path: Path, rows: list[dict[str, Any]]) -> list[RagSourceDocument]:
    sources: list[RagSourceDocument] = []
    for batch_index, batch in enumerate(_chunk_rows(rows, size=_JSON_BATCH_SIZE), start=1):
        lines = [_extract_json_row_content(row) for row in batch]
        compact_lines = [line for line in lines if line]
        if not compact_lines:
            continue
        source_id = f"{_slugify(path.stem)}_batch_{batch_index}"
        title = f"{path.stem} batch {batch_index}"
        sources.append(
            RagSourceDocument(
                source_id=source_id,
                source_path=str(path),
                title=title,
                content=_clean_text("\n".join(f"- {line}" for line in compact_lines)),
                metadata={
                    "source_type": "json_batch",
                    "source_path": str(path),
                    "row_count": str(len(batch)),
                },
            )
        )
    return sources


def _normalize_json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if "items" in payload and isinstance(payload["items"], list):
            return [item for item in payload["items"] if isinstance(item, dict)]
        server_data = payload.get("serverData")
        if isinstance(server_data, dict):
            return _normalize_server_data_rows(server_data)
        return [payload]
    return []


def _normalize_server_data_rows(server_data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for collection_name, collection_items in server_data.items():
        if not isinstance(collection_items, list):
            continue
        for item in collection_items:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["_collection"] = str(collection_name)
            rows.append(row)
    return rows


def _extract_json_row_title(row: dict[str, Any], *, fallback: str) -> str:
    nested_source = row.get("source_item") if isinstance(row.get("source_item"), dict) else {}
    nested_response = row.get("response") if isinstance(row.get("response"), dict) else {}
    title = _to_clean_string(
        row.get("title")
        or row.get("titulo")
        or row.get("name")
        or row.get("descricao")
        or nested_source.get("descricao")
        or nested_response.get("nome_alimento")
        or nested_response.get("nome_produto")
    )
    return title or fallback


def _extract_json_row_content(row: dict[str, Any]) -> str | None:
    if _looks_like_catalog_row(row):
        return _build_catalog_row_summary(row)
    return _to_clean_string(
        row.get("text")
        or row.get("content")
        or row.get("conteudo")
        or row.get("descricao")
        or row.get("description")
    )


def _looks_like_catalog_row(row: dict[str, Any]) -> bool:
    nested_source = row.get("source_item")
    nested_response = row.get("response")
    return any(
        [
            isinstance(nested_source, dict),
            isinstance(nested_response, dict),
            "table" in row,
            "grupo" in row,
            "marca" in row,
            "slug" in row,
            "_collection" in row,
        ]
    )


def _build_catalog_row_summary(row: dict[str, Any]) -> str | None:
    nested_source = row.get("source_item") if isinstance(row.get("source_item"), dict) else {}
    nested_response = row.get("response") if isinstance(row.get("response"), dict) else {}

    collection = _to_clean_string(row.get("_collection"))
    table = _to_clean_string(row.get("table") or nested_source.get("table") or nested_response.get("fonte"))
    item_name = _extract_json_row_title(row, fallback="")
    group = _to_clean_string(row.get("grupo") or nested_source.get("grupo") or nested_response.get("grupo_alimentar"))
    brand = _to_clean_string(row.get("marca") or nested_source.get("marca") or nested_response.get("marcas"))
    slug = _to_clean_string(row.get("slug") or nested_source.get("slug") or nested_response.get("slug"))
    base_calculo = _to_clean_string(nested_response.get("base_calculo"))
    grams = _to_clean_string(nested_response.get("gramas"))
    per_100g = _format_nutrient_snapshot(nested_response.get("por_100g"))
    adjusted = _format_nutrient_snapshot(nested_response.get("ajustado"))

    parts: list[str] = []
    if collection:
        parts.append(f"Collection: {collection}.")
    if table:
        parts.append(f"Table: {table}.")
    if item_name:
        parts.append(f"Item: {item_name}.")
    if group:
        parts.append(f"Group: {group}.")
    if brand:
        parts.append(f"Brand: {brand}.")
    if slug:
        parts.append(f"Slug: {slug}.")
    if base_calculo:
        parts.append(f"Base: {base_calculo}.")
    if per_100g:
        parts.append(f"Per 100g: {per_100g}.")
    if adjusted:
        adjusted_label = f"Adjusted for {grams} g" if grams else "Adjusted"
        parts.append(f"{adjusted_label}: {adjusted}.")

    summary = " ".join(parts).strip()
    return summary or None


def _format_nutrient_snapshot(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None

    labels = (
        ("energia_kcal", "energia_kcal"),
        ("proteina_g", "proteina_g"),
        ("carboidratos_g", "carboidratos_g"),
        ("lipidios_g", "lipidios_g"),
        ("fibra_g", "fibra_g"),
    )
    metrics: list[str] = []
    for key, label in labels:
        raw = value.get(key)
        if raw is None:
            continue
        metrics.append(f"{label}={raw}")
    return ", ".join(metrics) if metrics else None


def _chunk_rows(rows: list[dict[str, Any]], *, size: int) -> list[list[dict[str, Any]]]:
    if size <= 0:
        return [rows]
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def _to_clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_text(value: str) -> str:
    # Limpeza leve para preservar contexto sem carregar ruido de OCR/formatacao.
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _slugify(value: str) -> str:
    compact = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_")
    return compact.lower() or "source"
