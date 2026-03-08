from langchain_core.documents import Document

from vidasync_multiagents_ia.rag.models import RagSearchHit


class RagContextBuilder:
    def __init__(self, *, max_chars: int = 4000) -> None:
        self._max_chars = max_chars

    def build(self, *, hits: list[RagSearchHit]) -> tuple[str, list[Document]]:
        docs: list[Document] = []
        chunks: list[str] = []
        consumed_chars = 0

        for index, hit in enumerate(hits, start=1):
            text = hit.chunk.text.strip()
            if not text:
                continue
            if consumed_chars + len(text) > self._max_chars:
                break
            consumed_chars += len(text)
            metadata = dict(hit.chunk.metadata)
            metadata["score"] = str(hit.score)
            metadata["chunk_id"] = hit.chunk.chunk_id
            docs.append(Document(page_content=text, metadata=metadata))
            chunks.append(
                f"[doc_{index} source={metadata.get('source_path', 'desconhecido')} score={hit.score}] {text}"
            )

        context = "\n".join(chunks).strip()
        return context, docs
