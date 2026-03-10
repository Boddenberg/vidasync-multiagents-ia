import httpx
from openai import BadRequestError

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.services.foto_alimentos_service import FotoAlimentosService


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.image_urls: list[str] = []

    def generate_json_from_image(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_url: str,
    ) -> dict:
        self.calls.append(system_prompt)
        self.image_urls.append(image_url)
        if "triagem de imagens de refeicao" in system_prompt:
            return {
                "contexto": "identificar_fotos",
                "eh_comida": True,
                "qualidade_adequada": True,
                "confianca": 0.93,
                "motivo": "Prato visivel e iluminacao adequada.",
            }
        if "nome principal de pratos em fotos" in system_prompt:
            return {
                "contexto": "identificar_nome_prato_foto",
                "nome_prato": "Poke de salmao",
                "confianca": 0.89,
                "observacoes": "Prato montado em bowl com peixe cru, arroz e vegetais.",
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


class _FakeOpenAIClientInvalidImage:
    def generate_json_from_image(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_url: str,
    ) -> dict:
        request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        response = httpx.Response(status_code=400, request=request)
        raise BadRequestError(
            "The image data you provided does not represent a valid image. "
            "Please check your input and try again with one of the supported image formats: "
            "['image/jpeg', 'image/png', 'image/gif', 'image/webp'].",
            response=response,
            body={"error": {"code": "invalid_value", "param": "input"}},
        )


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


def test_foto_alimentos_service_identifica_nome_prato_da_foto() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    fake_client = _FakeOpenAIClient()
    service = FotoAlimentosService(settings=settings, client=fake_client)  # type: ignore[arg-type]

    result = service.identificar_nome_prato_da_foto(
        imagem_url="https://example.com/prato.jpg",
        contexto="identificar_nome_prato_foto",
        idioma="pt-BR",
    )

    assert result.contexto == "identificar_nome_prato_foto"
    assert result.resultado_nome_prato.nome_prato == "Poke de salmao"
    assert result.resultado_nome_prato.confianca == 0.89
    assert result.agente.nome_agente == "agente_nome_prato_foto"


def test_foto_alimentos_service_resolve_storage_key_sem_token() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        supabase_url="https://project.supabase.co",
        supabase_storage_public_bucket="pipeline-inputs",
    )
    fake_client = _FakeOpenAIClient()
    service = FotoAlimentosService(settings=settings, client=fake_client)  # type: ignore[arg-type]

    result = service.identificar_se_e_foto_de_comida(
        imagem_url="file/abc/2026-03-08/imagem.jpg",
        contexto="identificar_fotos",
        idioma="pt-BR",
    )

    expected_url = (
        "https://project.supabase.co/storage/v1/object/public/"
        "pipeline-inputs/file/abc/2026-03-08/imagem.jpg"
    )
    assert fake_client.image_urls[-1] == expected_url
    assert result.imagem_url == expected_url


def test_foto_alimentos_service_preserva_url_assinada() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        supabase_url="https://project.supabase.co",
        supabase_storage_public_bucket="pipeline-inputs",
    )
    fake_client = _FakeOpenAIClient()
    service = FotoAlimentosService(settings=settings, client=fake_client)  # type: ignore[arg-type]
    signed_url = (
        "https://project.supabase.co/storage/v1/object/sign/"
        "pipeline-inputs/file/abc/2026-03-08/imagem.jpg?token=abc123"
    )

    result = service.identificar_se_e_foto_de_comida(
        imagem_url=signed_url,
        contexto="identificar_fotos",
        idioma="pt-BR",
    )

    assert fake_client.image_urls[-1] == signed_url
    assert result.imagem_url == signed_url


def test_foto_alimentos_service_retorna_422_para_imagem_invalida_da_openai() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = FotoAlimentosService(settings=settings, client=_FakeOpenAIClientInvalidImage())  # type: ignore[arg-type]

    try:
        service.identificar_se_e_foto_de_comida(
            imagem_url="https://example.com/arquivo-invalido.png",
            contexto="identificar_fotos",
            idioma="pt-BR",
        )
        assert False, "Esperava ServiceError com 422 para imagem invalida."
    except ServiceError as exc:
        assert exc.status_code == 422
        assert "Converta para JPEG, PNG, GIF ou WEBP." in exc.message
