import base64
import logging
from dataclasses import dataclass, field
from typing import Any

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.services.audio_transcricao_service import AudioTranscricaoService
from vidasync_multiagents_ia.services.foto_alimentos_service import FotoAlimentosService
from vidasync_multiagents_ia.services.frase_porcoes_service import FrasePorcoesService


@dataclass(slots=True)
class ChatRefeicaoMultimodalFlowOutput:
    resposta: str
    warnings: list[str] = field(default_factory=list)
    precisa_revisao: bool = False
    metadados: dict[str, Any] = field(default_factory=dict)


class ChatRefeicaoMultimodalFlowService:
    """
    /****
     * Fluxo multimodal para registro de refeicoes no chat (foto e audio).
     *
     * Responsabilidades:
     * - validar anexo de entrada
     * - acionar servicos especializados existentes (foto/audio/porcoes)
     * - consolidar um retorno unico para o roteador de chat
     *
     * Nota de evolucao:
     * esta camada ainda nao persiste cadastro; ela prepara payload consistente
     * para confirmacao posterior no BFF/app.
     ****/
    """

    def __init__(
        self,
        *,
        settings: Settings,
        foto_alimentos_service: FotoAlimentosService | None = None,
        audio_transcricao_service: AudioTranscricaoService | None = None,
        frase_porcoes_service: FrasePorcoesService | None = None,
    ) -> None:
        self._settings = settings
        self._foto_alimentos_service = foto_alimentos_service or FotoAlimentosService(settings=settings)
        self._audio_transcricao_service = audio_transcricao_service or AudioTranscricaoService(settings=settings)
        self._frase_porcoes_service = frase_porcoes_service or FrasePorcoesService(settings=settings)
        self._logger = logging.getLogger(__name__)

    def executar_foto(
        self,
        *,
        prompt: str,
        idioma: str,
        refeicao_anexo: dict[str, Any] | None,
    ) -> ChatRefeicaoMultimodalFlowOutput:
        tipo_fonte = str((refeicao_anexo or {}).get("tipo_fonte") or "").strip().lower()
        if tipo_fonte != "imagem":
            raise ServiceError(
                "Campo 'refeicao_anexo.tipo_fonte' invalido para fluxo de foto. Use 'imagem'.",
                status_code=400,
            )
        imagem_url = str((refeicao_anexo or {}).get("imagem_url") or "").strip()
        if not imagem_url:
            raise ServiceError(
                "Campo 'refeicao_anexo.imagem_url' e obrigatorio para fluxo de foto.",
                status_code=400,
            )

        self._logger.info(
            "chat_refeicao_multimodal.foto.started",
            extra={
                "idioma": idioma,
                "prompt_chars": len(prompt),
                "imagem_url": imagem_url,
            },
        )
        identificacao = self._foto_alimentos_service.identificar_se_e_foto_de_comida(
            imagem_url=imagem_url,
            contexto="identificar_fotos",
            idioma=idioma,
        )
        resultado_identificacao = identificacao.resultado_identificacao
        warnings: list[str] = []
        if not resultado_identificacao.eh_comida:
            warnings.append("A imagem enviada nao parece ser uma refeicao.")
        if not resultado_identificacao.qualidade_adequada:
            warnings.append("Imagem com qualidade inadequada para estimar porcoes.")
        if (resultado_identificacao.confianca or 0.0) < 0.75:
            warnings.append("Confianca baixa na identificacao da imagem.")

        if warnings and not resultado_identificacao.eh_comida:
            return ChatRefeicaoMultimodalFlowOutput(
                resposta=(
                    "Nao consegui confirmar que a imagem e de refeicao. "
                    "Envie outra foto do prato com melhor enquadramento."
                ),
                warnings=warnings,
                precisa_revisao=True,
                metadados={
                    "flow": "registro_refeicao_foto_v1",
                    "origem_entrada": "foto",
                    "identificacao": identificacao.model_dump(exclude_none=True),
                },
            )

        porcoes = self._foto_alimentos_service.estimar_porcoes_do_prato(
            imagem_url=imagem_url,
            contexto="estimar_porcoes_do_prato",
            idioma=idioma,
        )
        itens = [
            {
                "nome_alimento": item.nome_alimento,
                "consulta_canonica": item.consulta_canonica,
                "quantidade_gramas": item.quantidade_estimada_gramas,
                "confianca": item.confianca,
                "origem": "foto",
            }
            for item in porcoes.resultado_porcoes.itens
        ]
        if not itens:
            warnings.append("Nenhum alimento foi identificado na foto.")
        itens_sem_gramas = sum(1 for item in itens if item["quantidade_gramas"] is None)
        itens_baixa_confianca = sum(1 for item in itens if (item["confianca"] or 0.0) < 0.7)
        if itens_sem_gramas > 0:
            warnings.append("Uma ou mais porcoes ficaram sem gramas estimadas.")
        if itens_baixa_confianca > 0:
            warnings.append("Uma ou mais porcoes ficaram com baixa confianca.")

        precisa_revisao = bool(warnings)
        return ChatRefeicaoMultimodalFlowOutput(
            resposta=_build_resposta_refeicao(
                origem="foto",
                total_itens=len(itens),
                precisa_revisao=precisa_revisao,
            ),
            warnings=warnings,
            precisa_revisao=precisa_revisao,
            metadados={
                "flow": "registro_refeicao_foto_v1",
                "origem_entrada": "foto",
                "identificacao": identificacao.model_dump(exclude_none=True),
                "porcoes": porcoes.model_dump(exclude_none=True),
                "cadastro_extraido": {
                    "origem_entrada": "foto",
                    "itens": itens,
                },
            },
        )

    def executar_audio(
        self,
        *,
        prompt: str,
        idioma: str,
        refeicao_anexo: dict[str, Any] | None,
    ) -> ChatRefeicaoMultimodalFlowOutput:
        tipo_fonte = str((refeicao_anexo or {}).get("tipo_fonte") or "").strip().lower()
        if tipo_fonte != "audio":
            raise ServiceError(
                "Campo 'refeicao_anexo.tipo_fonte' invalido para fluxo de audio. Use 'audio'.",
                status_code=400,
            )
        audio_base64 = str((refeicao_anexo or {}).get("audio_base64") or "").strip()
        if not audio_base64:
            raise ServiceError(
                "Campo 'refeicao_anexo.audio_base64' e obrigatorio para fluxo de audio.",
                status_code=400,
            )
        nome_arquivo = str((refeicao_anexo or {}).get("nome_arquivo") or "").strip() or "audio_refeicao.webm"
        inferir_quando_ausente = _to_bool(
            (refeicao_anexo or {}).get("inferir_quando_ausente"),
            default=True,
        )
        audio_bytes = _decode_base64_file(
            encoded=audio_base64,
            file_kind="audio",
            max_bytes=self._settings.audio_max_upload_bytes,
        )

        self._logger.info(
            "chat_refeicao_multimodal.audio.started",
            extra={
                "idioma": idioma,
                "prompt_chars": len(prompt),
                "nome_arquivo": nome_arquivo,
                "audio_bytes": len(audio_bytes),
                "inferir_quando_ausente": inferir_quando_ausente,
            },
        )
        transcricao = self._audio_transcricao_service.transcrever_audio(
            audio_bytes=audio_bytes,
            nome_arquivo=nome_arquivo,
            contexto="transcrever_audio_usuario",
            idioma=idioma,
        )
        porcoes = self._frase_porcoes_service.extrair_porcoes(
            texto_transcrito=transcricao.texto_transcrito,
            contexto="interpretar_porcoes_texto",
            idioma=idioma,
            inferir_quando_ausente=inferir_quando_ausente,
        )
        itens = [
            {
                "nome_alimento": item.nome_alimento,
                "consulta_canonica": item.consulta_canonica,
                "quantidade_gramas": item.quantidade_gramas,
                "quantidade_gramas_min": item.quantidade_gramas_min,
                "quantidade_gramas_max": item.quantidade_gramas_max,
                "confianca": item.confianca,
                "origem_quantidade": item.origem_quantidade,
                "precisa_revisao": item.precisa_revisao,
                "origem": "audio",
            }
            for item in porcoes.resultado_porcoes.itens
        ]
        warnings: list[str] = []
        if not transcricao.texto_transcrito.strip():
            warnings.append("Transcricao retornou texto vazio.")
        if not itens:
            warnings.append("Nenhum alimento foi identificado no audio.")
        itens_revisao = sum(1 for item in itens if item["precisa_revisao"])
        if itens_revisao > 0:
            warnings.append("Uma ou mais porcoes extraidas do audio precisam de revisao.")

        precisa_revisao = bool(warnings)
        return ChatRefeicaoMultimodalFlowOutput(
            resposta=_build_resposta_refeicao(
                origem="audio",
                total_itens=len(itens),
                precisa_revisao=precisa_revisao,
            ),
            warnings=warnings,
            precisa_revisao=precisa_revisao,
            metadados={
                "flow": "registro_refeicao_audio_v1",
                "origem_entrada": "audio",
                "transcricao": transcricao.model_dump(exclude_none=True),
                "porcoes": porcoes.model_dump(exclude_none=True),
                "cadastro_extraido": {
                    "origem_entrada": "audio",
                    "itens": itens,
                },
            },
        )


