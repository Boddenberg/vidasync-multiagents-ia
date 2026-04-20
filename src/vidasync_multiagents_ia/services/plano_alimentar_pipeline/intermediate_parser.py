import re
from typing import Any

from vidasync_multiagents_ia.core import normalize_pt_text
from vidasync_multiagents_ia.schemas import ItemAlimentarPlano, OpcaoRefeicaoPlano, RefeicaoPlano
from vidasync_multiagents_ia.services.plano_alimentar_pipeline.preprocessor import is_noise_food_text

_HEADING_ALIASES: dict[str, tuple[str, ...]] = {
    "cafe_da_manha": ("desjejum", "cafe da manha"),
    "lanche_da_manha": ("colacao", "lanche da manha"),
    "almoco": ("almoco",),
    "lanche_da_tarde": ("lanche da tarde",),
    "jantar": ("jantar",),
    "ceia": ("ceia",),
    "pre_treino": ("pre treino", "pre-treino"),
    "pos_treino": ("pos treino", "pos-treino"),
}

_QTD_ALIMENTO_PATTERN = re.compile(
    r"(?is)^qtd:\s*(?P<qtd>.+?)(?:\s*\|\s*alimento:\s*(?P<alimento>.+))?$"
)
_TIME_PATTERN = re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d\b")


def extract_deterministic_meal_sections(texto: str) -> list[RefeicaoPlano]:
    # Converte texto normalizado em refeicoes estruturadas sem depender de LLM.
    linhas = _normalize_lines(texto)
    if not linhas:
        return []

    section_order: list[str] = []
    section_lines: dict[str, list[str]] = {}
    section_hours: dict[str, str] = {}
    current_section: str | None = None

    for line in linhas:
        heading = _parse_heading(line)
        if heading is not None:
            nome_refeicao, horario = heading
            current_section = nome_refeicao
            if nome_refeicao not in section_lines:
                section_order.append(nome_refeicao)
                section_lines[nome_refeicao] = []
            if horario and nome_refeicao not in section_hours:
                section_hours[nome_refeicao] = horario
            continue

        if current_section is None:
            continue

        if current_section not in section_hours and _is_time_only_line(line):
            section_hours[current_section] = line
            continue

        section_lines[current_section].append(line)

    refeicoes: list[RefeicaoPlano] = []
    for nome_refeicao in section_order:
        itens = _extract_items_from_section_lines(section_lines.get(nome_refeicao, []))
        if not itens:
            continue
        refeicoes.append(
            RefeicaoPlano(
                nome_refeicao=nome_refeicao,
                horario=section_hours.get(nome_refeicao),
                opcoes=[
                    OpcaoRefeicaoPlano(
                        titulo="opcao 1",
                        itens=itens,
                        observacoes="extraido_por_parser_qtd_alimento",
                        origem_dado="deterministico_texto",
                    )
                ],
                observacoes="extraido_de_texto_normalizado",
                origem_dado="deterministico_texto",
            )
        )

    return refeicoes


def _extract_items_from_section_lines(lines: list[str]) -> list[ItemAlimentarPlano]:
    items: list[ItemAlimentarPlano] = []
    signatures: set[tuple[str, str]] = set()
    for raw_line in lines:
        parsed = _parse_qtd_alimento_line(raw_line)
        if not parsed:
            continue
        quantidade_texto, alimento = parsed
        if is_noise_food_text(alimento):
            continue

        signature = (_normalize_for_match(quantidade_texto), _normalize_for_match(alimento))
        if signature in signatures:
            continue
        signatures.add(signature)

        quantidade_valor, unidade, quantidade_gramas = _parse_quantity_fields(quantidade_texto)
        items.append(
            ItemAlimentarPlano(
                alimento=alimento,
                quantidade_texto=quantidade_texto,
                quantidade_valor=quantidade_valor,
                unidade=unidade,
                quantidade_gramas=quantidade_gramas,
                origem_dado="deterministico_texto",
                precisa_revisao=quantidade_gramas is None,
                motivo_revisao="Quantidade em gramas nao definida." if quantidade_gramas is None else None,
            )
        )
    return items


def _parse_qtd_alimento_line(line: str) -> tuple[str, str] | None:
    text = line.strip()
    if not text:
        return None

    match = _QTD_ALIMENTO_PATTERN.match(text)
    if not match:
        return None

    quantidade = _clean_text(match.group("qtd"))
    alimento = _clean_text(match.group("alimento"))
    if not quantidade:
        return None
    if not alimento:
        # Exige ALIMENTO explicito para reduzir ambiguidade em orientacoes.
        return None
    return quantidade, alimento


def _parse_heading(line: str) -> tuple[str, str | None] | None:
    text = line.strip()
    if not text:
        return None

    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()

    normalized = _normalize_for_match(text)
    normalized_no_time = _TIME_PATTERN.sub("", normalized).strip(" :-")

    for canonical, aliases in _HEADING_ALIASES.items():
        for alias in aliases:
            if normalized_no_time == alias:
                time_match = _TIME_PATTERN.search(text)
                return canonical, (time_match.group(0) if time_match else None)
    return None


def _is_time_only_line(text: str) -> bool:
    return bool(re.fullmatch(r"\s*([01]?\d|2[0-3]):[0-5]\d\s*", text))


def _parse_quantity_fields(quantidade_texto: str) -> tuple[float | None, str | None, float | None]:
    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|und|unid|unidade)\b",
        quantidade_texto,
        flags=re.IGNORECASE,
    )
    if not match:
        return None, None, None

    valor = _to_optional_float(match.group(1))
    unidade = match.group(2).lower()
    if valor is None:
        return None, unidade, None
    if unidade == "kg":
        return valor, unidade, round(valor * 1000.0, 4)
    if unidade == "g":
        return valor, unidade, valor
    return valor, unidade, None


def _normalize_lines(texto: str) -> list[str]:
    content = texto.replace("```", "")
    lines: list[str] = []
    for raw_line in content.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if line:
            lines.append(line)
    return lines


def _normalize_for_match(text: str) -> str:
    return normalize_pt_text(_fix_common_mojibake(text))


def _fix_common_mojibake(text: str) -> str:
    if "Ã" not in text and "Â" not in text:
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return text


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip(" .;:")


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text or text in {".", "-", "-."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None
