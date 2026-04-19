import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from openai import APIConnectionError, APIError

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    AgenteEstruturacaoPlano,
    ContatoProfissionalPlano,
    DiagnosticoPlano,
    HidratacaoPlano,
    ItemAlimentarPlano,
    MetasNutricionaisPlano,
    OpcaoRefeicaoPlano,
    PacientePlano,
    PlanoAlimentarEstruturado,
    PlanoAlimentarResponse,
    ProfissionalPlano,
    RefeicaoPlano,
    SubstituicaoPlano,
    SuplementoPlano,
)
from vidasync_multiagents_ia.services.plano_alimentar_pipeline import (
    PlanoAlimentarPipelineContext,
    PlanoAlimentarPreprocessor,
    extract_deterministic_meal_sections,
    is_noise_food_text,
)


class PlanoAlimentarService:
    def __init__(
        self,
        settings: Settings,
        client: OpenAIClient | None = None,
        preprocessor: PlanoAlimentarPreprocessor | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
        )
        self._preprocessor = preprocessor or PlanoAlimentarPreprocessor()
        self._logger = logging.getLogger(__name__)

    def estruturar_plano(
        self,
        *,
        textos_fonte: list[str],
        contexto: str = "estruturar_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoAlimentarResponse:
        # Pipeline principal: preprocessa, extrai geral, extrai refeicoes e valida.
        self._ensure_openai_api_key()
        if not textos_fonte:
            raise ServiceError("Campo 'textos_fonte' e obrigatorio.", status_code=400)

        self._logger.info(
            "plano_alimentar.started",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "fontes_processadas": len(textos_fonte),
                "modelo": self._settings.openai_model,
            },
        )
        pipeline_context = self._preprocessor.preparar_contexto(textos_fonte)

        payload_geral = self._executar_agente_estruturacao(
            contexto=contexto,
            idioma=idioma,
            texto_consolidado=pipeline_context.texto_limpo,
        )
        plano = self._normalizar_plano(payload_geral)

        # Etapa intermediaria deterministica: texto normalizado -> refeicoes estruturadas.
        refeicoes_deterministicas = extract_deterministic_meal_sections(pipeline_context.texto_sem_ruido)
        if refeicoes_deterministicas:
            plano.plano_refeicoes = _merge_refeicoes(refeicoes_deterministicas, plano.plano_refeicoes)
            self._logger.info(
                "plano_alimentar.intermediate_parser.applied",
                extra={
                    "refeicoes_extraidas": len(refeicoes_deterministicas),
                    "refeicoes_totais_apos_merge": len(plano.plano_refeicoes),
                },
            )

        usar_segundo_agente_refeicoes = (
            self._settings.plano_alimentar_refeicoes_second_pass_enabled
            and self._precisa_reforcar_refeicoes(plano)
            and bool(pipeline_context.secoes_refeicao)
        )
        payload_refeicoes: dict[str, Any] = {}
        if usar_segundo_agente_refeicoes:
            self._logger.info(
                "plano_alimentar.second_pass_refeicoes.enabled",
                extra={"motivo": "refeicoes_insuficientes", "secoes_detectadas": len(pipeline_context.secoes_refeicao)},
            )
            payload_refeicoes = self._executar_agente_refeicoes(
                contexto=contexto,
                idioma=idioma,
                pipeline_context=pipeline_context,
            )
        else:
            self._logger.info(
                "plano_alimentar.second_pass_refeicoes.skipped",
                extra={
                    "setting_enabled": self._settings.plano_alimentar_refeicoes_second_pass_enabled,
                    "secoes_detectadas": len(pipeline_context.secoes_refeicao),
                    "refeicoes_iniciais": len(plano.plano_refeicoes),
                },
            )

        self._mesclar_refeicoes(
            plano=plano,
            payload_refeicoes=payload_refeicoes,
            pipeline_context=pipeline_context,
        )
        self._aplicar_enriquecimento_por_texto(
            plano=plano,
            pipeline_context=pipeline_context,
            idioma=idioma,
        )
        self._avaliar_qualidade_plano(
            plano=plano,
            pipeline_context=pipeline_context,
        )
        self._logger.info(
            "plano_alimentar.completed",
            extra={
                "contexto": contexto,
                "fontes_processadas": len(textos_fonte),
                "secoes_detectadas": len(pipeline_context.secoes_refeicao),
                "refeicoes": len(plano.plano_refeicoes),
                "suplementos": len(plano.suplementos),
                "avisos_extracao": len(plano.avisos_extracao),
            },
        )

        return PlanoAlimentarResponse(
            contexto=contexto,
            idioma=idioma,
            fontes_processadas=len(textos_fonte),
            plano_alimentar=plano,
            agente=AgenteEstruturacaoPlano(
                contexto="estruturar_plano_alimentar",
                nome_agente="agente_estrutura_plano_alimentar",
                status="sucesso",
                modelo=self._settings.openai_model,
                fontes_processadas=len(textos_fonte),
            ),
            diagnostico=DiagnosticoPlano(
                pipeline="hibrido_llm_regras",
                secoes_detectadas=[secao.nome_refeicao for secao in pipeline_context.secoes_refeicao],
                warnings=plano.avisos_extracao,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _aplicar_enriquecimento_por_texto(
        self,
        *,
        plano: PlanoAlimentarEstruturado,
        pipeline_context: PlanoAlimentarPipelineContext,
        idioma: str,
    ) -> None:
        # Regras deterministicas para preencher campos criticos e limpar ruido.
        texto = pipeline_context.texto_limpo
        self._enriquecer_profissional(plano=plano, texto=texto)
        self._enriquecer_hidratacao(plano=plano, texto=texto)
        self._enriquecer_suplementos_com_dose(plano=plano, texto=texto)
        self._sanitizar_plano_refeicoes(plano=plano)
        self._deduplicar_plano_refeicoes(plano=plano)

        if plano.orientacoes_gerais:
            plano.orientacoes_gerais = _sanitizar_orientacoes(plano.orientacoes_gerais)
        else:
            plano.orientacoes_gerais = _extrair_bullets(texto=pipeline_context.texto_sem_ruido, max_items=20)

        if not plano.objetivos:
            plano.objetivos = _inferir_objetivos_basicos(texto=texto, idioma=idioma)

    def _avaliar_qualidade_plano(
        self,
        *,
        plano: PlanoAlimentarEstruturado,
        pipeline_context: PlanoAlimentarPipelineContext,
    ) -> None:
        # Marca revisoes e calcula confianca para facilitar etapa de judge.
        warnings: list[str] = []

        if not plano.plano_refeicoes:
            warnings.append("Nenhuma refeicao estruturada foi identificada.")

        for refeicao in plano.plano_refeicoes:
            total_itens = 0
            itens_com_medida = 0
            itens_revisao = 0

            for opcao in refeicao.opcoes:
                for item in opcao.itens:
                    total_itens += 1
                    if item.quantidade_gramas is not None or item.quantidade_texto:
                        itens_com_medida += 1

                    if item.quantidade_gramas is None and item.quantidade_texto is None:
                        item.precisa_revisao = True
                        if not item.motivo_revisao:
                            item.motivo_revisao = "Quantidade ausente para o alimento."
                    elif item.quantidade_gramas is None and item.unidade in {None, "und", "unid", "unidade", "ml", "l"}:
                        item.precisa_revisao = True
                        if not item.motivo_revisao:
                            item.motivo_revisao = "Quantidade em gramas nao definida."

                    if item.precisa_revisao:
                        itens_revisao += 1

            base_confianca = 0.58 if refeicao.origem_dado == "heuristica" else 0.72
            ratio = (itens_com_medida / total_itens) if total_itens else 0.0
            refeicao.confianca = round(min(0.98, base_confianca + (ratio * 0.26)), 4)

            if total_itens == 0:
                warnings.append(f"Refeicao '{refeicao.nome_refeicao}' sem itens validos.")
            elif ratio < 0.4:
                warnings.append(f"Refeicao '{refeicao.nome_refeicao}' com baixa cobertura de medidas.")
            if itens_revisao > 0:
                warnings.append(f"Refeicao '{refeicao.nome_refeicao}' com {itens_revisao} item(ns) para revisao.")
            if refeicao.origem_dado == "heuristica":
                warnings.append(f"Refeicao '{refeicao.nome_refeicao}' extraida por heuristica (recomendado revisar).")

        for suplemento in plano.suplementos:
            if not suplemento.origem_dado:
                suplemento.origem_dado = "llm"
            if not _to_optional_str(suplemento.dose):
                suplemento.precisa_revisao = True
                if not suplemento.motivo_revisao:
                    suplemento.motivo_revisao = "Dose nao identificada no texto."

        if not plano.objetivos:
            warnings.append("Objetivos do plano nao identificados com clareza.")
        if not pipeline_context.secoes_refeicao and not plano.plano_refeicoes:
            warnings.append("Nao foram detectados titulos de refeicao no texto.")

        plano.avisos_extracao = _dedupe_strings(warnings)

    def _precisa_reforcar_refeicoes(self, plano: PlanoAlimentarEstruturado) -> bool:
        if not plano.plano_refeicoes:
            return True

        total_opcoes = sum(len(refeicao.opcoes) for refeicao in plano.plano_refeicoes)
        if total_opcoes == 0:
            return True

        total_itens = 0
        itens_com_medida = 0
        for refeicao in plano.plano_refeicoes:
            for opcao in refeicao.opcoes:
                for item in opcao.itens:
                    total_itens += 1
                    if item.quantidade_gramas is not None or item.quantidade_texto:
                        itens_com_medida += 1

        if total_itens == 0:
            return True

        cobertura = itens_com_medida / total_itens
        return cobertura < 0.45

    def _ensure_openai_api_key(self) -> None:
        if not self._settings.openai_api_key.strip():
            raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)

    def _executar_agente_estruturacao(
        self,
        *,
        contexto: str,
        idioma: str,
        texto_consolidado: str,
    ) -> dict[str, Any]:
        # Agente geral: metadados, objetivos, suplementos, orientacoes e campos globais.
        system_prompt = (
            "Voce e um agente de extracao de dados de planos alimentares. "
            "Responda apenas JSON valido, sem markdown. "
            "Preencha o maximo de campos possiveis e use null/lista vazia quando nao houver dado."
        )
        user_prompt = (
            f"Idioma de resposta: {idioma}. "
            f"Contexto recebido: {contexto}. "
            "Retorne JSON com chave raiz 'plano_alimentar'. "
            "Estruture campos de profissional, paciente, objetivos, hidratacao, suplementos, "
            "metas_nutricionais, plano_refeicoes, substituicoes, alimentos_priorizar, alimentos_evitar, "
            "exames_solicitados, orientacoes_treino, monitoramento e observacoes_finais. "
            "Nao inclua informacoes de contato dentro de plano_refeicoes. "
            "Retorne SOMENTE campos com evidencias textuais; nao devolva campos vazios desnecessarios. "
            "Quando houver medidas com numeros, separe valor e unidade quando possivel. "
            f"Texto consolidado: {texto_consolidado}"
        )
        try:
            return self._client.generate_json_from_text(
                model=self._settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except APIConnectionError as exc:
            self._logger.exception("Falha de conexao com a OpenAI em estruturacao de plano alimentar")
            raise ServiceError("Falha de conexao com a OpenAI.", status_code=502) from exc
        except APIError as exc:
            self._logger.exception("Erro da OpenAI em estruturacao de plano alimentar")
            raise ServiceError(f"Erro da OpenAI: {exc.__class__.__name__}", status_code=502) from exc
        except ValueError as exc:
            self._logger.exception("Resposta da OpenAI nao retornou JSON valido para plano alimentar")
            raise ServiceError("Resposta da OpenAI em formato invalido para plano alimentar.", status_code=502) from exc

    def _executar_agente_refeicoes(
        self,
        *,
        contexto: str,
        idioma: str,
        pipeline_context: PlanoAlimentarPipelineContext,
    ) -> dict[str, Any]:
        # Agente dedicado para refeicoes segmentadas; falha aqui nao derruba request.
        secoes = pipeline_context.secoes_para_prompt()
        if not secoes:
            return {}

        system_prompt = (
            "Voce e um agente especialista em estruturar plano de refeicoes. "
            "Responda apenas JSON valido, sem markdown. "
            "Nao inclua endereco, telefone, redes sociais, assinatura profissional ou dados administrativos."
        )
        user_prompt = (
            f"Idioma de resposta: {idioma}. "
            f"Contexto recebido: {contexto}. "
            "Retorne JSON no formato {'plano_refeicoes': [...]} com schema: "
            "nome_refeicao, horario, opcoes[], cada opcao com titulo, itens[], observacoes. "
            "Cada item deve ter: alimento, quantidade_texto, quantidade_valor, unidade, quantidade_gramas, observacoes. "
            "So inclua alimentos/composicoes de refeicao. "
            "Se nao houver evidencia para algum campo, omita o campo ao inves de preencher null. "
            f"Secoes segmentadas: {json.dumps(secoes, ensure_ascii=False)}"
        )
        try:
            return self._client.generate_json_from_text(
                model=self._settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except (APIConnectionError, APIError, ValueError):
            self._logger.exception("Falha na etapa de extracao dedicada de refeicoes")
            return {}

    def _mesclar_refeicoes(
        self,
        *,
        plano: PlanoAlimentarEstruturado,
        payload_refeicoes: dict[str, Any],
        pipeline_context: PlanoAlimentarPipelineContext,
    ) -> None:
        # Merge por prioridade: refeicoes LLM dedicadas > heuristica > extraida no payload geral.
        refeicoes_llm = _normalizar_refeicoes(payload_refeicoes.get("plano_refeicoes"))
        refeicoes_heuristica = _refeicoes_heuristicas_from_context(pipeline_context)

        if refeicoes_llm:
            plano.plano_refeicoes = _merge_refeicoes(plano.plano_refeicoes, refeicoes_llm)

        if refeicoes_heuristica:
            # Evita duplicar ruido heuristico quando ja existe refeicao valida para o mesmo titulo.
            refeicoes_heuristica = _filtrar_refeicoes_heuristicas_por_base(
                refeicoes_heuristica=refeicoes_heuristica,
                base=plano.plano_refeicoes,
            )
            plano.plano_refeicoes = _merge_refeicoes(plano.plano_refeicoes, refeicoes_heuristica)

    def _enriquecer_profissional(self, *, plano: PlanoAlimentarEstruturado, texto: str) -> None:
        if not plano.profissional:
            return

        if not _to_optional_str(plano.profissional.registro_profissional):
            match = re.search(r"(?i)\bcrn\s*[:\-]?\s*(\d{3,6})\b", texto)
            if match:
                plano.profissional.registro_profissional = f"CRN {match.group(1)}"

    def _enriquecer_hidratacao(self, *, plano: PlanoAlimentarEstruturado, texto: str) -> None:
        if plano.hidratacao is None:
            plano.hidratacao = HidratacaoPlano()

        if plano.hidratacao.meta_ml_dia is None:
            range_match = re.search(
                r"(?is)\b(?:meta|hidratacao|ingestao|consumo|diario|dia)\b[^.\n]{0,40}?"
                r"(\d{2,4})\s*ml\s*[-a]\s*(\d{2,4})\s*ml",
                texto,
            )
            if not range_match:
                range_match = re.search(
                    r"(?is)(\d{2,4})\s*ml\s*[-a]\s*(\d{2,4})\s*ml[^.\n]{0,40}"
                    r"\b(?:meta|hidratacao|ingestao|consumo|diario|dia)\b",
                    texto,
                )
            if range_match:
                first = _to_optional_float(range_match.group(1))
                second = _to_optional_float(range_match.group(2))
                if first is not None and second is not None:
                    plano.hidratacao.meta_ml_dia = round((first + second) / 2.0, 4)
            else:
                single_match = re.search(
                    r"(?is)\b(?:meta|hidratacao|ingestao|consumo|diario|dia)\b[^.\n]{0,40}(\d{2,4})\s*ml",
                    texto,
                )
                if not single_match:
                    single_match = re.search(
                        r"(?is)(\d{2,4})\s*ml[^.\n]{0,40}\b(?:meta|hidratacao|ingestao|consumo|diario|dia)\b",
                        texto,
                    )
                if single_match:
                    single = _to_optional_float(single_match.group(1))
                    if single is not None:
                        plano.hidratacao.meta_ml_dia = single

        if not plano.hidratacao.orientacoes and "agua" in _normalizar_nome(texto):
            if "saborizada" in _normalizar_nome(texto):
                plano.hidratacao.orientacoes = ["agua saborizada"]

    def _enriquecer_suplementos_com_dose(
        self,
        *,
        plano: PlanoAlimentarEstruturado,
        texto: str,
    ) -> None:
        # Ex.: 'Whey protein: 45 g' deve preencher dose quando vier explicita.
        doses_por_nome = _extrair_doses_suplementos(texto)
        if not doses_por_nome:
            return

        for suplemento in plano.suplementos:
            chave = _normalizar_nome(suplemento.nome)
            dose_texto = doses_por_nome.get(chave)
            if dose_texto and not _to_optional_str(suplemento.dose):
                suplemento.dose = dose_texto
                suplemento.origem_dado = "regra_textual"
                suplemento.precisa_revisao = False
                suplemento.motivo_revisao = None

        nomes_existentes = {_normalizar_nome(item.nome) for item in plano.suplementos}
        for nome, dose in doses_por_nome.items():
            if nome in nomes_existentes:
                continue
            plano.suplementos.append(
                SuplementoPlano(
                    nome=nome,
                    dose=dose,
                    observacoes="extraido_por_regra_textual",
                    origem_dado="regra_textual",
                )
            )

    def _sanitizar_plano_refeicoes(self, *, plano: PlanoAlimentarEstruturado) -> None:
        refeicoes_limpas: list[RefeicaoPlano] = []
        for refeicao in plano.plano_refeicoes:
            opcoes_limpas: list[OpcaoRefeicaoPlano] = []
            for opcao in refeicao.opcoes:
                itens_limpos: list[ItemAlimentarPlano] = []
                for item in opcao.itens:
                    if _is_invalid_food_label(item.alimento):
                        continue
                    itens_limpos.append(item)
                if not itens_limpos:
                    continue
                opcoes_limpas.append(
                    OpcaoRefeicaoPlano(
                        titulo=opcao.titulo,
                        itens=itens_limpos,
                        observacoes=_to_optional_str(opcao.observacoes),
                        origem_dado=opcao.origem_dado,
                    )
                )

            if not opcoes_limpas:
                continue

            refeicoes_limpas.append(
                RefeicaoPlano(
                    nome_refeicao=refeicao.nome_refeicao,
                    horario=refeicao.horario,
                    opcoes=opcoes_limpas,
                    observacoes=refeicao.observacoes,
                    origem_dado=refeicao.origem_dado,
                    confianca=refeicao.confianca,
                )
            )

        plano.plano_refeicoes = refeicoes_limpas

    def _deduplicar_plano_refeicoes(self, *, plano: PlanoAlimentarEstruturado) -> None:
        deduped_refeicoes: list[RefeicaoPlano] = []
        index_by_name: dict[str, int] = {}

        for refeicao in plano.plano_refeicoes:
            opcoes_limpas = _dedupe_opcoes(refeicao.opcoes)
            if not opcoes_limpas:
                continue

            current = RefeicaoPlano(
                nome_refeicao=refeicao.nome_refeicao,
                horario=refeicao.horario,
                opcoes=opcoes_limpas,
                observacoes=refeicao.observacoes,
                origem_dado=refeicao.origem_dado,
                confianca=refeicao.confianca,
            )

            key = _normalizar_nome(current.nome_refeicao)
            existing_idx = index_by_name.get(key)
            if existing_idx is None:
                index_by_name[key] = len(deduped_refeicoes)
                deduped_refeicoes.append(current)
                continue

            existing = deduped_refeicoes[existing_idx]
            existing.opcoes = _dedupe_opcoes(existing.opcoes + current.opcoes)
            if not existing.observacoes and current.observacoes:
                existing.observacoes = current.observacoes

        plano.plano_refeicoes = deduped_refeicoes

    def _normalizar_plano(self, payload: dict[str, Any]) -> PlanoAlimentarEstruturado:
        raw_plan = payload.get("plano_alimentar") if isinstance(payload.get("plano_alimentar"), dict) else payload
        if not isinstance(raw_plan, dict):
            return PlanoAlimentarEstruturado()

        return PlanoAlimentarEstruturado(
            tipo_plano=_to_optional_str(raw_plan.get("tipo_plano") or raw_plan.get("plan_type")),
            data_plano=_to_optional_str(raw_plan.get("data_plano") or raw_plan.get("plan_date")),
            validade_inicio=_to_optional_str(raw_plan.get("validade_inicio")),
            validade_fim=_to_optional_str(raw_plan.get("validade_fim")),
            profissional=_normalizar_profissional(raw_plan.get("profissional")),
            paciente=_normalizar_paciente(raw_plan.get("paciente")),
            objetivos=_to_list_str(raw_plan.get("objetivos")),
            orientacoes_gerais=_to_list_str(raw_plan.get("orientacoes_gerais")),
            comportamento_alimentar=_to_list_str(raw_plan.get("comportamento_alimentar")),
            hidratacao=_normalizar_hidratacao(raw_plan.get("hidratacao")),
            suplementos=_normalizar_suplementos(raw_plan.get("suplementos")),
            metas_nutricionais=_normalizar_metas(raw_plan.get("metas_nutricionais")),
            plano_refeicoes=_normalizar_refeicoes(raw_plan.get("plano_refeicoes")),
            alimentos_priorizar=_to_list_str(raw_plan.get("alimentos_priorizar")),
            alimentos_evitar=_to_list_str(raw_plan.get("alimentos_evitar")),
            substituicoes=_normalizar_substituicoes(raw_plan.get("substituicoes")),
            exames_solicitados=_to_list_str(raw_plan.get("exames_solicitados")),
            orientacoes_treino=_to_list_str(raw_plan.get("orientacoes_treino")),
            monitoramento=_to_list_str(raw_plan.get("monitoramento")),
            observacoes_finais=_to_list_str(raw_plan.get("observacoes_finais")),
        )


def _normalizar_profissional(value: Any) -> ProfissionalPlano | None:
    if not isinstance(value, dict):
        return None
    contato_raw = value.get("contato") if isinstance(value.get("contato"), dict) else {}
    contato = ContatoProfissionalPlano(
        telefone=_to_optional_str(contato_raw.get("telefone")),
        email=_to_optional_str(contato_raw.get("email")),
        instagram=_to_optional_str(contato_raw.get("instagram")),
        endereco=_to_optional_str(contato_raw.get("endereco")),
    )
    return ProfissionalPlano(
        nome=_to_optional_str(value.get("nome")),
        registro_profissional=_to_optional_str(value.get("registro_profissional") or value.get("registro")),
        especialidades=_to_list_str(value.get("especialidades")),
        contato=contato,
    )


def _normalizar_paciente(value: Any) -> PacientePlano | None:
    if not isinstance(value, dict):
        return None
    return PacientePlano(
        nome=_to_optional_str(value.get("nome")),
        sexo=_to_optional_str(value.get("sexo")),
        idade_anos=_to_optional_float(value.get("idade_anos") or value.get("idade")),
        peso_kg=_to_optional_float(value.get("peso_kg") or value.get("peso")),
        altura_cm=_to_optional_float(value.get("altura_cm") or value.get("altura")),
        imc=_to_optional_float(value.get("imc")),
        condicoes_clinicas=_to_list_str(value.get("condicoes_clinicas")),
        alergias_alimentares=_to_list_str(value.get("alergias_alimentares")),
        restricoes_alimentares=_to_list_str(value.get("restricoes_alimentares")),
        sintomas_relatados=_to_list_str(value.get("sintomas_relatados")),
    )


def _normalizar_hidratacao(value: Any) -> HidratacaoPlano | None:
    if not isinstance(value, dict):
        return None
    return HidratacaoPlano(
        meta_ml_dia=_to_optional_float(value.get("meta_ml_dia") or value.get("meta_agua_ml")),
        orientacoes=_to_list_str(value.get("orientacoes")),
    )


def _normalizar_suplementos(value: Any) -> list[SuplementoPlano]:
    if not isinstance(value, list):
        return []
    result: list[SuplementoPlano] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        nome = _to_optional_str(item.get("nome"))
        if not nome:
            continue
        result.append(
            SuplementoPlano(
                nome=nome,
                dose=_to_optional_str(item.get("dose")),
                frequencia=_to_optional_str(item.get("frequencia")),
                horario=_to_optional_str(item.get("horario")),
                observacoes=_to_optional_str(item.get("observacoes")),
                origem_dado=_to_optional_str(item.get("origem_dado")) or "llm",
                precisa_revisao=bool(item.get("precisa_revisao", False)),
                motivo_revisao=_to_optional_str(item.get("motivo_revisao")),
            )
        )
    return result


def _normalizar_metas(value: Any) -> MetasNutricionaisPlano | None:
    if not isinstance(value, dict):
        return None
    return MetasNutricionaisPlano(
        calorias_kcal=_to_optional_float(value.get("calorias_kcal")),
        proteina_g=_to_optional_float(value.get("proteina_g")),
        carboidratos_g=_to_optional_float(value.get("carboidratos_g")),
        lipidios_g=_to_optional_float(value.get("lipidios_g")),
        fibras_g=_to_optional_float(value.get("fibras_g")),
    )


def _normalizar_refeicoes(value: Any) -> list[RefeicaoPlano]:
    if not isinstance(value, list):
        return []

    refeicoes: list[RefeicaoPlano] = []
    for refeicao_raw in value:
        if not isinstance(refeicao_raw, dict):
            continue

        nome_refeicao = _to_optional_str(refeicao_raw.get("nome_refeicao"))
        if not nome_refeicao:
            continue

        opcoes_raw = refeicao_raw.get("opcoes")
        opcoes: list[OpcaoRefeicaoPlano] = []
        if isinstance(opcoes_raw, list):
            for opcao_raw in opcoes_raw:
                if not isinstance(opcao_raw, dict):
                    continue

                itens_raw = opcao_raw.get("itens")
                itens: list[ItemAlimentarPlano] = []
                if isinstance(itens_raw, list):
                    for item_raw in itens_raw:
                        if not isinstance(item_raw, dict):
                            continue
                        alimento = _to_optional_str(item_raw.get("alimento"))
                        if not alimento:
                            continue
                        itens.append(
                            ItemAlimentarPlano(
                                alimento=alimento,
                                quantidade_texto=_to_optional_str(item_raw.get("quantidade_texto")),
                                quantidade_valor=_to_optional_float(item_raw.get("quantidade_valor")),
                                unidade=_to_optional_str(item_raw.get("unidade")),
                                quantidade_gramas=_to_optional_float(item_raw.get("quantidade_gramas")),
                                observacoes=_to_optional_str(item_raw.get("observacoes")),
                                origem_dado=_to_optional_str(item_raw.get("origem_dado")) or "llm",
                                precisa_revisao=bool(item_raw.get("precisa_revisao", False)),
                                motivo_revisao=_to_optional_str(item_raw.get("motivo_revisao")),
                            )
                        )

                opcoes.append(
                    OpcaoRefeicaoPlano(
                        titulo=_to_optional_str(opcao_raw.get("titulo")),
                        itens=itens,
                        observacoes=_to_optional_str(opcao_raw.get("observacoes")),
                        origem_dado=_to_optional_str(opcao_raw.get("origem_dado")) or "llm",
                    )
                )

        refeicoes.append(
            RefeicaoPlano(
                nome_refeicao=nome_refeicao,
                horario=_to_optional_str(refeicao_raw.get("horario")),
                opcoes=opcoes,
                observacoes=_to_optional_str(refeicao_raw.get("observacoes")),
                origem_dado=_to_optional_str(refeicao_raw.get("origem_dado")) or "llm",
                confianca=_to_optional_float(refeicao_raw.get("confianca")),
            )
        )

    return refeicoes


def _normalizar_substituicoes(value: Any) -> list[SubstituicaoPlano]:
    if not isinstance(value, list):
        return []
    result: list[SubstituicaoPlano] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        result.append(
            SubstituicaoPlano(
                refeicao=_to_optional_str(item.get("refeicao")),
                item_original=_to_optional_str(item.get("item_original")),
                item_substituto=_to_optional_str(item.get("item_substituto")),
                proporcao=_to_optional_str(item.get("proporcao")),
                observacoes=_to_optional_str(item.get("observacoes")),
            )
        )
    return result


def _refeicoes_heuristicas_from_context(context: PlanoAlimentarPipelineContext) -> list[RefeicaoPlano]:
    refeicoes: list[RefeicaoPlano] = []
    for secao in context.secoes_refeicao:
        if not secao.opcoes_heuristicas:
            continue
        refeicoes.append(
            RefeicaoPlano(
                nome_refeicao=secao.nome_refeicao,
                opcoes=[
                    OpcaoRefeicaoPlano(
                        titulo=opcao.titulo,
                        itens=opcao.itens,
                        observacoes=opcao.observacoes,
                        origem_dado=opcao.origem_dado or "heuristica",
                    )
                    for opcao in secao.opcoes_heuristicas
                ],
                observacoes="extraido_por_segmentacao_heuristica",
                origem_dado="heuristica",
            )
        )
    return refeicoes


def _merge_refeicoes(base: list[RefeicaoPlano], incoming: list[RefeicaoPlano]) -> list[RefeicaoPlano]:
    if not base:
        return incoming

    merged = list(base)
    index_by_name = {_normalizar_nome(item.nome_refeicao): idx for idx, item in enumerate(merged)}

    for refeicao in incoming:
        key = _normalizar_nome(refeicao.nome_refeicao)
        idx = index_by_name.get(key)
        if idx is None:
            index_by_name[key] = len(merged)
            merged.append(refeicao)
            continue

        current = merged[idx]
        if not current.opcoes and refeicao.opcoes:
            current.opcoes = refeicao.opcoes
            if not current.observacoes:
                current.observacoes = refeicao.observacoes
            continue

        if refeicao.opcoes:
            current.opcoes = _merge_opcoes(current.opcoes, refeicao.opcoes)
            if not current.observacoes:
                current.observacoes = refeicao.observacoes

    return merged


def _merge_opcoes(base: list[OpcaoRefeicaoPlano], incoming: list[OpcaoRefeicaoPlano]) -> list[OpcaoRefeicaoPlano]:
    if not base:
        return [opcao for opcao in incoming if _opcao_tem_itens_validos(opcao)]

    merged = list(base)
    signatures = {_opcao_signature(opcao) for opcao in merged}

    for opcao in incoming:
        if not _opcao_tem_itens_validos(opcao):
            continue
        signature = _opcao_signature(opcao)
        if signature in signatures:
            continue
        signatures.add(signature)
        merged.append(opcao)

    return merged


def _filtrar_refeicoes_heuristicas_por_base(
    *,
    refeicoes_heuristica: list[RefeicaoPlano],
    base: list[RefeicaoPlano],
) -> list[RefeicaoPlano]:
    if not refeicoes_heuristica or not base:
        return refeicoes_heuristica

    refeicoes_base_com_conteudo = {
        _normalizar_nome(refeicao.nome_refeicao)
        for refeicao in base
        if _refeicao_tem_itens_validos(refeicao)
    }
    if not refeicoes_base_com_conteudo:
        return refeicoes_heuristica

    filtradas: list[RefeicaoPlano] = []
    for refeicao in refeicoes_heuristica:
        if _normalizar_nome(refeicao.nome_refeicao) in refeicoes_base_com_conteudo:
            continue
        filtradas.append(refeicao)
    return filtradas


def _refeicao_tem_itens_validos(refeicao: RefeicaoPlano) -> bool:
    return any(_opcao_tem_itens_validos(opcao) for opcao in refeicao.opcoes)


def _opcao_tem_itens_validos(opcao: OpcaoRefeicaoPlano) -> bool:
    for item in opcao.itens:
        if not _is_invalid_food_label(item.alimento):
            return True
    return False


def _opcao_signature(opcao: OpcaoRefeicaoPlano) -> tuple[str, tuple[str, ...]]:
    titulo = _normalizar_nome(opcao.titulo or "")
    alimentos = tuple(
        _normalizar_nome(item.alimento)
        for item in opcao.itens
        if not _is_invalid_food_label(item.alimento)
    )
    return titulo, alimentos


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _to_list_str(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = _to_optional_str(item)
            if text:
                result.append(text)
        return result
    text = _to_optional_str(value)
    if not text:
        return []
    separators = r"[;\n\|]"
    parts = [part.strip() for part in re.split(separators, text) if part.strip()]
    return parts or [text]


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if not text or text in {"na", "n/a", "nd", "tr", "-", "--"}:
            return None
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                normalized = text.replace(".", "").replace(",", ".")
            else:
                normalized = text.replace(",", "")
        elif "," in text:
            normalized = text.replace(".", "").replace(",", ".")
        else:
            normalized = text
        normalized = re.sub(r"[^0-9.\-]", "", normalized)
        if not normalized or normalized in {".", "-", "-."}:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _normalizar_nome(value: str) -> str:
    lowered = value.strip().lower()
    normalized = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", normalized).strip()


def _extrair_doses_suplementos(texto: str) -> dict[str, str]:
    padroes = [
        ("whey protein", r"whey(?:\s*protein)?"),
        ("creatina", r"creatina"),
        ("albumina", r"albumina"),
        ("caseina", r"caseina"),
        ("omega 3", r"omega[\s\-]*3"),
        ("multivitaminico", r"multivitaminic[oa]"),
    ]
    doses: dict[str, str] = {}
    for nome_canonico, padrao_nome in padroes:
        match = re.search(
            rf"(?is)\b{padrao_nome}\b[^0-9\n]{{0,24}}(\d+(?:[.,]\d+)?)\s*(g|mg|ml|mcg|ug)\b",
            texto,
        )
        if not match:
            continue
        valor = match.group(1).replace(",", ".")
        unidade = match.group(2).lower()
        doses[nome_canonico] = f"{valor} {unidade}"
    return doses


def _extrair_bullets(texto: str, max_items: int) -> list[str]:
    linhas = [linha.strip(" -*\t") for linha in texto.splitlines()]
    bullets: list[str] = []
    for linha in linhas:
        if not linha or len(linha) < 8:
            continue
        if is_noise_food_text(linha) or _is_orientacao_ruido(linha):
            continue
        if not _is_orientacao_relevante(linha):
            continue
        bullets.append(linha)
        if len(bullets) >= max_items:
            break
    return bullets


def _sanitizar_orientacoes(orientacoes: list[str]) -> list[str]:
    resultado: list[str] = []
    for item in orientacoes:
        text = _to_optional_str(item)
        if not text:
            continue
        if _is_qtd_alimento_line(text):
            continue
        if is_noise_food_text(text) or _is_orientacao_ruido(text):
            continue
        if not _is_orientacao_relevante(text):
            continue
        if text not in resultado:
            resultado.append(text)
    return resultado


def _inferir_objetivos_basicos(texto: str, idioma: str) -> list[str]:
    _ = idioma
    normalizado = _normalizar_nome(texto)
    objetivos: list[str] = []
    if "reducao" in normalizado or "emagrec" in normalizado:
        objetivos.append("reducao de peso")
    if "musculacao" in normalizado or "treino" in normalizado:
        objetivos.append("suporte ao treino")
    if "fadiga" in normalizado or "falta de energia" in normalizado:
        objetivos.append("melhora de energia")
    return objetivos


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        text = _to_optional_str(value)
        if not text:
            continue
        if text not in deduped:
            deduped.append(text)
    return deduped


def _is_invalid_food_label(value: str | None) -> bool:
    text = _to_optional_str(value)
    if not text:
        return True
    if is_noise_food_text(text):
        return True

    normalized = _normalizar_nome(text)
    if normalized.startswith("qtd:") or normalized.startswith("qtd "):
        return True
    if normalized.startswith("alimento:") or "| alimento:" in normalized:
        return True
    return False


def _is_orientacao_ruido(value: str) -> bool:
    normalized = _normalizar_nome(value)
    markers = (
        "dra ",
        "dr ",
        "nutricionista",
        "especialista",
        "metodo",
        "crn",
        "composicao alimentar",
        "pedido de exames em pdf",
    )
    return any(marker in normalized for marker in markers)


def _is_orientacao_relevante(value: str) -> bool:
    normalized = _normalizar_nome(value)
    if len(normalized) < 8:
        return False
    if _is_qtd_alimento_line(normalized):
        return False

    keywords = (
        "comer",
        "beber",
        "ingerir",
        "agua",
        "refeicao",
        "treino",
        "musculacao",
        "cardio",
        "garfo",
        "faca",
        "sem telas",
        "descansar os talheres",
        "devagar",
    )
    return any(keyword in normalized for keyword in keywords)


def _is_qtd_alimento_line(value: str) -> bool:
    normalized = _normalizar_nome(value)
    return bool(re.match(r"^qtd:\s*.+\|\s*alimento:\s*.+$", normalized))


def _dedupe_opcoes(opcoes: list[OpcaoRefeicaoPlano]) -> list[OpcaoRefeicaoPlano]:
    deduped: list[OpcaoRefeicaoPlano] = []
    signatures: set[tuple[str, tuple[str, ...]]] = set()

    for opcao in opcoes:
        itens = _dedupe_itens(opcao.itens)
        if not itens:
            continue
        current = OpcaoRefeicaoPlano(
            titulo=opcao.titulo,
            itens=itens,
            observacoes=opcao.observacoes,
            origem_dado=opcao.origem_dado,
        )
        signature = _opcao_signature(current)
        if signature in signatures:
            continue
        signatures.add(signature)
        deduped.append(current)

    return deduped


def _dedupe_itens(itens: list[ItemAlimentarPlano]) -> list[ItemAlimentarPlano]:
    deduped: list[ItemAlimentarPlano] = []
    seen: set[tuple[str, str, str]] = set()

    for item in itens:
        if _is_invalid_food_label(item.alimento):
            continue
        alimento_key = _normalizar_nome(item.alimento)
        qtd_key = _normalizar_nome(item.quantidade_texto or "")
        gramas_key = "" if item.quantidade_gramas is None else f"{item.quantidade_gramas:.4f}"
        signature = (alimento_key, qtd_key, gramas_key)
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(item)

    return deduped

