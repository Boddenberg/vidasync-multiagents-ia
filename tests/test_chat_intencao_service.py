from vidasync_multiagents_ia.services.chat_intencao_service import ChatIntencaoService


def test_detecta_intencao_calorias_com_confianca() -> None:
    service = ChatIntencaoService()

    result = service.detectar("Quantas calorias tem 100g de arroz cozido?")

    assert result.intencao == "perguntar_calorias"
    assert result.contexto_roteamento == "calcular_calorias_texto"
    assert result.confianca >= 0.6
    assert result.requer_fluxo_estruturado is True


def test_detecta_intencao_imc() -> None:
    service = ChatIntencaoService()

    result = service.detectar("Pode calcular meu IMC com 72kg e 175cm?")

    assert result.intencao == "calcular_imc"
    assert result.contexto_roteamento == "calcular_imc"
    assert result.confianca >= 0.6


def test_fallback_para_conversa_geral_quando_sem_sinal_claro() -> None:
    service = ChatIntencaoService()

    result = service.detectar("Oi, tudo bem por ai?")

    assert result.intencao == "conversa_geral"
    assert result.contexto_roteamento == "chat"
    assert result.requer_fluxo_estruturado is False
    assert result.confianca >= 0.5


def test_detecta_dica_nutricional_para_pergunta_sobre_fibra() -> None:
    service = ChatIntencaoService()

    result = service.detectar("Como melhorar a ingestao de fibra alimentar?")

    assert result.intencao == "pedir_dicas"
    assert result.contexto_roteamento == "chat_dicas"
    assert result.requer_fluxo_estruturado is False
    assert result.confianca >= 0.48
