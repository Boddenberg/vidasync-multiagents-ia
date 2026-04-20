import logging
from dataclasses import dataclass

from vidasync_multiagents_ia.core import normalize_pt_text
from vidasync_multiagents_ia.schemas import (
    IntencaoChatCandidata,
    IntencaoChatDetectada,
    IntencaoChatNome,
)


@dataclass(frozen=True, slots=True)
class _RegraIntencao:
    intencao: IntencaoChatNome
    contexto_roteamento: str
    termos: tuple[str, ...]
    requer_fluxo_estruturado: bool = True


class ChatIntencaoService:
    _FALLBACK_INTENCAO: IntencaoChatNome = "conversa_geral"
    _FALLBACK_CONTEXTO = "chat"
    _LIMIAR_CONFIANCA = 0.48

    _REGRAS: tuple[_RegraIntencao, ...] = (
        _RegraIntencao(
            intencao="enviar_plano_nutri",
            contexto_roteamento="normalizar_texto_plano_alimentar",
            termos=(
                "plano alimentar",
                "plano da nutri",
                "plano da nutricionista",
                "enviar plano",
                "nutricionista",
            ),
        ),
        _RegraIntencao(
            intencao="pedir_receitas",
            contexto_roteamento="chat_receitas",
            termos=("receita", "receitas", "prato para fazer", "como preparo", "modo de preparo"),
        ),
        _RegraIntencao(
            intencao="pedir_substituicoes",
            contexto_roteamento="chat_substituicoes",
            termos=("substituir", "substituicao", "trocar alimento", "alternativa", "equivalente"),
        ),
        _RegraIntencao(
            intencao="pedir_dicas",
            contexto_roteamento="chat_dicas",
            termos=(
                "dica",
                "dicas",
                "conselho",
                "orientacao",
                "sugestao",
                "fibra",
                "fibras",
                "fibra alimentar",
                "como aumentar fibra",
                "como melhorar a alimentacao",
                "o que comer",
                "como montar uma refeicao",
                "saciedade",
            ),
            requer_fluxo_estruturado=False,
        ),
        _RegraIntencao(
            intencao="perguntar_calorias",
            contexto_roteamento="calcular_calorias_texto",
            termos=("caloria", "calorias", "kcal", "quantas calorias", "macro", "macros"),
        ),
        _RegraIntencao(
            intencao="cadastrar_pratos",
            contexto_roteamento="cadastrar_pratos",
            termos=("cadastrar prato", "salvar prato", "adicionar prato", "favoritar prato"),
        ),
        _RegraIntencao(
            intencao="calcular_imc",
            contexto_roteamento="calcular_imc",
            termos=("imc", "indice de massa corporal", "calcular imc"),
        ),
        _RegraIntencao(
            intencao="registrar_refeicao_foto",
            contexto_roteamento="estimar_porcoes_do_prato",
            termos=(
                "foto do prato",
                "registrar por foto",
                "registrar refeicao por foto",
                "refeicao por foto",
                "analisar foto",
                "imagem do prato",
            ),
        ),
        _RegraIntencao(
            intencao="registrar_refeicao_audio",
            contexto_roteamento="transcrever_audio_usuario",
            termos=(
                "registrar por audio",
                "registrar refeicao por audio",
                "refeicao por audio",
                "mandar audio",
                "gravei um audio",
                "transcrever audio",
            ),
        ),
    )

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def detectar(self, prompt: str) -> IntencaoChatDetectada:
        # Etapa deterministica de intencao para orientar roteamento sem custo extra de LLM.
        texto = _normalizar_texto(prompt)
        candidatos: list[IntencaoChatCandidata] = []
        melhor: tuple[_RegraIntencao, float] | None = None

        for regra in self._REGRAS:
            score = _score_regra(regra, texto)
            if score <= 0:
                continue
            candidatos.append(IntencaoChatCandidata(intencao=regra.intencao, confianca=score))
            if melhor is None or score > melhor[1]:
                melhor = (regra, score)

        candidatos.sort(key=lambda item: item.confianca, reverse=True)
        top_candidatos = candidatos[:3]

        if melhor is None or melhor[1] < self._LIMIAR_CONFIANCA:
            result = IntencaoChatDetectada(
                intencao=self._FALLBACK_INTENCAO,
                confianca=0.55,
                contexto_roteamento=self._FALLBACK_CONTEXTO,
                requer_fluxo_estruturado=False,
                candidatos=top_candidatos,
            )
            self._logger.info(
                "chat_intencao.detected",
                extra={
                    "intencao": result.intencao,
                    "confianca": result.confianca,
                    "metodo": result.metodo,
                    "prompt_chars": len(prompt),
                    "candidatos": [
                        {"intencao": item.intencao, "confianca": item.confianca}
                        for item in top_candidatos
                    ],
                },
            )
            return result

        regra, score = melhor
        result = IntencaoChatDetectada(
            intencao=regra.intencao,
            confianca=round(score, 4),
            contexto_roteamento=regra.contexto_roteamento,
            requer_fluxo_estruturado=regra.requer_fluxo_estruturado,
            candidatos=top_candidatos,
        )
        self._logger.info(
            "chat_intencao.detected",
            extra={
                "intencao": result.intencao,
                "confianca": result.confianca,
                "metodo": result.metodo,
                "prompt_chars": len(prompt),
                "candidatos": [
                    {"intencao": item.intencao, "confianca": item.confianca}
                    for item in top_candidatos
                ],
            },
        )
        return result


def _normalizar_texto(value: str) -> str:
    return normalize_pt_text(value)


def _score_regra(regra: _RegraIntencao, texto: str) -> float:
    hits = [termo for termo in regra.termos if termo in texto]
    if not hits:
        return 0.0

    score = 0.42
    for termo in hits:
        comprimento_bonus = min(0.14, len(termo) / 120.0)
        score += 0.07 + comprimento_bonus

    cobertura = len(hits) / len(regra.termos)
    score += min(0.2, cobertura * 0.3)
    return min(0.99, round(score, 4))
