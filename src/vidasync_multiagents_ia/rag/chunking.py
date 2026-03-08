from dataclasses import dataclass

from vidasync_multiagents_ia.rag.models import RagChunk, RagSourceDocument


@dataclass(slots=True)
class SlidingWindowChunker:
    chunk_size: int
    chunk_overlap: int

    def chunk_sources(self, *, sources: list[RagSourceDocument]) -> list[RagChunk]:
        chunks: list[RagChunk] = []
        for source in sources:
            source_chunks = self._chunk_text(source=source)
            chunks.extend(source_chunks)
        return chunks

    def _chunk_text(self, *, source: RagSourceDocument) -> list[RagChunk]:
        text = source.content.strip()
        if not text:
            return []

        if len(text) <= self.chunk_size:
            return [
                RagChunk(
                    chunk_id=f"{source.source_id}:0",
                    source_id=source.source_id,
                    text=text,
                    metadata={
                        **source.metadata,
                        "source_id": source.source_id,
                        "title": source.title,
                    },
                )
            ]

        chunks: list[RagChunk] = []
        start = 0
        index = 0
        step = max(1, self.chunk_size - self.chunk_overlap)
        while start < len(text):
            end = min(len(text), start + self.chunk_size)
            window = text[start:end].strip()
            if window:
                chunks.append(
                    RagChunk(
                        chunk_id=f"{source.source_id}:{index}",
                        source_id=source.source_id,
                        text=window,
                        metadata={
                            **source.metadata,
                            "source_id": source.source_id,
                            "title": source.title,
                            "chunk_start": str(start),
                            "chunk_end": str(end),
                        },
                    )
                )
                index += 1
            if end >= len(text):
                break
            start += step
        return chunks
