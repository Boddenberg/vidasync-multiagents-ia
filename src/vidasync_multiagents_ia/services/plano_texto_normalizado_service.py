import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from openai import APIConnectionError, APIError

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError, normalize_pt_text
from vidasync_multiagents_ia.observability.context import submit_with_context
from vidasync_multiagents_ia.schemas import (
    AgenteNormalizacaoPlanoTexto,
    PlanoTextoNormalizadoResponse,
    PlanoTextoNormalizadoSecao,
)
from vidasync_multiagents_ia.services.image_reference_resolver import (
    resolve_image_reference_to_public_url,
)


class PlanoTextoNormalizadoService:
    def __init__(self, settings: Settings, client: OpenAIClient | None = None) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
        )
        self._logger = logging.getLogger(__name__)

    def normalizar_de_imagens(
        self,
        *,
        imagem_urls: list[str],
        contexto: str = "normalizar_texto_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoTextoNormalizadoResponse:
        self._ensure_openai_api_key()
        if not imagem_urls:
            raise ServiceError("Campo 'imagem_urls' e obrigatorio.", status_code=400)
        imagem_urls_resolvidas = [self._resolve_imagem_url(url) for url in imagem_urls]

        self._logger.info(
            "plano_texto_normalizado.imagens.started",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "total_fontes": len(imagem_urls_resolvidas),
                "modelo": self._settings.openai_model,
            },
        )

        max_workers = min(4, len(imagem_urls_resolvidas))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                submit_with_context(
                    executor,
                    self._normalizar_payload_da_imagem,
                    imagem_url=url,
                    contexto=contexto,
                    idioma=idioma,
                )
                for url in imagem_urls_resolvidas
            ]
            payloads = [future.result() for future in futures]

        response = self._build_response_from_payloads(
            payloads=payloads,
            contexto=contexto,
            idioma=idioma,
            tipo_fonte="imagem",
            total_fontes=len(imagem_urls_resolvidas),
        )
        self._logger.info(
            "plano_texto_normalizado.imagens.completed",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "total_fontes": len(imagem_urls_resolvidas),
                "secoes": len(response.secoes),
                "texto_chars": len(response.texto_normalizado),
            },
        )
        return response

    def normalizar_de_pdf(
        self,
        *,
        pdf_bytes: bytes,
        nome_arquivo: str,
        contexto: str = "normalizar_texto_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoTextoNormalizadoResponse:
        self._ensure_openai_api_key()
        if not pdf_bytes:
            raise ServiceError("Arquivo PDF vazio.", status_code=400)
        if not pdf_bytes.startswith(b"%PDF-"):
            raise ServiceError("Arquivo invalido: envie um PDF valido.", status_code=400)

        self._logger.info(
            "plano_texto_normalizado.pdf.started",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "nome_arquivo": nome_arquivo,
                "pdf_bytes": len(pdf_bytes),
                "modelo": self._settings.openai_model,
            },
        )
        payload = self._normalizar_payload_do_pdf(
            pdf_bytes=pdf_bytes,
            nome_arquivo=nome_arquivo,
            contexto=contexto,
            idioma=idioma,
        )
        response = self._build_response_from_payloads(
            payloads=[payload],
            contexto=contexto,
            idioma=idioma,
            tipo_fonte="pdf",
            total_fontes=1,
        )
        self._logger.info(
            "plano_texto_normalizado.pdf.completed",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "nome_arquivo": nome_arquivo,
                "secoes": len(response.secoes),
                "texto_chars": len(response.texto_normalizado),
            },
        )
        return response

    def normalizar_de_textos(
        self,
        *,
        textos_fonte: list[str],
        contexto: str = "normalizar_texto_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoTextoNormalizadoResponse:
        self._ensure_openai_api_key()
        textos_validos = [texto.strip() for texto in textos_fonte if texto and texto.strip()]
        if not textos_validos:
            raise ServiceError("Campo 'textos_fonte' e obrigatorio.", status_code=400)

        self._logger.info(
            "plano_texto_normalizado.texto.started",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "total_fontes": len(textos_validos),
                "modelo": self._settings.openai_model,
            },
        )

        payloads = [
            self._normalizar_payload_do_texto(
                texto_fonte=texto,
                contexto=contexto,
                idioma=idioma,
            )
            for texto in textos_validos
        ]

        response = self._build_response_from_payloads(
            payloads=payloads,
            contexto=contexto,
            idioma=idioma,
            tipo_fonte="texto_ocr",
            total_fontes=len(textos_validos),
        )
        self._logger.info(
            "plano_texto_normalizado.texto.completed",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "total_fontes": len(textos_validos),
                "secoes": len(response.secoes),
                "texto_chars": len(response.texto_normalizado),
            },
        )
        return response

    def _normalizar_payload_da_imagem(
        self,
        *,
        imagem_url: str,
        contexto: str,
        idioma: str,
    ) -> dict[str, Any]:
        try:
            return self._client.generate_json_from_image(
                model=self._settings.openai_model,
                system_prompt=_build_system_prompt(),
                user_prompt=_build_user_prompt(
                    contexto=contexto,
                    idioma=idioma,
                    tipo_fonte="imagem",
                ),
                image_url=imagem_url,
            )
        except (APIConnectionError, APIError) as exc:
            self._logger.exception("Falha ao normalizar imagem '%s'", imagem_url)
            raise ServiceError("Falha ao normalizar texto da imagem.", status_code=502) from exc
        except ValueError:
            # Fallback: se o modelo nao retornar JSON valido, usa texto semantico bruto.
            texto_fallback = self._client.extract_text_from_image(
                model=self._settings.openai_model,
                system_prompt=(
                    "Voce organiza texto de plano alimentar mantendo a estrutura por refeicoes e itens."
                ),
                user_prompt=(
                    f"Contexto: {contexto}. Idioma: {idioma}. "
                    "Organize o conteudo em secoes textuais com titulos curtos, sem inventar."
                ),
                image_url=imagem_url,
            )
            return {
                "titulo_documento": None,
                "secoes": [
                    {"titulo": "conteudo_principal", "texto": texto_fallback},
                ],
                "texto_normalizado": texto_fallback,
                "observacoes": ["fallback_texto_semantico_por_imagem"],
            }

    def _normalizar_payload_do_pdf(
        self,
        *,
        pdf_bytes: bytes,
        nome_arquivo: str,
        contexto: str,
        idioma: str,
    ) -> dict[str, Any]:
        try:
            return self._client.generate_json_from_pdf(
                model=self._settings.openai_model,
                system_prompt=_build_system_prompt(),
                user_prompt=_build_user_prompt(
                    contexto=contexto,
                    idioma=idioma,
                    tipo_fonte="pdf",
                ),
                pdf_bytes=pdf_bytes,
                filename=nome_arquivo,
            )
        except (APIConnectionError, APIError) as exc:
            self._logger.exception("Falha ao normalizar PDF '%s'", nome_arquivo)
            raise ServiceError("Falha ao normalizar texto do PDF.", status_code=502) from exc
        except ValueError:
            # Fallback: se vier resposta invalida em JSON, usa texto semantico bruto.
            texto_fallback = self._client.extract_text_from_pdf(
                model=self._settings.openai_model,
                system_prompt=(
                    "Voce organiza texto de plano alimentar mantendo a estrutura por refeicoes e itens."
                ),
                user_prompt=(
                    f"Contexto: {contexto}. Idioma: {idioma}. "
                    "Organize o conteudo em secoes textuais com titulos curtos, sem inventar."
                ),
                pdf_bytes=pdf_bytes,
                filename=nome_arquivo,
            )
            return {
                "titulo_documento": None,
                "secoes": [
                    {"titulo": "conteudo_principal", "texto": texto_fallback},
                ],
                "texto_normalizado": texto_fallback,
                "observacoes": ["fallback_texto_semantico_por_pdf"],
            }

    def _normalizar_payload_do_texto(
        self,
        *,
        texto_fonte: str,
        contexto: str,
        idioma: str,
    ) -> dict[str, Any]:
        try:
            return self._client.generate_json_from_text(
                model=self._settings.openai_model,
                system_prompt=_build_system_prompt_text(),
                user_prompt=_build_user_prompt_text(
                    contexto=contexto,
                    idioma=idioma,
                    texto_fonte=texto_fonte,
                ),
            )
        except (APIConnectionError, APIError) as exc:
            self._logger.exception("Falha ao normalizar texto OCR.")
            raise ServiceError("Falha ao normalizar texto OCR.", status_code=502) from exc
        except ValueError:
            # Fallback deterministico para texto OCR quando o modelo nao retorna JSON valido.
            secoes = _fallback_sections_from_raw_text(texto_fonte)
            texto_normalizado = _sections_to_text(secoes) if secoes else texto_fonte.strip()
            return {
                "titulo_documento": None,
                "secoes": [secao.model_dump(mode="json") for secao in secoes],
                "texto_normalizado": texto_normalizado,
                "observacoes": ["fallback_deterministico_texto_ocr"],
            }

    def _build_response_from_payloads(
        self,
        *,
        payloads: list[dict[str, Any]],
        contexto: str,
        idioma: str,
        tipo_fonte: str,
        total_fontes: int,
    ) -> PlanoTextoNormalizadoResponse:
        secoes: list[PlanoTextoNormalizadoSecao] = []
        observacoes: list[str] = []
        titulo_documento: str | None = None

        for index, payload in enumerate(payloads, start=1):
            raw_titulo = _as_clean_string(payload.get("titulo_documento"))
            if raw_titulo and not titulo_documento:
                titulo_documento = raw_titulo

            item_secoes = _extract_sections(payload)
            if total_fontes > 1:
                for secao in item_secoes:
                    secao.titulo = f"fonte_{index}::{secao.titulo}"
            secoes.extend(item_secoes)

            observacoes.extend(_extract_string_list(payload.get("observacoes")))

        if not secoes:
            raise ServiceError("Nao foi possivel normalizar o texto do documento.", status_code=502)

        secoes = _dedupe_sections(secoes)
        texto_normalizado = _sections_to_text(secoes)
        observacoes = _dedupe_text_list(observacoes)

        return PlanoTextoNormalizadoResponse(
            contexto=contexto,
            idioma=idioma,
            tipo_fonte=tipo_fonte,
            total_fontes=total_fontes,
            titulo_documento=titulo_documento,
            secoes=secoes,
            texto_normalizado=texto_normalizado,
            observacoes=observacoes,
            agente=AgenteNormalizacaoPlanoTexto(
                contexto="normalizar_texto_plano_alimentar",
                nome_agente="agente_normalizacao_plano_texto",
                status="sucesso",
                modelo=self._settings.openai_model,
                tipo_fonte=tipo_fonte,
                total_fontes=total_fontes,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _ensure_openai_api_key(self) -> None:
        if not self._settings.openai_api_key.strip():
            raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)

    def _resolve_imagem_url(self, imagem_url: str) -> str:
        return resolve_image_reference_to_public_url(
            imagem_url,
            supabase_url=self._settings.supabase_url,
            public_bucket=self._settings.supabase_storage_public_bucket,
        )


def _build_system_prompt() -> str:
    return (
        "Voce recebe uma imagem ou PDF de plano alimentar e deve normalizar o conteudo em texto estruturado. "
        "Mantenha relacoes entre medida e alimento/preparacao sem misturar colunas. "
        "Nao invente informacoes. Nao omita itens legiveis. "
        "Retorne APENAS JSON valido no formato: "
        '{"titulo_documento":"",'
        '"secoes":[{"titulo":"", "texto":""}],'
        '"texto_normalizado":"",'
        '"observacoes":[""]}.'
    )


def _build_system_prompt_text() -> str:
    return (
        "Voce recebe OCR literal de plano alimentar e deve reestruturar em secoes semanticas claras. "
        "Nao invente informacoes. Nao inclua markdown. "
        "Retorne APENAS JSON valido no formato: "
        '{"titulo_documento":"",'
        '"secoes":[{"titulo":"", "texto":""}],'
        '"texto_normalizado":"",'
        '"observacoes":[""]}.'
    )


def _build_user_prompt(*, contexto: str, idioma: str, tipo_fonte: str) -> str:
    return (
        f"Contexto: {contexto}. Idioma: {idioma}. Tipo_fonte: {tipo_fonte}. "
        "Extraia secoes textuais semanticas para alimentar um agente posterior de estruturacao. "
        "Sugestao de secoes: cabecalho, desjejum, colacao, almoco, jantar, ceia, orientacoes. "
        "Cada secao deve conter linhas no formato 'QTD: ... | ALIMENTO: ...' quando aplicavel."
    )


def _build_user_prompt_text(*, contexto: str, idioma: str, texto_fonte: str) -> str:
    return (
        f"Contexto: {contexto}. Idioma: {idioma}. Tipo_fonte: texto_ocr. "
        "Reestruture o OCR em secoes de refeicao (ex.: desjejum, colacao, almoco, jantar, ceia, orientacoes). "
        "Quando houver evidencia, normalize linhas no formato 'QTD: ... | ALIMENTO: ...'. "
        "Mantenha somente dados alimentares/publicos do plano, removendo assinatura e contato. "
        f"Texto OCR bruto: {texto_fonte}"
    )


def _extract_sections(payload: dict[str, Any]) -> list[PlanoTextoNormalizadoSecao]:
    sections: list[PlanoTextoNormalizadoSecao] = []
    raw_sections = payload.get("secoes")
    if isinstance(raw_sections, list):
        for item in raw_sections:
            if isinstance(item, dict):
                titulo = _as_clean_string(item.get("titulo")) or "secao"
                texto = _as_clean_string(item.get("texto"))
                if texto:
                    sections.append(PlanoTextoNormalizadoSecao(titulo=titulo, texto=texto))
            elif isinstance(item, str):
                texto = _as_clean_string(item)
                if texto:
                    sections.append(PlanoTextoNormalizadoSecao(titulo=f"secao_{len(sections) + 1}", texto=texto))

    if sections:
        return sections

    texto = _as_clean_string(payload.get("texto_normalizado"))
    if texto:
        return [PlanoTextoNormalizadoSecao(titulo="conteudo_principal", texto=texto)]

    return []


def _extract_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = _as_clean_string(item)
        if text:
            normalized.append(text)
    return normalized


def _sections_to_text(secoes: list[PlanoTextoNormalizadoSecao]) -> str:
    chunks: list[str] = []
    for secao in secoes:
        chunks.append(f"[{secao.titulo}]\n{secao.texto}")
    return "\n\n".join(chunks).strip()


def _as_clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dedupe_sections(secoes: list[PlanoTextoNormalizadoSecao]) -> list[PlanoTextoNormalizadoSecao]:
    grouped: dict[str, PlanoTextoNormalizadoSecao] = {}
    order: list[str] = []

    for secao in secoes:
        key = _normalize_for_match(secao.titulo)
        merged_text = _dedupe_text_lines(secao.texto)
        if not merged_text:
            continue
        if key not in grouped:
            grouped[key] = PlanoTextoNormalizadoSecao(titulo=secao.titulo.strip(), texto=merged_text)
            order.append(key)
            continue
        combined = "\n".join([grouped[key].texto, merged_text]).strip()
        grouped[key].texto = _dedupe_text_lines(combined)

    return [grouped[key] for key in order]


def _dedupe_text_lines(texto: str) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for raw_line in texto.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        line = _normalize_qtd_alimento_line(line)
        key = _normalize_for_match(line)
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return "\n".join(lines).strip()


def _normalize_qtd_alimento_line(line: str) -> str:
    match = re.match(r"(?is)^qtd:\s*(.+?)\s*\|\s*alimento:\s*(.+)$", line)
    if not match:
        return line
    qtd = re.sub(r"\s+", " ", match.group(1)).strip(" .;:")
    alimento = re.sub(r"\s+", " ", match.group(2)).strip(" .;:")
    if not qtd or not alimento:
        return line
    return f"QTD: {qtd} | ALIMENTO: {alimento}"


def _dedupe_text_list(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _as_clean_string(value)
        if not text:
            continue
        key = _normalize_for_match(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _fallback_sections_from_raw_text(texto: str) -> list[PlanoTextoNormalizadoSecao]:
    lines = _split_clean_lines(texto)
    if not lines:
        return []

    sections: dict[str, list[str]] = {}
    order: list[str] = []
    current = "conteudo_principal"
    sections[current] = []
    order.append(current)

    for line in lines:
        heading = _detect_meal_heading(line)
        if heading:
            current = heading
            if current not in sections:
                sections[current] = []
                order.append(current)
            continue
        sections[current].append(line)

    normalized_sections: list[PlanoTextoNormalizadoSecao] = []
    for title in order:
        normalized_text = _normalize_section_content(sections.get(title, []))
        if not normalized_text:
            continue
        normalized_sections.append(PlanoTextoNormalizadoSecao(titulo=title, texto=normalized_text))
    return normalized_sections


def _normalize_section_content(lines: list[str]) -> str:
    normalized_lines: list[str] = []
    for line in lines:
        parsed = _parse_qtd_alimento_line(line)
        if parsed:
            qtd, alimento = parsed
            normalized_lines.append(f"QTD: {qtd} | ALIMENTO: {alimento}")
            continue
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            normalized_lines.append(cleaned)
    return _dedupe_text_lines("\n".join(normalized_lines))


def _parse_qtd_alimento_line(line: str) -> tuple[str, str] | None:
    # Detecta linhas OCR no formato tabela: quantidade + alimento na mesma linha.
    if "|" in line:
        match = re.match(r"(?is)^qtd:\s*(.+?)\s*\|\s*alimento:\s*(.+)$", line.strip())
        if match:
            qtd = re.sub(r"\s+", " ", match.group(1)).strip(" .;:")
            alimento = re.sub(r"\s+", " ", match.group(2)).strip(" .;:")
            if qtd and alimento:
                return qtd, alimento

    compact = re.sub(r"\s+", " ", line).strip()
    pattern = re.match(
        r"(?is)^(?P<qtd>\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l|unidade|unid|und|col(?:her)?(?:es)?(?: de sopa| de cha| de sobremesa)?|fatia(?:s)?|porcao|prato|rod(?:ela)?s?|gotas?|copo(?:s)?)(?:[^a-z0-9]+.*)?)\s+(?P<alimento>[A-Za-zÃ€-Ã¿].+)$",
        compact,
    )
    if not pattern:
        return None
    qtd = pattern.group("qtd").strip(" .;:")
    alimento = pattern.group("alimento").strip(" .;:")
    if not qtd or not alimento:
        return None
    return qtd, alimento


def _split_clean_lines(texto: str) -> list[str]:
    content = texto.replace("```", "")
    lines: list[str] = []
    for raw_line in content.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if line:
            lines.append(line)
    return lines


def _detect_meal_heading(line: str) -> str | None:
    aliases = {
        "desjejum": "desjejum",
        "cafe da manha": "desjejum",
        "colacao": "colacao",
        "lanche da manha": "colacao",
        "almoco": "almoco",
        "lanche da tarde": "lanche_da_tarde",
        "jantar": "jantar",
        "ceia": "ceia",
        "orientacoes": "orientacoes",
    }
    normalized = _normalize_for_match(line)
    normalized = re.sub(r"\b([01]?\d|2[0-3]):[0-5]\d\b", "", normalized).strip(" :-[]")
    return aliases.get(normalized)


def _normalize_for_match(value: str) -> str:
    return normalize_pt_text(value)

