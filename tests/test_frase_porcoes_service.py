from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.services.frase_porcoes_service import FrasePorcoesService


class _FakeOpenAIClient:
    def generate_json_from_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        assert model == "gpt-4o-mini"
        assert "Texto:" in user_prompt
        return {
            "contexto": "interpretar_porcoes_texto",
            "itens": [
                {
                    "nome_alimento": "babaganuche",
                    "consulta_canonica": "babaganuche",
                    "quantidade_original": "cerca de 50 gramas",
                    "quantidade_gramas": 50,
                    "confianca": 0.92,
                },
                {
                    "nome_alimento": "kibe cru",
                    "consulta_canonica": "kibe cru",
                    "quantidade_original": "80 ou 100 gramas",
                    "quantidade_gramas_min": 80,
                    "quantidade_gramas_max": 100,
                    "confianca": 0.8,
                },
            ],
            "observacoes_gerais": "Estimativa com base em unidades narradas.",
        }


class _FakeOpenAIClientSemGramas:
    def generate_json_from_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        assert model == "gpt-4o-mini"
        return {
            "contexto": "interpretar_porcoes_texto",
            "itens": [
                {
                    "nome_alimento": "kafta",
                    "consulta_canonica": "kafta media",
                    "quantidade_original": "uma kafta inteira, media",
                    "quantidade_gramas": None,
                },
                {
                    "nome_alimento": "pao sirio",
                    "consulta_canonica": "pao sirio torrado",
                    "quantidade_original": "um pao sirio e meio",
                    "quantidade_gramas": None,
                },
            ],
        }


def test_frase_porcoes_service_estrutura_itens_em_gramas() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = FrasePorcoesService(settings=settings, client=_FakeOpenAIClient())  # type: ignore[arg-type]

    result = service.extrair_porcoes(
        texto_transcrito="Comi 50 gramas de babaganuche e 80 ou 100 gramas de kibe cru.",
        contexto="interpretar_porcoes_texto",
        idioma="pt-BR",
    )

    assert result.contexto == "interpretar_porcoes_texto"
    assert len(result.resultado_porcoes.itens) == 2
    assert result.resultado_porcoes.itens[0].quantidade_gramas == 50.0
    assert result.resultado_porcoes.itens[1].quantidade_gramas_min == 80.0
    assert result.resultado_porcoes.itens[1].quantidade_gramas_max == 100.0
    assert result.resultado_porcoes.itens[1].quantidade_gramas == 90.0
    assert result.agente.nome_agente == "agente_interpretacao_porcoes_texto"
    assert result.agente.confianca_media is not None


def test_frase_porcoes_service_infere_quando_ausente() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = FrasePorcoesService(settings=settings, client=_FakeOpenAIClientSemGramas())  # type: ignore[arg-type]

    result = service.extrair_porcoes(
        texto_transcrito="Comi uma kafta media e um pao sirio e meio.",
        contexto="interpretar_porcoes_texto",
        idioma="pt-BR",
        inferir_quando_ausente=True,
    )

    kafta = result.resultado_porcoes.itens[0]
    pao = result.resultado_porcoes.itens[1]

    assert kafta.quantidade_gramas == 90.0
    assert kafta.origem_quantidade == "inferida"
    assert kafta.metodo_inferencia == "unidade_media_por_alimento"
    assert kafta.precisa_revisao is True

    assert pao.quantidade_gramas == 90.0
    assert pao.quantidade_gramas_min is not None
    assert pao.quantidade_gramas_max is not None
    assert pao.origem_quantidade == "inferida"
    assert result.agente.confianca_media is not None