def _build_resposta_refeicao(*, origem: str, total_itens: int, precisa_revisao: bool) -> str:
    if total_itens <= 0:
        if origem == "foto":
            return "Nao consegui extrair itens da foto do prato. Tente outra imagem."
        return "Nao consegui extrair itens do audio. Tente gravar novamente com mais detalhes."
    if precisa_revisao:
        return (
            f"Registrei {total_itens} item(ns) da refeicao via {origem}, "
            "mas existem pontos para revisar antes de confirmar."
        )
    return f"Registrei {total_itens} item(ns) da refeicao via {origem} com sucesso."


def _to_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "sim", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "nao", "não", "no", "n", "off"}:
        return False
    return default


def _decode_base64_file(*, encoded: str, file_kind: str, max_bytes: int) -> bytes:
    raw = encoded.strip()
    if ";base64," in raw:
        raw = raw.split(",", 1)[1]
    raw = "".join(raw.split())
    if not raw:
        raise ServiceError(f"Arquivo {file_kind} em base64 esta vazio.", status_code=400)
    try:
        decoded = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ServiceError(f"Arquivo {file_kind} em base64 invalido.", status_code=400) from exc
    if len(decoded) > max_bytes:
        raise ServiceError(
            f"Arquivo {file_kind} acima do limite de {max_bytes} bytes.",
            status_code=413,
        )
    return decoded
