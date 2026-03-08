from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.services.plano_alimentar_service import PlanoAlimentarService


class _FakeOpenAIClient:
    def generate_json_from_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        assert model == "gpt-4o-mini"
        if "Secoes segmentadas" in user_prompt:
            return {"plano_refeicoes": []}

        assert "Texto consolidado" in user_prompt
        assert "fonte 1" in user_prompt
        assert "fonte 2" in user_prompt
        return {
            "plano_alimentar": {
                "tipo_plano": "reducao de gordura",
                "profissional": {
                    "nome": "Dra. Carolina",
                    "registro": "CRN3 56353",
                    "especialidades": "nutricao esportiva; emagrecimento",
                    "contato": {
                        "telefone": "(11) 99999-9999",
                        "email": "carol@example.com",
                    },
                },
                "objetivos": ["reduzir gordura", "melhorar disposicao"],
                "hidratacao": {"meta_ml_dia": "2500 ml"},
                "suplementos": [
                    {
                        "nome": "whey protein",
                        "dose": "45 g",
                        "frequencia": "dias de treino",
                    }
                ],
                "metas_nutricionais": {
                    "calorias_kcal": "1800",
                    "proteina_g": "140,5",
                    "carboidratos_g": "190",
                    "lipidios_g": "55",
                },
                "plano_refeicoes": [
                    {
                        "nome_refeicao": "cafe da manha",
                        "horario": "07:00",
                        "opcoes": [
                            {
                                "titulo": "opcao 1",
                                "itens": [
                                    {
                                        "alimento": "banana",
                                        "quantidade_texto": "1 unidade",
                                        "quantidade_valor": "1",
                                        "unidade": "unidade",
                                        "quantidade_gramas": "80 g",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "exames_solicitados": "hemograma\nultrassonografia de abdomen total",
                "observacoes_finais": "retorno em 30 dias",
            }
        }


class _FakeOpenAIClientPlanoVazio:
    def generate_json_from_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        assert model == "gpt-4o-mini"
        if "Secoes segmentadas" in user_prompt:
            return {"plano_refeicoes": []}
        return {
            "plano_alimentar": {
                "suplementos": [{"nome": "Whey protein", "dose": None}],
                "plano_refeicoes": [],
            }
        }


class _FakeOpenAIClientComItemSemQuantidade:
    def generate_json_from_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        assert model == "gpt-4o-mini"
        if "Secoes segmentadas" in user_prompt:
            return {
                "plano_refeicoes": [
                    {
                        "nome_refeicao": "lanche_da_tarde",
                        "opcoes": [
                            {
                                "titulo": "opcao 1",
                                "itens": [
                                    {"alimento": "banana"},
                                    {"alimento": "aveia", "quantidade_texto": "20 g", "quantidade_gramas": "20"},
                                ],
                            }
                        ],
                    }
                ]
            }
        return {"plano_alimentar": {"suplementos": [{"nome": "Creatina"}]}}


class _FakeOpenAIClientComDuplicacao:
    def generate_json_from_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        assert model == "gpt-4o-mini"
        if "Secoes segmentadas" in user_prompt:
            return {"plano_refeicoes": []}
        return {
            "plano_alimentar": {
                "plano_refeicoes": [
                    {
                        "nome_refeicao": "cafe_da_manha",
                        "opcoes": [
                            {
                                "titulo": "opcao 1",
                                "itens": [
                                    {"alimento": "Ovo", "quantidade_texto": "1 unidade"},
                                    {"alimento": "Ovo", "quantidade_texto": "1 unidade"},
                                ],
                            },
                            {
                                "titulo": "opcao 1",
                                "itens": [
                                    {"alimento": "Ovo", "quantidade_texto": "1 unidade"},
                                ],
                            },
                        ],
                    }
                ]
            }
        }


def test_plano_alimentar_service_estrutura_dados_do_texto() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PlanoAlimentarService(settings=settings, client=_FakeOpenAIClient())  # type: ignore[arg-type]

    result = service.estruturar_plano(
        textos_fonte=["fonte 1", "fonte 2"],
        contexto="estruturar_plano_alimentar",
        idioma="pt-BR",
    )

    assert result.contexto == "estruturar_plano_alimentar"
    assert result.fontes_processadas == 2
    assert result.plano_alimentar.tipo_plano == "reducao de gordura"
    assert result.plano_alimentar.profissional is not None
    assert result.plano_alimentar.profissional.registro_profissional == "CRN3 56353"
    assert result.plano_alimentar.hidratacao is not None
    assert result.plano_alimentar.hidratacao.meta_ml_dia == 2500.0
    assert result.plano_alimentar.metas_nutricionais is not None
    assert result.plano_alimentar.metas_nutricionais.proteina_g == 140.5
    assert len(result.plano_alimentar.plano_refeicoes) == 1
    assert result.plano_alimentar.plano_refeicoes[0].opcoes[0].itens[0].quantidade_gramas == 80.0
    assert result.plano_alimentar.exames_solicitados == [
        "hemograma",
        "ultrassonografia de abdomen total",
    ]


def test_plano_alimentar_service_enriquece_dose_e_refeicoes_por_regex() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PlanoAlimentarService(settings=settings, client=_FakeOpenAIClientPlanoVazio())  # type: ignore[arg-type]

    result = service.estruturar_plano(
        textos_fonte=[
            "Whey protein: 45 g, so nos dias de treino.",
            "1. Pao integral + creme de ricota + banana. 20g 40g 1 und.",
            "2. Tapioca integral + queijo mussarela + uva. 30g 15g 50g.",
        ],
    )

    assert result.plano_alimentar.suplementos[0].dose == "45 g"
    assert len(result.plano_alimentar.plano_refeicoes) == 1
    primeira_refeicao = result.plano_alimentar.plano_refeicoes[0]
    assert primeira_refeicao.nome_refeicao == "refeicoes_gerais"
    assert len(primeira_refeicao.opcoes) == 2
    assert len(primeira_refeicao.opcoes[0].itens) >= 3


def test_plano_alimentar_service_segmenta_lanche_por_titulo() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PlanoAlimentarService(settings=settings, client=_FakeOpenAIClientPlanoVazio())  # type: ignore[arg-type]

    result = service.estruturar_plano(
        textos_fonte=[
            "Lanche da tarde",
            "1. Pao integral + creme de ricota + banana",
            "20g 40g 1 und",
            "Endereco: Rua Exemplo, 10",
        ],
    )

    assert len(result.plano_alimentar.plano_refeicoes) == 1
    refeicao = result.plano_alimentar.plano_refeicoes[0]
    assert refeicao.nome_refeicao == "lanche_da_tarde"
    assert len(refeicao.opcoes) == 1
    assert all("Endereco" not in (item.alimento or "") for item in refeicao.opcoes[0].itens)


def test_plano_alimentar_service_retorna_diagnostico_e_flags_de_revisao() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PlanoAlimentarService(settings=settings, client=_FakeOpenAIClientComItemSemQuantidade())  # type: ignore[arg-type]

    result = service.estruturar_plano(
        textos_fonte=[
            "Lanche da tarde",
            "1. Banana + aveia",
        ]
    )

    assert result.diagnostico is not None
    assert result.diagnostico.pipeline == "hibrido_llm_regras"
    assert "lanche_da_tarde" in result.diagnostico.secoes_detectadas
    assert result.plano_alimentar.avisos_extracao

    refeicao = result.plano_alimentar.plano_refeicoes[0]
    assert refeicao.confianca is not None
    assert 0.0 <= refeicao.confianca <= 1.0

    primeiro_item = refeicao.opcoes[0].itens[0]
    assert primeiro_item.precisa_revisao is True
    assert primeiro_item.motivo_revisao is not None


def test_plano_alimentar_service_parseia_linhas_qtd_alimento_com_parser_deterministico() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PlanoAlimentarService(settings=settings, client=_FakeOpenAIClientPlanoVazio())  # type: ignore[arg-type]

    result = service.estruturar_plano(
        textos_fonte=[
            "[Desjejum]\nQTD: 1 unidade | ALIMENTO: Ovo\nQTD: 1 colher de sopa | ALIMENTO: Farinha de arroz",
            "[Almoço]\nQTD: 3 colheres de sopa | ALIMENTO: Arroz integral",
        ],
    )

    nomes = [ref.nome_refeicao for ref in result.plano_alimentar.plano_refeicoes]
    assert "cafe_da_manha" in nomes
    assert "almoco" in nomes
    assert "Nenhuma refeicao estruturada foi identificada." not in result.plano_alimentar.avisos_extracao

    cafe = next(ref for ref in result.plano_alimentar.plano_refeicoes if ref.nome_refeicao == "cafe_da_manha")
    assert len(cafe.opcoes) == 1
    assert cafe.opcoes[0].itens
    assert cafe.opcoes[0].itens[0].alimento == "Ovo"
    assert cafe.opcoes[0].itens[0].quantidade_texto == "1 unidade"
    assert cafe.opcoes[0].origem_dado == "deterministico_texto"
    assert all("QTD:" not in item.alimento for opcao in cafe.opcoes for item in opcao.itens)


def test_plano_alimentar_service_nao_inferir_hidratacao_apenas_por_medida_da_refeicao() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PlanoAlimentarService(settings=settings, client=_FakeOpenAIClientPlanoVazio())  # type: ignore[arg-type]

    result = service.estruturar_plano(
        textos_fonte=[
            "[Desjejum]\nQTD: 1 copo (250ml) | ALIMENTO: Suco Mix: Água de coco ou mineral",
        ],
    )

    assert result.plano_alimentar.hidratacao is not None
    assert result.plano_alimentar.hidratacao.meta_ml_dia is None


def test_plano_alimentar_service_nao_duplica_heuristica_quando_qtd_alimento_ja_estruturado() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PlanoAlimentarService(settings=settings, client=_FakeOpenAIClientPlanoVazio())  # type: ignore[arg-type]

    result = service.estruturar_plano(
        textos_fonte=[
            "[Desjejum]",
            "QTD: 4 unidades + 1 col. de sopa | ALIMENTO: Recheio: Morango + Pasta de amendoim",
            "QTD: 1 copo (250ml) | ALIMENTO: Suco Mix: Agua de coco ou mineral",
        ],
    )

    cafe = next(ref for ref in result.plano_alimentar.plano_refeicoes if ref.nome_refeicao == "cafe_da_manha")
    assert len(cafe.opcoes) == 1
    alimentos = [item.alimento for item in cafe.opcoes[0].itens]
    assert "QTD: 4 unidades" not in alimentos
    assert any("Recheio: Morango + Pasta de amendoim" in alimento for alimento in alimentos)


def test_plano_alimentar_service_deduplica_opcoes_e_itens_repetidos() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PlanoAlimentarService(settings=settings, client=_FakeOpenAIClientComDuplicacao())  # type: ignore[arg-type]

    result = service.estruturar_plano(
        textos_fonte=[
            "[Desjejum]\nQTD: 1 unidade | ALIMENTO: Ovo",
        ],
    )

    cafe = next(ref for ref in result.plano_alimentar.plano_refeicoes if ref.nome_refeicao == "cafe_da_manha")
    assert len(cafe.opcoes) == 1
    assert len(cafe.opcoes[0].itens) == 1
    assert cafe.opcoes[0].itens[0].alimento == "Ovo"
