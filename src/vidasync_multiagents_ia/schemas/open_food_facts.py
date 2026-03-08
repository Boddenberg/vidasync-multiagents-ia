from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field


class OpenFoodFactsSearchRequest(BaseModel):
    consulta: str = Field(min_length=1, validation_alias=AliasChoices("consulta", "query", "search_terms"))
    gramas: float = Field(default=100.0, gt=0, validation_alias=AliasChoices("gramas", "grams"))
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)


class OpenFoodFactsNutrients(BaseModel):
    energia_kcal: float | None = None
    energia_kj: float | None = None
    proteina_g: float | None = None
    carboidratos_g: float | None = None
    lipidios_g: float | None = None
    gorduras_saturadas_g: float | None = None
    fibra_g: float | None = None
    acucares_g: float | None = None
    sodio_g: float | None = None
    sal_g: float | None = None


class OpenFoodFactsProduct(BaseModel):
    codigo_barras: str
    nome_produto: str | None = None
    marcas: str | None = None
    url_imagem: str | None = None
    por_100g: OpenFoodFactsNutrients
    ajustado: OpenFoodFactsNutrients


class OpenFoodFactsSearchResponse(BaseModel):
    contexto: str = "consultar_open_food_facts"
    fonte: str = "OPEN_FOOD_FACTS"
    consulta: str
    gramas: float
    page: int
    page_size: int
    total_produtos: int
    produtos: list[OpenFoodFactsProduct] = Field(default_factory=list)
    extraido_em: datetime
