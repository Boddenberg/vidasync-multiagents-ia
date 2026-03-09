import logging
from datetime import datetime, timezone
from typing import Any

from openai import APIConnectionError, APIError

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    EstimativaPorcoesFotoResponse,
    ExecucaoAgenteFoto,
    IdentificacaoFotoResponse,
    ItemAlimentoEstimado,
    ResultadoIdentificacaoFoto,
    ResultadoPorcoesFoto,
)
from vidasync_multiagents_ia.services.image_reference_resolver import (
    resolve_image_reference_to_public_url,
)


class FotoAlimentosService:
    def __init__(self, settings: Settings, client: OpenAIClient | None = None) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
        )
        self._logger = logging.getLogger(__name__)

    def identificar_se_e_foto_de_comida(
        self,
        *,
        imagem_url: str,
        contexto: str = "identificar_fotos",
        idioma: str = "pt-BR",
    ) -> IdentificacaoFotoResponse:
        # /**** Agente 1: valida se a imagem e de refeicao e se possui qualidade minima. ****/
        self._ensure_openai_api_key()
        imagem_url_resolvida = self._resolve_imagem_url(imagem_url)
        self._logger.info(
            "foto_alimentos.identificacao.started",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "imagem_url": imagem_url_resolvida,
                "modelo": self._settings.openai_model,
            },
        )
        identificacao_raw = self._executar_agente_identificacao(
            imagem_url=imagem_url_resolvida,
            contexto=contexto,
            idioma=idioma,
        )
        identificacao = self._normalizar_identificacao(identificacao_raw)
        self._logger.info(
            "foto_alimentos.identificacao.completed",
            extra={
                "contexto": contexto,
                "imagem_url": imagem_url_resolvida,
                "eh_comida": identificacao.eh_comida,
                "qualidade_adequada": identificacao.qualidade_adequada,
                "confianca": identificacao.confianca,
            },
        )

        return IdentificacaoFotoResponse(
            contexto=contexto,
            imagem_url=imagem_url_resolvida,
            resultado_identificacao=identificacao,
            agente=ExecucaoAgenteFoto(
                contexto="identificar_se_e_foto_de_comida",
                nome_agente="agente_portaria_comida",
                status="sucesso",
                modelo=self._settings.openai_model,
                confianca=identificacao.confianca,
                saida=identificacao_raw,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def estimar_porcoes_do_prato(
        self,
        *,
        imagem_url: str,
        contexto: str = "estimar_porcoes_do_prato",
        idioma: str = "pt-BR",
    ) -> EstimativaPorcoesFotoResponse:
        # /**** Agente 2: estima porcoes e gramas por item visualizado na imagem. ****/
        self._ensure_openai_api_key()
        imagem_url_resolvida = self._resolve_imagem_url(imagem_url)
        self._logger.info(
            "foto_alimentos.porcoes.started",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "imagem_url": imagem_url_resolvida,
                "modelo": self._settings.openai_model,
            },
        )
        porcoes_raw = self._executar_agente_porcoes(
            imagem_url=imagem_url_resolvida,
            contexto=contexto,
            idioma=idioma,
        )
        porcoes = self._normalizar_porcoes(porcoes_raw)
        confianca_media = _confianca_media_itens(porcoes.itens)
        self._logger.info(
            "foto_alimentos.porcoes.completed",
            extra={
                "contexto": contexto,
                "imagem_url": imagem_url_resolvida,
                "itens": len(porcoes.itens),
                "confianca_media": confianca_media,
            },
        )

        return EstimativaPorcoesFotoResponse(
            contexto=contexto,
            imagem_url=imagem_url_resolvida,
            resultado_porcoes=porcoes,
            agente=ExecucaoAgenteFoto(
                contexto="estimar_porcoes_do_prato",
                nome_agente="agente_estimativa_porcoes",
                status="sucesso",
                modelo=self._settings.openai_model,
                confianca=confianca_media,
                saida=porcoes_raw,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _ensure_openai_api_key(self) -> None:
        api_key = self._settings.openai_api_key.strip()
        if not api_key:
            raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)

    def _resolve_imagem_url(self, imagem_url: str) -> str:
        return resolve_image_reference_to_public_url(
            imagem_url,
            supabase_url=self._settings.supabase_url,
            public_bucket=self._settings.supabase_storage_public_bucket,
        )

    def _executar_agente_identificacao(
        self,
        *,
        imagem_url: str,
        contexto: str,
        idioma: str,
    ) -> dict[str, Any]:
        system_prompt = (
            "Voce e um agente de triagem de imagens de refeicao. "
            "Responda somente em JSON valido, sem markdown. "
            "Contexto da tarefa: identificar_fotos."
        )
        user_prompt = (
            f"Idioma de resposta: {idioma}. "
            f"Contexto recebido: {contexto}. "
            "Analise a imagem e retorne o JSON com as chaves: "
            "contexto, eh_comida, qualidade_adequada, confianca, motivo. "
            "Use confianca de 0 a 1."
        )
        return self._executar_chamada_openai(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            imagem_url=imagem_url,
        )

    def _executar_agente_porcoes(
        self,
        *,
        imagem_url: str,
        contexto: str,
        idioma: str,
    ) -> dict[str, Any]:
        system_prompt = (
            "Voce e um agente de estimativa visual de porcoes de alimentos. "
            "Responda somente em JSON valido, sem markdown. "
            "Nao invente dados nao visiveis."
        )
        user_prompt = (
            f"Idioma de resposta: {idioma}. "
            f"Contexto recebido: {contexto}. "
            "Retorne JSON com as chaves: contexto, itens, observacoes_gerais. "
            "Cada item deve conter: nome_alimento, consulta_canonica, quantidade_estimada_gramas, confianca, observacoes. "
            "Use confianca de 0 a 1."
        )
        return self._executar_chamada_openai(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            imagem_url=imagem_url,
        )

    def _executar_chamada_openai(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        imagem_url: str,
    ) -> dict[str, Any]:
        try:
            return self._client.generate_json_from_image(
                model=self._settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_url=imagem_url,
            )
        except APIConnectionError as exc:
            self._logger.exception("Falha de conexao com a OpenAI em analise de foto")
            raise ServiceError("Falha de conexao com a OpenAI.", status_code=502) from exc
        except APIError as exc:
            self._logger.exception("Erro da OpenAI em analise de foto")
            raise ServiceError(f"Erro da OpenAI: {exc.__class__.__name__}", status_code=502) from exc
        except ValueError as exc:
            self._logger.exception("Resposta da OpenAI nao retornou JSON valido")
            raise ServiceError("Resposta da OpenAI em formato invalido para analise de foto.", status_code=502) from exc

    def _normalizar_identificacao(self, payload: dict[str, Any]) -> ResultadoIdentificacaoFoto:
        eh_comida = _to_bool(payload.get("eh_comida"), fallback=_to_bool(payload.get("is_food"), fallback=False))
        qualidade_adequada = _to_bool(
            payload.get("qualidade_adequada"),
            fallback=_to_bool(payload.get("quality_ok"), fallback=False),
        )
        motivo = _to_optional_str(payload.get("motivo") or payload.get("reason"))
        confianca = _to_optional_float(payload.get("confianca") or payload.get("confidence"))

        return ResultadoIdentificacaoFoto(
            eh_comida=eh_comida,
            qualidade_adequada=qualidade_adequada,
            motivo=motivo,
            confianca=confianca,
        )

    def _normalizar_porcoes(self, payload: dict[str, Any]) -> ResultadoPorcoesFoto:
        raw_items = payload.get("itens") or payload.get("items") or []
        itens: list[ItemAlimentoEstimado] = []
        if isinstance(raw_items, list):
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    continue
                nome = _to_optional_str(raw_item.get("nome_alimento") or raw_item.get("food_name"))
                consulta = _to_optional_str(raw_item.get("consulta_canonica") or raw_item.get("canonical_query"))
                if not nome and not consulta:
                    continue
                itens.append(
                    ItemAlimentoEstimado(
                        nome_alimento=nome or consulta or "alimento_nao_identificado",
                        consulta_canonica=consulta or nome or "alimento_nao_identificado",
                        quantidade_estimada_gramas=_to_optional_float(
                            raw_item.get("quantidade_estimada_gramas") or raw_item.get("estimated_grams")
                        ),
                        confianca=_to_optional_float(raw_item.get("confianca") or raw_item.get("confidence")),
                        observacoes=_to_optional_str(raw_item.get("observacoes") or raw_item.get("notes")),
                    )
                )

        observacoes_gerais = _to_optional_str(payload.get("observacoes_gerais") or payload.get("general_notes"))
        return ResultadoPorcoesFoto(itens=itens, observacoes_gerais=observacoes_gerais)


def _to_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "sim", "yes"}:
            return True
        if lowered in {"false", "0", "nao", "no"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return fallback


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _confianca_media_itens(itens: list[ItemAlimentoEstimado]) -> float | None:
    confiancas = [item.confianca for item in itens if item.confianca is not None]
    if not confiancas:
        return None
    return round(sum(confiancas) / len(confiancas), 4)

