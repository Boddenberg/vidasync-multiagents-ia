from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.services.foto_alimentos_service import FotoAlimentosService


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_json_from_image(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_url: str,
    ) -> dict:
        self.calls.append(system_prompt)
        if "triagem de imagens de refeicao" in system_prompt:
            return {
                "contexto": "identificar_fotos",
                "eh_comida": True,
                "qualidade_adequada": True,
                "confianca": 0.93,
                "motivo": "Prato visivel e iluminacao adequada.",
            }
        return {
            "contexto": "estimar_porcoes_do_prato",
            "itens": [
                {
                    "nome_alimento": "Arroz branco cozido",
                    "consulta_canonica": "arroz branco cozido",
                    "quantidade_estimada_gramas": 130,
                    "confianca": 0.88,
                },
                {
                    "nome_alimento": "Feijao carioca cozido",
                    "consulta_canonica": "feijao carioca cozido",
                    "quantidade_estimada_gramas": 90,
                    "confianca": 0.81,
                },
            ],
            "observacoes_gerais": "Estimativa visual aproximada.",
        }


def test_foto_alimentos_service_identificacao_por_agente() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    fake_client = _FakeOpenAIClient()
    service = FotoAlimentosService(settings=settings, client=fake_client)  # type: ignore[arg-type]

    result = service.identificar_se_e_foto_de_comida(
        imagem_url="https://example.com/prato.jpg",
        contexto="identificar_fotos",
        idioma="pt-BR",
    )

    assert result.contexto == "identificar_fotos"
    assert result.resultado_identificacao.eh_comida is True
    assert result.resultado_identificacao.qualidade_adequada is True
    assert result.agente.nome_agente == "agente_portaria_comida"


def test_foto_alimentos_service_estimativa_por_agente() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    fake_client = _FakeOpenAIClient()
    service = FotoAlimentosService(settings=settings, client=fake_client)  # type: ignore[arg-type]

    result = service.estimar_porcoes_do_prato(
        imagem_url="https://example.com/prato.jpg",
        contexto="estimar_porcoes_do_prato",
        idioma="pt-BR",
    )

    assert result.contexto == "estimar_porcoes_do_prato"
    assert len(result.resultado_porcoes.itens) == 2
    assert result.resultado_porcoes.itens[0].consulta_canonica == "arroz branco cozido"
    assert result.agente.nome_agente == "agente_estimativa_porcoes"
