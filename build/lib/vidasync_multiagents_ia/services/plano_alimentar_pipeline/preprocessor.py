import re
import unicodedata
from dataclasses import dataclass, field

from vidasync_multiagents_ia.schemas import ItemAlimentarPlano, OpcaoRefeicaoPlano

_REFEICAO_PATTERNS: dict[str, tuple[str, ...]] = {
    "cafe_da_manha": ("cafe da manha", "desjejum"),
    "lanche_da_manha": ("lanche da manha", "colacao"),
    "almoco": ("almoco",),
    "lanche_da_tarde": ("lanche da tarde",),
    "jantar": ("jantar",),
    "ceia": ("ceia",),
    "pre_treino": ("pre treino", "pre-treino"),
    "pos_treino": ("pos treino", "pos-treino"),
    "almoco_e_jantar": ("almoco e jantar",),
}

_CONTACT_NOISE_MARKERS = (
    "endereco",
    "rua ",
    "celular",
    "whatsapp",
    "instagram",
    "e-mail",
    " email",
    "crn",
    "nutricionista",
    "especialista",
    "usp",
    "unifesp",
    "franco da rocha",
)

_NOISE_FOOD_MARKERS = (
    "endereco",
    "celular",
    "whatsapp",
    "instagram",
    "e-mail",
    "@",
    "rua ",
    "sala ",
    "crn",
)


@dataclass(slots=True)
class SecaoRefeicaoPipeline:
    nome_refeicao: str
    conteudo: str
    opcoes_heuristicas: list[OpcaoRefeicaoPlano] = field(default_factory=list)


@dataclass(slots=True)
class PlanoAlimentarPipelineContext:
    texto_consolidado: str
    texto_limpo: str
    texto_sem_ruido: str
    secoes_refeicao: list[SecaoRefeicaoPipeline]

    def secoes_para_prompt(self) -> list[dict[str, str]]:
        return [{"nome_refeicao": secao.nome_refeicao, "conteudo": secao.conteudo} for secao in self.secoes_refeicao]


class PlanoAlimentarPreprocessor:
    def preparar_contexto(self, textos_fonte: list[str]) -> PlanoAlimentarPipelineContext:
        texto_consolidado = "\n\n---\n\n".join(texto.strip() for texto in textos_fonte if texto and texto.strip())
        linhas_limpo = _normalizar_linhas(texto_consolidado)
        linhas_deduplicadas = _deduplicar_linhas(linhas_limpo)
        texto_limpo = "\n".join(linhas_deduplicadas)

        linhas_sem_ruido = [linha for linha in linhas_deduplicadas if not _is_contact_noise_line(linha)]
        texto_sem_ruido = "\n".join(linhas_sem_ruido)

        secoes = self._segmentar_secoes_refeicao(linhas_sem_ruido)
        if not secoes and _tem_opcoes_numeradas(texto_sem_ruido):
            secoes = [SecaoRefeicaoPipeline(nome_refeicao="refeicoes_gerais", conteudo=texto_sem_ruido)]

        for secao in secoes:
            secao.opcoes_heuristicas = _extrair_opcoes_do_bloco(secao.conteudo)

        return PlanoAlimentarPipelineContext(
            texto_consolidado=texto_consolidado,
            texto_limpo=texto_limpo,
            texto_sem_ruido=texto_sem_ruido,
            secoes_refeicao=secoes,
        )

    def _segmentar_secoes_refeicao(self, linhas: list[str]) -> list[SecaoRefeicaoPipeline]:
        secoes_map: dict[str, list[str]] = {}
        ordem: list[str] = []
        secoes_pendentes: list[str] = []
        secoes_pendentes_com_conteudo = False

        for linha in linhas:
            nome_detectado = _detect_refeicao_heading(linha)
            if nome_detectado:
                # /**** Suporta lista de titulos consecutivos (ex.: Cafe/Lanche/Ceia) antes das opcoes. ****/
                if secoes_pendentes and secoes_pendentes_com_conteudo:
                    secoes_pendentes = [nome_detectado]
                    secoes_pendentes_com_conteudo = False
                elif nome_detectado not in secoes_pendentes:
                    secoes_pendentes.append(nome_detectado)

                if nome_detectado not in secoes_map:
                    secoes_map[nome_detectado] = []
                    ordem.append(nome_detectado)
                continue

            if not secoes_pendentes:
                continue

            linha_limpa = linha.strip()
            if not linha_limpa:
                continue

            for secao in secoes_pendentes:
                secoes_map[secao].append(linha_limpa)
            secoes_pendentes_com_conteudo = True

        secoes: list[SecaoRefeicaoPipeline] = []
        for nome in ordem:
            conteudo = "\n".join(secoes_map.get(nome, []))
            if not conteudo.strip():
                continue
            secoes.append(SecaoRefeicaoPipeline(nome_refeicao=nome, conteudo=conteudo.strip()))
        return secoes


def is_noise_food_text(value: str) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return True
    return any(marker in normalized for marker in _NOISE_FOOD_MARKERS)


def _normalizar_linhas(texto: str) -> list[str]:
    texto = texto.replace("```", "")
    linhas = []
    for raw_line in texto.splitlines():
        line = raw_line.replace("\t", " ")
        line = re.sub(r"\s+", " ", line).strip()
        if line and set(line) == {"-"}:
            continue
        if line:
            linhas.append(line)
    return linhas


