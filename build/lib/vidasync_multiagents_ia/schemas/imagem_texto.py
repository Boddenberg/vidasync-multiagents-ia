from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ImagemTextoRequest(BaseModel):
    contexto: str = "transcrever_texto_imagem"
    idioma: str = "pt-BR"
    imagem_url: str | None = Field(default=None, min_length=1)
    imagem_urls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_input(self) -> "ImagemTextoRequest":
        # /**** Garante que pelo menos uma URL de imagem foi informada. ****/
        normalized_list = [url.strip() for url in self.imagem_urls if url and url.strip()]
        if self.imagem_url and self.imagem_url.strip():
            normalized_list.insert(0, self.imagem_url.strip())
        deduplicated: list[str] = []
        for url in normalized_list:
            if url not in deduplicated:
                deduplicated.append(url)
        if not deduplicated:
            raise ValueError("Informe 'imagem_url' ou 'imagem_urls'.")
        self.imagem_urls = deduplicated
        self.imagem_url = None
        return self


class AgenteTranscricaoImagemTexto(BaseModel):
    contexto: str
    nome_agente: str
    status: str
    modelo: str
    modo_execucao: str
    total_imagens: int


class ImagemTextoItemResponse(BaseModel):
    imagem_url: str
    status: str
    texto_transcrito: str
    erro: str | None = None


class ImagemTextoResponse(BaseModel):
    contexto: str
    idioma: str
    total_imagens: int
    resultados: list[ImagemTextoItemResponse]
    agente: AgenteTranscricaoImagemTexto
    extraido_em: datetime
