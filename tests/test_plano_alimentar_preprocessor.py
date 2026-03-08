from vidasync_multiagents_ia.services.plano_alimentar_pipeline import PlanoAlimentarPreprocessor


def test_preprocessor_segmenta_refeicoes_e_filtra_ruido_de_contato() -> None:
    preprocessor = PlanoAlimentarPreprocessor()

    context = preprocessor.preparar_contexto(
        [
            "Nutricionista - USP",
            "Lanche da tarde",
            "1. Pao integral + creme de ricota + banana",
            "20g 40g 1 und",
            "Instagram: @nutri",
            "Endereco: Rua Exemplo, 10",
        ]
    )

    assert "instagram" not in context.texto_sem_ruido.lower()
    assert "endereco" not in context.texto_sem_ruido.lower()
    assert len(context.secoes_refeicao) == 1
    assert context.secoes_refeicao[0].nome_refeicao == "lanche_da_tarde"
    assert len(context.secoes_refeicao[0].opcoes_heuristicas) == 1
    assert len(context.secoes_refeicao[0].opcoes_heuristicas[0].itens) >= 3


def test_preprocessor_distribui_opcoes_para_titulos_consecutivos() -> None:
    preprocessor = PlanoAlimentarPreprocessor()

    context = preprocessor.preparar_contexto(
        [
            "- Cafe da manha",
            "- Lanche da tarde",
            "- Ceia",
            "1. Pao integral + banana + aveia",
            "20g 1 und 15g",
        ]
    )

    nomes = [secao.nome_refeicao for secao in context.secoes_refeicao]
    assert "cafe_da_manha" in nomes
    assert "lanche_da_tarde" in nomes
    assert "ceia" in nomes
    assert all(secao.opcoes_heuristicas for secao in context.secoes_refeicao)


def test_preprocessor_detecta_titulos_com_colchetes() -> None:
    preprocessor = PlanoAlimentarPreprocessor()

    context = preprocessor.preparar_contexto(
        [
            "[Desjejum]",
            "QTD: 1 unidade | ALIMENTO: Ovo",
            "[Almoço]",
            "QTD: 3 colheres de sopa | ALIMENTO: Arroz integral",
        ]
    )

    nomes = [secao.nome_refeicao for secao in context.secoes_refeicao]
    assert "cafe_da_manha" in nomes
    assert "almoco" in nomes
