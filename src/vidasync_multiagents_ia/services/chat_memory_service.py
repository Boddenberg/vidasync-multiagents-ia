import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.schemas import ChatMemoriaEstado, ChatPipelineNome, IntencaoChatNome


@dataclass(slots=True)
class ChatMemoryBuildResult:
    context_text: str
    estado: ChatMemoriaEstado


@dataclass(slots=True)
class _MemoryTurn:
    role: str
    content: str
    created_at: datetime


@dataclass(slots=True)
class _ConversationMemory:
    conversation_id: str
    created_at: datetime
    updated_at: datetime
    summary: str = ""
    summarized_turns: int = 0
    turns: list[_MemoryTurn] = field(default_factory=list)
    total_turns: int = 0
    last_intent: IntencaoChatNome | None = None
    last_pipeline: ChatPipelineNome | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class ChatMemoryService:
    """
    /****
     * Gerencia memoria conversacional controlada em memoria:
     * - curto prazo: ultimos turnos (janela deslizante)
     * - longo prazo leve: resumo acumulado dos turnos antigos
     * - metadados: dados de conversa para rastreabilidade
     *
     * Observacao de manutencao:
     * Esta versao e in-memory e nao persiste entre reinicios.
     * Para producao horizontal, trocar storage mantendo o mesmo contrato.
     ****/
    """

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings
        self._conversations: dict[str, _ConversationMemory] = {}
        self._lock = Lock()
        self._logger = logging.getLogger(__name__)

    def build_context(
        self,
        *,
        conversation_id: str,
        metadados_conversa: dict[str, Any] | None = None,
    ) -> ChatMemoryBuildResult:
        if not self._settings.chat_memory_enabled:
            return ChatMemoryBuildResult(
                context_text="",
                estado=self._to_estado(
                    convo=_ConversationMemory(
                        conversation_id=conversation_id,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    ),
                    context_chars=0,
                    limit_applied=False,
                ),
            )

        with self._lock:
            convo = self._get_or_create(conversation_id=conversation_id)
            self._merge_metadata(convo=convo, input_metadata=metadados_conversa or {})
            context_text, limit_applied = self._build_context_text(convo=convo)
            estado = self._to_estado(
                convo=convo,
                context_chars=len(context_text),
                limit_applied=limit_applied,
            )
            return ChatMemoryBuildResult(context_text=context_text, estado=estado)

    def append_exchange(
        self,
        *,
        conversation_id: str,
        user_prompt: str,
        assistant_response: str,
        intencao: IntencaoChatNome,
        pipeline: ChatPipelineNome,
        metadados_conversa: dict[str, Any] | None = None,
    ) -> ChatMemoriaEstado:
        if not self._settings.chat_memory_enabled:
            return self.build_context(conversation_id=conversation_id).estado

        now = datetime.now(timezone.utc)
        with self._lock:
            convo = self._get_or_create(conversation_id=conversation_id)
            self._merge_metadata(convo=convo, input_metadata=metadados_conversa or {})
            user_text = _normalize_message(user_prompt)
            assistant_text = _normalize_message(assistant_response)
            if user_text:
                convo.turns.append(_MemoryTurn(role="user", content=user_text, created_at=now))
                convo.total_turns += 1
            if assistant_text:
                convo.turns.append(_MemoryTurn(role="assistant", content=assistant_text, created_at=now))
                convo.total_turns += 1

            convo.last_intent = intencao
            convo.last_pipeline = pipeline
            convo.updated_at = now

            compacted = self._compact_short_term(convo=convo)
            context_text, context_limited = self._build_context_text(convo=convo)
            estado = self._to_estado(
                convo=convo,
                context_chars=len(context_text),
                limit_applied=compacted or context_limited,
            )
            self._logger.info(
                "chat_memory.updated",
                extra={
                    "conversation_id": conversation_id,
                    "total_turns": estado.total_turnos,
                    "short_term_turns": estado.turnos_curto_prazo,
                    "summarized_turns": estado.turnos_resumidos,
                    "context_chars": estado.contexto_chars,
                    "limit_applied": estado.limite_aplicado,
                    "last_intent": estado.ultima_intencao,
                    "last_pipeline": estado.ultimo_pipeline,
                },
            )
            return estado

    def _get_or_create(self, *, conversation_id: str) -> _ConversationMemory:
        convo = self._conversations.get(conversation_id)
        if convo is not None:
            return convo
        now = datetime.now(timezone.utc)
        convo = _ConversationMemory(
            conversation_id=conversation_id,
            created_at=now,
            updated_at=now,
        )
        self._conversations[conversation_id] = convo
        return convo

    def _merge_metadata(self, *, convo: _ConversationMemory, input_metadata: dict[str, Any]) -> None:
        for key, value in input_metadata.items():
            key_norm = str(key).strip()
            if not key_norm:
                continue
            value_norm = str(value).strip()
            if not value_norm:
                continue
            convo.metadata[key_norm[:64]] = value_norm[:120]

    def _compact_short_term(self, *, convo: _ConversationMemory) -> bool:
        max_turns = max(2, self._settings.chat_memory_max_turns_short_term)
        if len(convo.turns) <= max_turns:
            return False

        overflow = len(convo.turns) - max_turns
        moved = convo.turns[:overflow]
        convo.turns = convo.turns[overflow:]
        convo.summarized_turns += len(moved)
        convo.summary = _merge_summary(
            current_summary=convo.summary,
            moved_turns=moved,
            max_chars=max(200, self._settings.chat_memory_summary_max_chars),
            max_turn_chars=max(60, self._settings.chat_memory_max_turn_chars),
        )
        return True

    def _build_context_text(self, *, convo: _ConversationMemory) -> tuple[str, bool]:
        max_chars = max(80, self._settings.chat_memory_context_max_chars)
        turn_chars = max(60, self._settings.chat_memory_max_turn_chars)
        lines: list[str] = []
        consumed = 0
        limit_applied = False

        if convo.summary:
            summary_header = "Resumo acumulado da conversa:"
            summary_body = convo.summary.strip()
            summary_block = f"{summary_header}\n{summary_body}"
            if len(summary_block) > max_chars:
                summary_block = summary_block[: max_chars - 3].rstrip() + "..."
                limit_applied = True
            lines.append(summary_block)
            consumed += len(summary_block)

        recent_lines: list[str] = []
        for turn in reversed(convo.turns):
            role = "Usuario" if turn.role == "user" else "Assistente"
            content = _clip(turn.content, turn_chars)
            line = f"{role}: {content}"
            projected = consumed + len("\n".join(recent_lines + [line]))
            if projected > max_chars:
                limit_applied = True
                break
            recent_lines.append(line)

        if recent_lines:
            recent_lines.reverse()
            if lines:
                lines.append("Historico recente:")
            else:
                lines.append("Historico recente:")
            lines.extend(recent_lines)

        context_text = "\n".join(lines).strip()
        if len(context_text) > max_chars:
            context_text = context_text[: max_chars - 3].rstrip() + "..."
            limit_applied = True
        return context_text, limit_applied

    def _to_estado(
        self,
        *,
        convo: _ConversationMemory,
        context_chars: int,
        limit_applied: bool,
    ) -> ChatMemoriaEstado:
        return ChatMemoriaEstado(
            conversation_id=convo.conversation_id,
            total_turnos=convo.total_turns,
            turnos_curto_prazo=len(convo.turns),
            turnos_resumidos=convo.summarized_turns,
            resumo_presente=bool(convo.summary),
            contexto_chars=context_chars,
            limite_aplicado=limit_applied,
            ultima_intencao=convo.last_intent,
            ultimo_pipeline=convo.last_pipeline,
            metadados=dict(convo.metadata),
            atualizada_em=convo.updated_at,
        )


def _normalize_message(value: str) -> str:
    cleaned = " ".join(value.split())
    return cleaned.strip()


def _clip(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _merge_summary(
    *,
    current_summary: str,
    moved_turns: list[_MemoryTurn],
    max_chars: int,
    max_turn_chars: int,
) -> str:
    lines: list[str] = []
    if current_summary.strip():
        lines.append(current_summary.strip())
    for turn in moved_turns:
        role = "U" if turn.role == "user" else "A"
        lines.append(f"{role}: {_clip(turn.content, max_turn_chars)}")
    merged = " | ".join(line for line in lines if line).strip()
    if len(merged) <= max_chars:
        return merged
    suffix = merged[-(max_chars - 3) :].lstrip()
    return f"...{suffix}"


def compose_prompt_with_memory(*, prompt_atual: str, memoria_contexto: str) -> str:
    if not memoria_contexto.strip():
        return prompt_atual
    return (
        "Contexto util da conversa:\n"
        f"{memoria_contexto.strip()}\n\n"
        "Mensagem atual do usuario:\n"
        f"{prompt_atual.strip()}"
    )
