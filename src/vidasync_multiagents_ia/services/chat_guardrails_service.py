import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from vidasync_multiagents_ia.schemas import ChatUIAction, IntencaoChatNome


@dataclass(frozen=True, slots=True)
class ChatGuardrailDecision:
    handler: str
    response: str
    tipo: Literal["bloqueio_conteudo", "quantidade_fora_da_faixa", "redirecionamento_fluxo_app"]
    status: Literal["sucesso", "parcial", "erro"] = "parcial"
    warnings: list[str] = field(default_factory=list)
    precisa_revisao: bool = False
    acoes_ui: list[ChatUIAction] = field(default_factory=list)
    metadados: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _FeatureRedirectRule:
    nome: str
    handler: str
    response: str
    acao_ui: ChatUIAction
    termos: tuple[str, ...] = ()
    intencoes: tuple[IntencaoChatNome, ...] = ()


class ChatGuardrailsService:
    _UNSAFE_TERMS: tuple[str, ...] = (
        "cu",
        "buceta",
        "xota",
        "xoxota",
        "pau",
        "pica",
        "rola",
        "piroca",
        "penis",
        "vagina",
        "anus",
        "gozar",
        "sexo oral",
        "sexo anal",
        "boquete",
        "siririca",
        "punheta",
        "masturbacao",
        "transar",
    )
    _QUANTITY_PATTERN = re.compile(
        r"(?P<valor>\d+(?:[.,]\d+)?)\s*(?P<unidade>"
        r"kg|quilo|quilos|g|grama|gramas|ml|millilitro|millilitros|l|litro|litros|"
        r"unidade|unidades|un|porcao|porcoes|xicara|xicaras|colher|colheres"
        r")\b"
    )
    _LIMITS_BY_UNIT: dict[str, float] = {
        "kg": 10.0,
        "g": 5000.0,
        "ml": 5000.0,
        "l": 5.0,
        "unidade": 25.0,
        "porcao": 10.0,
        "xicara": 10.0,
        "colher": 30.0,
    }
    _APP_FEATURE_RULES: tuple[_FeatureRedirectRule, ...] = (
        _FeatureRedirectRule(
            nome="contagem_calorias",
            handler="handler_guardrail_redirecionar_calorias",
            response=(
                "Para contar calorias ou macros, use a tela de calorias do app. "
                "Ela valida quantidade, unidade e alimento antes de calcular."
            ),
            acao_ui=ChatUIAction(
                action_id="open_calorie_counter",
                label="Abrir calorias",
                target="calorie_counter",
                payload={"feature": "contagem_calorias"},
            ),
            intencoes=("perguntar_calorias",),
        ),
        _FeatureRedirectRule(
            nome="cadastro_pratos",
            handler="handler_guardrail_redirecionar_cadastro_pratos",
            response=(
                "Para cadastrar prato ou refeicao, use o fluxo de cadastro do app. "
                "La voce consegue revisar os itens antes de salvar."
            ),
            acao_ui=ChatUIAction(
                action_id="open_saved_dishes",
                label="Abrir meus pratos",
                target="saved_dishes",
                payload={"feature": "cadastro_pratos"},
            ),
            intencoes=("cadastrar_pratos",),
        ),
        _FeatureRedirectRule(
            nome="registro_refeicao_foto",
            handler="handler_guardrail_redirecionar_refeicao_foto",
            response=(
                "Para registrar refeicao por foto, use a funcao de foto do prato no app. "
                "Esse fluxo aplica as validacoes corretas para a imagem."
            ),
            acao_ui=ChatUIAction(
                action_id="open_meal_photo",
                label="Abrir foto da refeicao",
                target="meal_photo",
                payload={"feature": "registro_refeicao_foto"},
            ),
            intencoes=("registrar_refeicao_foto",),
        ),
        _FeatureRedirectRule(
            nome="registro_refeicao_audio",
            handler="handler_guardrail_redirecionar_refeicao_audio",
            response=(
                "Para registrar refeicao por audio, use o fluxo de audio do app. "
                "La a transcricao e a confirmacao ficam guiadas."
            ),
            acao_ui=ChatUIAction(
                action_id="open_meal_audio",
                label="Abrir audio da refeicao",
                target="meal_audio",
                payload={"feature": "registro_refeicao_audio"},
            ),
            intencoes=("registrar_refeicao_audio",),
        ),
        _FeatureRedirectRule(
            nome="hidratacao",
            handler="handler_guardrail_redirecionar_hidratacao",
            response="Para adicionar ou remover agua, use a area de hidratacao do app.",
            acao_ui=ChatUIAction(
                action_id="open_hydration",
                label="Abrir agua",
                target="hydration",
                payload={"feature": "hidratacao"},
            ),
            termos=(
                "adicionar agua",
                "registrar agua",
                "lancar agua",
                "marcar agua",
                "remover agua",
                "retirar agua",
                "tirar agua",
                "desfazer agua",
                "editar agua",
                "ajustar agua",
            ),
        ),
        _FeatureRedirectRule(
            nome="senha",
            handler="handler_guardrail_redirecionar_senha",
            response="Para trocar ou recuperar senha, use a area de perfil e seguranca do app.",
            acao_ui=ChatUIAction(
                action_id="open_security_settings",
                label="Abrir seguranca",
                target="security_settings",
                payload={"feature": "senha"},
            ),
            termos=(
                "trocar senha",
                "alterar senha",
                "mudar senha",
                "redefinir senha",
                "resetar senha",
                "recuperar senha",
                "esqueci minha senha",
                "esqueci a senha",
                "forgot password",
            ),
        ),
    )

    def evaluate(
        self,
        *,
        prompt: str,
        intencao: IntencaoChatNome,
    ) -> ChatGuardrailDecision | None:
        texto_normalizado = _normalizar_texto(prompt)

        unsafe_term = self._find_unsafe_term(texto_normalizado)
        if unsafe_term is not None:
            return ChatGuardrailDecision(
                handler="handler_guardrail_bloqueio_conteudo",
                response=(
                    "Nao posso ajudar com termos sexualizados ou improprios nesse chat. "
                    "Se quiser, envie um alimento real e eu sigo com um tema de nutricao."
                ),
                tipo="bloqueio_conteudo",
                warnings=["Conteudo improprio bloqueado no chat."],
                metadados={
                    "guardrail_aplicado": True,
                    "guardrail_tipo": "bloqueio_conteudo",
                    "termo_bloqueado": unsafe_term,
                },
            )

        quantity_guardrail = self._build_quantity_guardrail(texto_normalizado=texto_normalizado, intencao=intencao)
        if quantity_guardrail is not None:
            return quantity_guardrail

        for rule in self._APP_FEATURE_RULES:
            if intencao in rule.intencoes or any(_contains_term(texto_normalizado, termo) for termo in rule.termos):
                return ChatGuardrailDecision(
                    handler=rule.handler,
                    response=rule.response,
                    tipo="redirecionamento_fluxo_app",
                    warnings=["Solicitacao redirecionada para um fluxo estruturado do app."],
                    acoes_ui=[rule.acao_ui.model_copy(deep=True)],
                    metadados={
                        "guardrail_aplicado": True,
                        "guardrail_tipo": "redirecionamento_fluxo_app",
                        "feature_alvo": rule.nome,
                    },
                )
        return None

    def _find_unsafe_term(self, texto_normalizado: str) -> str | None:
        for term in self._UNSAFE_TERMS:
            if _contains_term(texto_normalizado, term):
                return term
        return None

    def _build_quantity_guardrail(
        self,
        *,
        texto_normalizado: str,
        intencao: IntencaoChatNome,
    ) -> ChatGuardrailDecision | None:
        if intencao not in {"perguntar_calorias", "cadastrar_pratos"}:
            return None

        for match in self._QUANTITY_PATTERN.finditer(texto_normalizado):
            valor = _parse_decimal(match.group("valor"))
            unidade_bruta = match.group("unidade")
            unidade = _canonicalize_unit(unidade_bruta)
            limite = self._LIMITS_BY_UNIT.get(unidade)
            if limite is None or valor <= limite:
                continue

            response = (
                "Para esse tipo de lancamento, use a tela estruturada do app. "
                f"No chat eu nao processo quantidades fora da faixa validada, como {match.group(0)}."
            )
            if intencao == "perguntar_calorias":
                response = (
                    "Para contar calorias ou macros, use a tela de calorias do app. "
                    f"No chat eu nao processo quantidades fora da faixa validada, como {match.group(0)}."
                )

            return ChatGuardrailDecision(
                handler="handler_guardrail_quantidade_fora_da_faixa",
                response=response,
                tipo="quantidade_fora_da_faixa",
                warnings=["Quantidade fora da faixa permitida no chat."],
                acoes_ui=[
                    ChatUIAction(
                        action_id="open_calorie_counter",
                        label="Abrir calorias",
                        target="calorie_counter",
                        payload={"feature": "contagem_calorias", "motivo": "quantidade_fora_da_faixa"},
                    )
                ]
                if intencao == "perguntar_calorias"
                else [
                    ChatUIAction(
                        action_id="open_saved_dishes",
                        label="Abrir meus pratos",
                        target="saved_dishes",
                        payload={"feature": "cadastro_pratos", "motivo": "quantidade_fora_da_faixa"},
                    )
                ],
                metadados={
                    "guardrail_aplicado": True,
                    "guardrail_tipo": "quantidade_fora_da_faixa",
                    "quantidade_detectada": valor,
                    "unidade_detectada": unidade,
                    "limite_maximo": limite,
                    "trecho_detectado": match.group(0),
                },
            )
        return None


def _normalizar_texto(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.lower())
    ascii_like = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(ascii_like.split())


def _contains_term(texto_normalizado: str, termo: str) -> bool:
    pattern = rf"(?<!\w){re.escape(termo)}(?!\w)"
    return re.search(pattern, texto_normalizado) is not None


def _parse_decimal(value: str) -> float:
    return float(value.replace(",", "."))


def _canonicalize_unit(unit: str) -> str:
    if unit in {"kg", "quilo", "quilos"}:
        return "kg"
    if unit in {"g", "grama", "gramas"}:
        return "g"
    if unit in {"ml", "millilitro", "millilitros"}:
        return "ml"
    if unit in {"l", "litro", "litros"}:
        return "l"
    if unit in {"unidade", "unidades", "un"}:
        return "unidade"
    if unit in {"porcao", "porcoes"}:
        return "porcao"
    if unit in {"xicara", "xicaras"}:
        return "xicara"
    if unit in {"colher", "colheres"}:
        return "colher"
    return unit
