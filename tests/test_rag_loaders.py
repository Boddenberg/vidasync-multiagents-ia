import json

from vidasync_multiagents_ia.rag.loaders import NutritionKnowledgeLoader


def test_loader_carrega_fontes_md_txt_json(tmp_path) -> None:
    (tmp_path / "faq.md").write_text(
        "Pergunta: fibra\n\n\nResposta: ajuda no intestino.   ",
        encoding="utf-8",
    )
    (tmp_path / "notas.txt").write_text("Dica 1: hidratacao diaria.", encoding="utf-8")
    (tmp_path / "estruturado.json").write_text(
        json.dumps(
            [
                {"title": "Guia porcao", "content": "Arroz: 3 colheres de sopa."},
                {"titulo": "Proteina", "conteudo": "Frango: palma da mao."},
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "ignorar.csv").write_text("nao deve carregar", encoding="utf-8")

    loader = NutritionKnowledgeLoader()
    sources = loader.load_sources(docs_dir=str(tmp_path))

    assert len(sources) == 4
    assert all(source.content for source in sources)
    assert all("source_path" in source.metadata for source in sources)
    assert any("faq" in source.source_id for source in sources)


def test_loader_ignora_json_invalido(tmp_path) -> None:
    (tmp_path / "quebrado.json").write_text("{invalido", encoding="utf-8")

    loader = NutritionKnowledgeLoader()
    sources = loader.load_sources(docs_dir=str(tmp_path))

    assert sources == []


def test_loader_carrega_serverdata_em_lotes_para_catalogos_grandes(tmp_path) -> None:
    payload = {
        "serverData": {
            "taco": [
                {
                    "id": index,
                    "slug": f"item-{index}",
                    "descricao": f"Alimento {index}",
                    "grupo": "Cereais",
                    "table": "TACO",
                }
                for index in range(30)
            ]
        }
    }
    (tmp_path / "banco.json").write_text(json.dumps(payload), encoding="utf-8")

    loader = NutritionKnowledgeLoader()
    sources = loader.load_sources(docs_dir=str(tmp_path))

    assert len(sources) == 1
    assert sources[0].metadata["source_type"] == "json_batch"
    assert "Collection: taco." in sources[0].content
    assert "Item: Alimento 0." in sources[0].content
    assert "Item: Alimento 29." in sources[0].content


def test_loader_carrega_items_estruturados_com_resposta_nutricional(tmp_path) -> None:
    payload = {
        "items": [
            {
                "source_item": {
                    "descricao": "Arroz integral cozido",
                    "grupo": "Cereais",
                    "table": "TACO",
                    "slug": "arroz-integral-cozido",
                },
                "response": {
                    "fonte": "TABELA_TACO_ONLINE",
                    "nome_alimento": "Arroz integral cozido",
                    "grupo_alimentar": "Cereais",
                    "slug": "arroz-integral-cozido",
                    "gramas": 100.0,
                    "base_calculo": "100 gramas",
                    "por_100g": {
                        "energia_kcal": 124.0,
                        "proteina_g": 2.6,
                        "carboidratos_g": 25.8,
                        "lipidios_g": 1.0,
                    },
                    "ajustado": {
                        "energia_kcal": 124.0,
                        "proteina_g": 2.6,
                        "carboidratos_g": 25.8,
                        "lipidios_g": 1.0,
                    },
                },
            }
        ]
    }
    (tmp_path / "taco_catalog_full.json").write_text(json.dumps(payload), encoding="utf-8")

    loader = NutritionKnowledgeLoader()
    sources = loader.load_sources(docs_dir=str(tmp_path))

    assert len(sources) == 1
    assert sources[0].title == "Arroz integral cozido"
    assert "Table: TACO." in sources[0].content
    assert "Per 100g: energia_kcal=124.0" in sources[0].content
    assert "Adjusted for 100.0 g" in sources[0].content
