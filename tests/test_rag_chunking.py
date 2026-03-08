from vidasync_multiagents_ia.rag.chunking import SlidingWindowChunker
from vidasync_multiagents_ia.rag.models import RagSourceDocument


def test_chunker_aplica_janela_deslizante_com_overlap() -> None:
    source = RagSourceDocument(
        source_id="doc1",
        source_path="knowledge/doc1.md",
        title="Doc 1",
        content="A" * 260,
        metadata={"source_path": "knowledge/doc1.md"},
    )
    chunker = SlidingWindowChunker(chunk_size=100, chunk_overlap=20)

    chunks = chunker.chunk_sources(sources=[source])

    assert len(chunks) == 3
    assert chunks[0].chunk_id == "doc1:0"
    assert chunks[1].chunk_id == "doc1:1"
    assert chunks[1].metadata["chunk_start"] == "80"
    assert chunks[1].metadata["chunk_end"] == "180"


def test_chunker_retorna_chunk_unico_para_texto_curto() -> None:
    source = RagSourceDocument(
        source_id="doc2",
        source_path="knowledge/doc2.md",
        title="Doc 2",
        content="texto curto",
        metadata={"source_path": "knowledge/doc2.md"},
    )
    chunker = SlidingWindowChunker(chunk_size=100, chunk_overlap=20)

    chunks = chunker.chunk_sources(sources=[source])

    assert len(chunks) == 1
    assert chunks[0].text == "texto curto"

