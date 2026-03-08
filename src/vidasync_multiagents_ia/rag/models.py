from dataclasses import dataclass, field


@dataclass(slots=True)
class RagSourceDocument:
    source_id: str
    source_path: str
    title: str
    content: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RagChunk:
    chunk_id: str
    source_id: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RagSearchHit:
    chunk: RagChunk
    score: float


@dataclass(slots=True)
class RagIngestionSummary:
    total_sources: int
    total_chunks: int
    embedder_name: str
    vector_dimensions: int
