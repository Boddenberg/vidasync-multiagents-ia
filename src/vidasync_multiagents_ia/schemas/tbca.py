from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class TBCASearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    consulta: str = Field(min_length=1, validation_alias=AliasChoices("consulta", "query"))
    gramas: float = Field(default=100.0, gt=0, validation_alias=AliasChoices("gramas", "grams"))


class TBCAFoodCandidate(BaseModel):
    code: str | None = None
    name: str = Field(min_length=1)
    detail_path: str = Field(min_length=1)


class TBCANutrientRow(BaseModel):
    component: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    value_per_100g: str = Field(min_length=1)


class TBCAFoodSelection(BaseModel):
    codigo: str | None = None
    nome: str
    url_detalhe: str


class TBCAMacros(BaseModel):
    energia_kcal: float | None = None
    proteina_g: float | None = None
    carboidratos_g: float | None = None
    lipidios_g: float | None = None


class TBCASearchResponse(BaseModel):
    contexto: str = "consultar_tbca"
    fonte: str = "TBCA"
    consulta: str
    gramas: float
    alimento_selecionado: TBCAFoodSelection
    por_100g: TBCAMacros
    ajustado: TBCAMacros
