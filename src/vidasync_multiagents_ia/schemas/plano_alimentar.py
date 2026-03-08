from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class PlanoAlimentarRequest(BaseModel):
    contexto: str = "estruturar_plano_alimentar"
    idioma: str = "pt-BR"
    texto_transcrito: str | None = Field(default=None, min_length=1)
    textos_fonte: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_input(self) -> "PlanoAlimentarRequest":
        textos_normalizados = [texto.strip() for texto in self.textos_fonte if texto and texto.strip()]
        if self.texto_transcrito and self.texto_transcrito.strip():
            textos_normalizados.insert(0, self.texto_transcrito.strip())

        deduplicados: list[str] = []
        for texto in textos_normalizados:
            if texto not in deduplicados:
                deduplicados.append(texto)

        if not deduplicados:
            raise ValueError("Informe 'texto_transcrito' ou 'textos_fonte'.")

        self.textos_fonte = deduplicados
        self.texto_transcrito = None
        return self


class ContatoProfissionalPlano(BaseModel):
    telefone: str | None = None
    email: str | None = None
    instagram: str | None = None
    endereco: str | None = None


class ProfissionalPlano(BaseModel):
    nome: str | None = None
    registro_profissional: str | None = None
    especialidades: list[str] = Field(default_factory=list)
    contato: ContatoProfissionalPlano | None = None


class PacientePlano(BaseModel):
    nome: str | None = None
    sexo: str | None = None
    idade_anos: float | None = None
    peso_kg: float | None = None
    altura_cm: float | None = None
    imc: float | None = None
    condicoes_clinicas: list[str] = Field(default_factory=list)
    alergias_alimentares: list[str] = Field(default_factory=list)
    restricoes_alimentares: list[str] = Field(default_factory=list)
    sintomas_relatados: list[str] = Field(default_factory=list)


class HidratacaoPlano(BaseModel):
    meta_ml_dia: float | None = None
    orientacoes: list[str] = Field(default_factory=list)


class SuplementoPlano(BaseModel):
    nome: str
    dose: str | None = None
    frequencia: str | None = None
    horario: str | None = None
    observacoes: str | None = None
    origem_dado: str | None = None
    precisa_revisao: bool = False
    motivo_revisao: str | None = None


class ItemAlimentarPlano(BaseModel):
    alimento: str
    quantidade_texto: str | None = None
    quantidade_valor: float | None = None
    unidade: str | None = None
    quantidade_gramas: float | None = None
    observacoes: str | None = None
    origem_dado: str | None = None
    precisa_revisao: bool = False
    motivo_revisao: str | None = None


class OpcaoRefeicaoPlano(BaseModel):
    titulo: str | None = None
    itens: list[ItemAlimentarPlano] = Field(default_factory=list)
    observacoes: str | None = None
    origem_dado: str | None = None


class RefeicaoPlano(BaseModel):
    nome_refeicao: str
    horario: str | None = None
    opcoes: list[OpcaoRefeicaoPlano] = Field(default_factory=list)
    observacoes: str | None = None
    origem_dado: str | None = None
    confianca: float | None = None


class MetasNutricionaisPlano(BaseModel):
    calorias_kcal: float | None = None
    proteina_g: float | None = None
    carboidratos_g: float | None = None
    lipidios_g: float | None = None
    fibras_g: float | None = None


class SubstituicaoPlano(BaseModel):
    refeicao: str | None = None
    item_original: str | None = None
    item_substituto: str | None = None
    proporcao: str | None = None
    observacoes: str | None = None


class PlanoAlimentarEstruturado(BaseModel):
    tipo_plano: str | None = None
    data_plano: str | None = None
    validade_inicio: str | None = None
    validade_fim: str | None = None
    profissional: ProfissionalPlano | None = None
    paciente: PacientePlano | None = None
    objetivos: list[str] = Field(default_factory=list)
    orientacoes_gerais: list[str] = Field(default_factory=list)
    comportamento_alimentar: list[str] = Field(default_factory=list)
    hidratacao: HidratacaoPlano | None = None
    suplementos: list[SuplementoPlano] = Field(default_factory=list)
    metas_nutricionais: MetasNutricionaisPlano | None = None
    plano_refeicoes: list[RefeicaoPlano] = Field(default_factory=list)
    alimentos_priorizar: list[str] = Field(default_factory=list)
    alimentos_evitar: list[str] = Field(default_factory=list)
    substituicoes: list[SubstituicaoPlano] = Field(default_factory=list)
    exames_solicitados: list[str] = Field(default_factory=list)
    orientacoes_treino: list[str] = Field(default_factory=list)
    monitoramento: list[str] = Field(default_factory=list)
    observacoes_finais: list[str] = Field(default_factory=list)
    avisos_extracao: list[str] = Field(default_factory=list)


class AgenteEstruturacaoPlano(BaseModel):
    contexto: str
    nome_agente: str
    status: str
    modelo: str
    fontes_processadas: int


class DiagnosticoPlano(BaseModel):
    pipeline: str
    secoes_detectadas: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PlanoAlimentarResponse(BaseModel):
    contexto: str
    idioma: str
    fontes_processadas: int
    plano_alimentar: PlanoAlimentarEstruturado
    agente: AgenteEstruturacaoPlano
    diagnostico: DiagnosticoPlano | None = None
    extraido_em: datetime
