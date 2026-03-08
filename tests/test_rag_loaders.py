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