def _deduplicar_linhas(linhas: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for linha in linhas:
        chave = _normalize_text(linha)
        if chave in seen:
            continue
        seen.add(chave)
        result.append(linha)
    return result


def _is_contact_noise_line(linha: str) -> bool:
    normalized = _normalize_text(linha)
    if not normalized:
        return True
    return any(marker in normalized for marker in _CONTACT_NOISE_MARKERS)


def _detect_refeicao_heading(linha: str) -> str | None:
    normalized = _normalize_text(linha)
    normalized = normalized.strip("[]")
    normalized = re.sub(r"\b([01]?\d|2[0-3]):[0-5]\d\b", "", normalized)
    normalized = normalized.strip(" :-")
    for canonical_name, patterns in _REFEICAO_PATTERNS.items():
        for pattern in patterns:
            if normalized == pattern or normalized.startswith(f"{pattern} "):
                return canonical_name
    return None


def _tem_opcoes_numeradas(texto: str) -> bool:
    return bool(re.search(r"(?m)^\s*\d+[\.\)]\s+", texto))


def _extrair_opcoes_do_bloco(texto: str) -> list[OpcaoRefeicaoPlano]:
    blocos = re.findall(r"(?ms)(?:^|\n)\s*(\d+)[\.\)]\s*(.+?)(?=(?:\n\s*\d+[\.\)]\s*)|\Z)", texto)
    if not blocos:
        return _extrair_opcoes_sem_numeracao(texto)

    opcoes: list[OpcaoRefeicaoPlano] = []
    for numero, bloco in blocos:
        opcoes.append(_build_option(titulo=f"opcao {numero}", bloco=bloco))
    return [opcao for opcao in opcoes if opcao.itens]


def _extrair_opcoes_sem_numeracao(texto: str) -> list[OpcaoRefeicaoPlano]:
    linhas_candidatas = []
    for linha in texto.splitlines():
        line = linha.strip(" -")
        if not line:
            continue
        if "+" in line or " com " in _normalize_text(line):
            linhas_candidatas.append(line)

    opcoes: list[OpcaoRefeicaoPlano] = []
    for index, linha in enumerate(linhas_candidatas, start=1):
        opcoes.append(_build_option(titulo=f"opcao {index}", bloco=linha))
    return [opcao for opcao in opcoes if opcao.itens]


def _build_option(titulo: str, bloco: str) -> OpcaoRefeicaoPlano:
    texto_curto = re.sub(r"\s+", " ", bloco).strip()
    primeira_linha = bloco.splitlines()[0] if bloco.splitlines() else bloco
    alimentos = _extrair_alimentos_da_linha(primeira_linha)
    quantidades = re.findall(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|und|unid|unidade)\b", bloco, flags=re.IGNORECASE)

    itens: list[ItemAlimentarPlano] = []
    for index, alimento in enumerate(alimentos):
        valor_raw: str | None = None
        unidade_raw: str | None = None
        if index < len(quantidades):
            valor_raw, unidade_raw = quantidades[index]

        quantidade_texto: str | None = None
        quantidade_valor: float | None = None
        unidade: str | None = None
        quantidade_gramas: float | None = None

        if valor_raw and unidade_raw:
            unidade = unidade_raw.lower()
            quantidade_valor = _to_optional_float(valor_raw)
            quantidade_texto = f"{valor_raw} {unidade}"
            if quantidade_valor is not None:
                if unidade == "kg":
                    quantidade_gramas = round(quantidade_valor * 1000.0, 4)
                elif unidade == "g":
                    quantidade_gramas = quantidade_valor

        itens.append(
            ItemAlimentarPlano(
                alimento=alimento,
                quantidade_texto=quantidade_texto,
                quantidade_valor=quantidade_valor,
                unidade=unidade,
                quantidade_gramas=quantidade_gramas,
                origem_dado="heuristica",
                precisa_revisao=quantidade_gramas is None,
                motivo_revisao="Quantidade em gramas nao definida." if quantidade_gramas is None else None,
            )
        )

    observacoes = texto_curto[:300] if texto_curto else None
    return OpcaoRefeicaoPlano(
        titulo=titulo,
        itens=itens,
        observacoes=observacoes,
        origem_dado="heuristica",
    )


def _extrair_alimentos_da_linha(linha: str) -> list[str]:
    base = re.sub(r"^\s*\d+[\.\)]\s*", "", linha).strip().rstrip(".;")
    if not base:
        return []

    partes: list[str] = []
    for bloco in base.split("+"):
        bloco_limpo = bloco.strip(" ,.;")
        if not bloco_limpo:
            continue
        if " com " in _normalize_text(bloco_limpo):
            subpartes = [p.strip(" ,.;") for p in re.split(r"\bcom\b", bloco_limpo, flags=re.IGNORECASE)]
            partes.extend([item for item in subpartes if len(item) >= 2])
        else:
            partes.append(bloco_limpo)

    deduplicados: list[str] = []
    for item in partes:
        item_limpo = re.sub(r"\s+", " ", item).strip()
        if not item_limpo or is_noise_food_text(item_limpo):
            continue
        if item_limpo not in deduplicados:
            deduplicados.append(item_limpo)
    return deduplicados


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip()


def _to_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
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
