from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class PlanoTextoNormalizadoSecao(BaseModel):
    titulo: str
    texto: str


class AgenteNormalizacaoPlanoTexto(BaseModel):
    contexto: str
    nome_agente: str
    status: str
    modelo: str
    tipo_fonte: str
    total_fontes: int


class PlanoTextoNormalizadoImagemRequest(BaseModel):
    contexto: str = "normalizar_texto_plano_alimentar"
    idioma: str = "pt-BR"
    imagem_url: str | None = Field(default=None, min_length=1)
    imagem_urls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_input(self) -> "PlanoTextoNormalizadoImagemRequest":
        # Aceita imagem unica ou lista e remove duplicadas/vazias.
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


class PlanoTextoNormalizadoResponse(BaseModel):
    contexto: str
    idioma: str
    tipo_fonte: str
    total_fontes: int
    titulo_documento: str | None = None
    secoes: list[PlanoTextoNormalizadoSecao]
    texto_normalizado: str
    observacoes: list[str] = Field(default_factory=list)
    agente: AgenteNormalizacaoPlanoTexto
    extraido_em: datetime
