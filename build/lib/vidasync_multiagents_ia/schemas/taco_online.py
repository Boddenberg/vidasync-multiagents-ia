from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class TacoOnlineFoodRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slug: str | None = Field(default=None, min_length=1)
    url: str | None = Field(default=None, min_length=1)
    consulta: str | None = Field(default=None, min_length=1, validation_alias=AliasChoices("consulta", "query"))
    gramas: float = Field(default=100.0, gt=0, validation_alias=AliasChoices("gramas", "grams"))


class TacoOnlineNutrients(BaseModel):
    energia_kcal: float | None = None
    energia_kj: float | None = None
    carboidratos_g: float | None = None
    proteina_g: float | None = None
    lipidios_g: float | None = None
    fibra_g: float | None = None
    ferro_mg: float | None = None
    calcio_mg: float | None = None
    sodio_mg: float | None = None
    magnesio_mg: float | None = None
    potassio_mg: float | None = None
    manganes_mg: float | None = None
    fosforo_mg: float | None = None
    cobre_mg: float | None = None
    zinco_mg: float | None = None
    cinzas_g: float | None = None
    retinol_mcg: float | None = None
    tiamina_mg: float | None = None
    riboflavina_mg: float | None = None
    piridoxina_mg: float | None = None
    niacina_mg: float | None = None
    umidade_percentual: float | None = None


class TacoOnlineRawFoodData(BaseModel):
    slug: str | None = None
    nome_alimento: str | None = None
    grupo_alimentar: str | None = None
    base_calculo: str | None = None
    nutrientes: dict[str, str | None] = Field(default_factory=dict)


class TacoOnlineFoodIndexItem(BaseModel):
    slug: str
    nome_alimento: str
    grupo_alimentar: str | None = None
    tabela: str


class TacoOnlineFoodResponse(BaseModel):
    contexto: str = "consultar_taco_online"
    fonte: str = "TABELA_TACO_ONLINE"
    url_pagina: str
    slug: str | None = None
    gramas: float
    nome_alimento: str | None = None
    grupo_alimentar: str | None = None
    base_calculo: str | None = None
    por_100g: TacoOnlineNutrients
    ajustado: TacoOnlineNutrients
    extraido_em: datetime
