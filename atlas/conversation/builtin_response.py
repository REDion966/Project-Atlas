"""Atlas Built-In Conversational Response Service (Phase 1 + Phase 3).

Deterministic, model-independent conversational response path. It answers a
bounded set of conversational intents without calling any external AI
provider:

- greeting
- help
- identity / self-description
- capabilities (grounded in the injected ToolRegistry + CapabilityRegistry)
- capability-explain (a named registered capability/tool, or honest unknown)
- status (grounded in injected collaborators + caller-supplied counts)
- memory/knowledge recall (deterministic lookup; honest when unavailable)
- commands (supported CLI surfaces + safe next steps)
- unsupported-request notice (bounded, fail-closed)

Pure logic: no AI imports, no network, no storage/schema changes, no
RuntimeCoordinator changes. All collaborators are optional and injected;
when absent the service degrades gracefully instead of inventing content.
Every answer distinguishes confirmed state (what is registered/stored/
running) from unavailable or unknown state.

Boundary: this service only handles conversational turns whose classified
``TaskSpec`` is casual (CONVERSATION / UNKNOWN / QUESTION, and never a
needs-clarification spec). Governed lifecycle types (development,
investigation, planning, approval, execution, autonomy, orchestration
requests, ...) always return ``None`` so they continue through the existing
governed pipeline. Nothing here authorizes, executes, mutates, or approves.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from atlas.conversation.message import Message
from atlas.conversation.normalization import collapse_whitespace

if TYPE_CHECKING:
    from atlas.conversation.conversation_context import ConversationContext
    from atlas.conversation.task_intake import TaskSpec
    from atlas.knowledge.knowledge_manager import KnowledgeManager
    from atlas.memory.service.memory_manager_service import MemoryManagerService
    from atlas.reasoning.execution.registry import CapabilityRegistry
    from atlas.session.context import SessionContext
    from atlas.tools.registry import ToolRegistry

#: Intents this service answers. Anything else returns None (unsupported
#: inputs receive the bounded unsupported notice instead).
BUILTIN_INTENT_GREETING = "greeting"
BUILTIN_INTENT_HELP = "help"
BUILTIN_INTENT_IDENTITY = "identity"
BUILTIN_INTENT_CAPABILITIES = "capabilities"
BUILTIN_INTENT_CAPABILITY_DETAIL = "capability_detail"
BUILTIN_INTENT_STATUS = "status"
BUILTIN_INTENT_RECALL = "recall"
BUILTIN_INTENT_CONVERSATION_RECALL = "conversation_recall"
BUILTIN_INTENT_COMMANDS = "commands"
BUILTIN_INTENT_UNSUPPORTED = "unsupported"

#: Task types this service may answer. Every governed lifecycle type is
#: excluded so the existing pipeline keeps full authority over it.
_BUILTIN_TASK_TYPES: frozenset[str] = frozenset(
    {"conversation", "unknown", "question"}
)

_HELP_RE = re.compile(
    r"\bhelp\b|what can you do\b|how do i (use|talk to|chat with)\b"
    r"|\bcommands\b|\busage\b|^\s*help\s*[?!.\s]*$"
)

#: Bounded identity questions. The bare "what are you" alternative is
#: TERMINAL: an identity turn is the complete question ("what are you?",
#: optionally with an identity qualifier), never a prefix of a predicate
#: question. Without the anchor, "what are you good at" was claimed as
#: identity before any capability form could be recognised.
_IDENTITY_RE = re.compile(
    r"who are you\b|what is atlas\b|your name\b|introduce yourself\b"
    r"|about yourself\b|tell me about yourself\b"
    r"|what are you(?:\s+(?:exactly|really|precisely|then))?\s*[?!.]*\s*$"
)

_CAPABILITIES_RE = re.compile(
    r"\bcapabilit(y|ies)\b|\bcapable\b|list tools\b|tools do you have\b"
    r"|what (tools|features) (do|can) you\b|show .*tools\b"
)

#: "explain/describe/tell me about <name>" — the named capability detail
#: intent. Handled conservatively: the name must resolve against a
#: registered capability or tool, otherwise the standard unsupported
#: response is used. "tell me about yourself" stays identity (checked
#: by the identity pattern first).
_CAPABILITY_DETAIL_RE = re.compile(
    r"(?:explain|describe|what is|tell me about|how does|details? (?:on|about|for))\s+"
    r"(?P<name>[a-zA-Z0-9_][a-zA-Z0-9_.:\-/ ]{0,60})"
)

_STATUS_RE = re.compile(
    r"\bstatus\b|how are you\b|are you (ok|okay|online|working|up|running)\b"
    r"|system (status|health)\b|how is atlas\b"
)

#: Deterministic memory/knowledge recall. Conservative trigger phrases
#: only; the lookup itself is a verbatim keyword search over the injected
#: stores. Anything genuinely ambiguous falls through to unsupported.
_RECALL_RE = re.compile(
    r"\b(?:do you )?(?:remember|recall)\b|what do you (?:know|remember) about\b"
    r"|\b(?:can you\s+)?remind me\b"
    r"|\bwhat did we (?:discover|find|learn)(?: about)?\b"
    r"|search (?:your )?(?:memory|knowledge)(?: for)?\b"
    r"|look up .*?(?:in|from) (?:your )?(?:memory|knowledge)\b"
)

# ---------------------------------------------------------------------------
# Phase 5 — bounded conversational-turn recall.
#
# A capability DISTINCT from the ``_RECALL_RE`` memory/knowledge-store recall
# above. These patterns ask about the recent CONVERSATION itself; they are
# answered only from the bounded ConversationContext plus structured state,
# never from the memory/knowledge stores, and never by inventing content.
# ---------------------------------------------------------------------------

#: "What did I ask/say previously?" — previous user request.
_CONVERSATION_RECALL_USER_RE = re.compile(
    r"\bwhat did i (?:ask|ask you|say|request|mention)\b"
    r"|\bwhat was my (?:last|previous|earlier) (?:question|request|message|ask)\b"
    r"|\bremind me what i (?:asked|said)\b"
)

#: "What did you just tell me?" — previous Atlas response.
_CONVERSATION_RECALL_ASSISTANT_RE = re.compile(
    r"\bwhat did you (?:just )?(?:say|tell me)\b"
    r"|\bwhat was your (?:last|previous|earlier) (?:response|answer|message|reply)\b"
    r"|\bremind me what you (?:said|told me)\b"
)

#: "What were we discussing?" — recent conversation topic.
_CONVERSATION_RECALL_TOPIC_RE = re.compile(
    r"\bwhat (?:were|are) we (?:discussing|talking about|chatting about)\b"
    r"|\bwhat did we discuss\b"
    r"|\bwhat have we been (?:discussing|talking about)\b"
    r"|\bwhat was the recent (?:topic|subject)\b"
    r"|\bremind me what we (?:were discussing|discussed)\b"
)

#: "What did we find?" — recent governed finding/result.
_CONVERSATION_RECALL_FINDING_RE = re.compile(
    r"\bwhat did we (?:just )?find\b"
    r"|\bwhat (?:issue|problem|finding) did we (?:find|discuss)\b"
    r"|\bwhat was the (?:issue|problem) we (?:just )?discussed\b"
)

#: Bounded lead cues marking a prior user turn as a conversation subject.
_CONVERSATION_SUBJECT_LEAD_RE = re.compile(
    r"\b(?:investigate|investigation|analyze|analyse|diagnose|inspect"
    r"|examine|trace|debug)\b"
)

#: Provenance label per conversational-recall source.
_CONVERSATION_RECALL_LABELS: dict[str, str] = {
    "user": "You asked earlier:",
    "assistant": "I said:",
    "topic": "We were discussing:",
    "finding": "The most recent result:",
}

#: Bound applied to recalled turn content in the rendered answer.
_MAX_CONVERSATION_RECALL_CHARS: int = 400

#: Supported-command inquiry. Answered from the fixed, actually-existing
#: CLI command surfaces (never invented).
_COMMANDS_RE = re.compile(
    r"\bcommands?\b|what (?:can|should) i (?:type|say|ask|do)(?: next)?\b"
    r"|how do i (?:use|talk to|chat with|operate) (?:you|atlas)\b"
    r"|safe next steps?\b|what .*options? do i have\b"
)

#: Same greeting vocabulary as TaskIntake; greetings are the weakest match
#: and are only answered when no stronger intent matched.
_GREETING_RE = re.compile(
    r"\b(?:hello|hi|hey)\b|how are you|good morning|good afternoon"
    r"|good evening|nice to meet you"
)

# ---------------------------------------------------------------------------
# Bounded intent aliases (Phase 2).
#
# Explicit, readable phrase families for EXISTING conversational intents. Each
# alias is a bounded, word-boundary regex — never a fuzzy/substring match — so
# unrelated sentences are not captured. Aliases only select an existing
# intent; they never grant authority or execute anything.
# ---------------------------------------------------------------------------

#: Capability questions clearly equivalent to the canonical capability surface.
#: The "what can you <adverb> do" family deliberately requires the adverb so the
#: canonical "what can you do" help phrasing is left unchanged.
_CAPABILITY_ALIAS_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwhat can you (?:currently|actually|really|now|presently) do\b"),
    re.compile(r"\bwhat can you help(?: me)? with\b"),
    re.compile(r"\bwhat can atlas help(?: me)? with\b"),
    re.compile(r"\bwhat are you (?:able|capable)\b"),
    re.compile(r"\bwhat are you (?:good|best|better) at\b"),
    re.compile(
        r"\bwhat (?:are|is) your (?:current |present |existing |main )?"
        r"(?:abilities|capabilities|skills)\b"
    ),
    re.compile(
        r"\b(?:give me )?an? overview of your (?:current )?"
        r"(?:abilities|capabilities|skills)\b"
    ),
    re.compile(
        r"\btell me what you can (?:actually |really |currently |now )?do\b"
    ),
)

#: Narrow identity phrasings equivalent to the canonical identity surface.
_IDENTITY_ALIAS_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwhat (?:exactly )?is atlas\b"),
)

#: Status phrasings equivalent to the canonical status surface.
_STATUS_ALIAS_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bhow are things (?:looking|going)\b"),
    re.compile(
        r"\bwhat(?:'s| is) (?:going on|happening) with (?:your|the) system\b"
    ),
)


def _alias_hit(
    patterns: tuple[re.Pattern[str], ...],
    text: str,
) -> bool:
    """True when ``text`` matches one of the bounded alias patterns."""
    return any(pattern.search(text) for pattern in patterns)

_MAX_TOOLS_LISTED = 20


class BuiltinResponseService:
    """Deterministic built-in conversational responder.

    Answers the bounded intent set from injected Atlas state only. Never
    calls a model, never invents capabilities, never mutates anything.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        knowledge_manager: KnowledgeManager | None = None,
        capability_registry: CapabilityRegistry | None = None,
        memory_service: MemoryManagerService | None = None,
        service_names: (
            list[str]
            | tuple[str, ...]
            | Callable[[], list[str] | tuple[str, ...]]
            | None
        ) = None,
        started: bool | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._knowledge_manager = knowledge_manager
        self._capability_registry = capability_registry
        self._memory_service = memory_service
        self._service_names = service_names
        self._started = started

    def _resolve_service_names(self) -> tuple[str, ...] | None:
        """Resolve the container/service snapshot for the status answer.

        A sequence is used as the eager snapshot it has always been; a lazy
        zero-argument provider is resolved on demand, so a kernel that
        registers services after construction is still observed accurately.
        """
        names = self._service_names
        if callable(names):
            try:
                names = names()
            except Exception:
                return None
        if names is None:
            return None
        return tuple(sorted(names))

    @property
    def tool_registry(self) -> ToolRegistry | None:
        return self._tool_registry

    @property
    def knowledge_manager(self) -> KnowledgeManager | None:
        return self._knowledge_manager

    @property
    def capability_registry(self) -> CapabilityRegistry | None:
        return self._capability_registry

    @property
    def memory_service(self) -> MemoryManagerService | None:
        return self._memory_service

    def handles(
        self,
        text: str,
        spec: TaskSpec | None = None,
    ) -> bool:
        """True when this service should answer ``text`` deterministically."""
        return self._classify(text, spec) is not None

    def respond(
        self,
        text: str,
        spec: TaskSpec | None = None,
        session_context: SessionContext | None = None,
        message_count: int | None = None,
        context: ConversationContext | None = None,
    ) -> Message | None:
        """Build a deterministic assistant Message, or None to continue.

        Returns None when the turn belongs to the governed pipeline (typed
        lifecycle request, needs-clarification spec), so ``send``/``stream``
        fall through to the existing handling unchanged.

        ``context`` is the bounded, read-only :class:`ConversationContext`
        projection of recent conversation history/state. Phase 3 only
        *accepts* it: the deterministic responses are unchanged, and the value
        is never mutated, executed, or used to authorize anything.
        """
        classified = self._classify(text, spec, context)
        if classified is None:
            return None
        if isinstance(classified, tuple):
            intent, detail = classified
        else:
            intent, detail = classified, None
        content = self._render(intent, message_count=message_count, detail=detail)
        metadata: dict[str, Any] = {
            "builtin_response": True,
            "builtin_intent": intent,
            "model_used": False,
        }
        if intent == BUILTIN_INTENT_CONVERSATION_RECALL and isinstance(detail, tuple):
            metadata["recall_source"] = detail[0]
        return Message(
            role="assistant",
            content=content,
            metadata=metadata,
        )

    def respond_stream(
        self,
        text: str,
        spec: TaskSpec | None = None,
        session_context: SessionContext | None = None,
        message_count: int | None = None,
        context: ConversationContext | None = None,
    ) -> Iterator[str]:
        """Yield the deterministic response content as a single chunk."""
        msg = self.respond(
            text,
            spec=spec,
            session_context=session_context,
            message_count=message_count,
            context=context,
        )
        if msg is None:
            return
        yield msg.content

    def _classify(
        self,
        text: str,
        spec: TaskSpec | None,
        context: ConversationContext | None = None,
    ) -> str | tuple[str, object] | None:
        """Classify a turn into a builtin intent.

        Returns an intent name, an ``(intent, detail)`` tuple for intents
        that carry a resolved argument (capability detail, store recall query,
        conversational-turn recall), or ``None`` when the turn belongs
        elsewhere. Conservative by design: anything that does not match a
        bounded trigger with a resolvable argument becomes the honest
        unsupported response.

        ``context`` is the bounded, read-only :class:`ConversationContext`; it
        is consulted only for conversational-turn recall (Phase 5).
        """
        lowered = collapse_whitespace(text).lower()
        if not lowered:
            return BUILTIN_INTENT_UNSUPPORTED
        if spec is not None:
            task_type = getattr(spec.task_type, "value", "") or ""
            if task_type not in _BUILTIN_TASK_TYPES:
                return None
            if bool(getattr(spec, "needs_clarification", False)):
                return None
        if _COMMANDS_RE.search(lowered):
            return BUILTIN_INTENT_COMMANDS
        # Bounded capability aliases precede help/identity: genuinely
        # equivalent capability questions must not be captured by the help
        # word ("... help me with") or by the identity predicate's
        # "what are you" ("what are you capable of").
        if _CAPABILITIES_RE.search(lowered) or _alias_hit(
            _CAPABILITY_ALIAS_RES, lowered
        ):
            return BUILTIN_INTENT_CAPABILITIES
        if _HELP_RE.search(lowered):
            return BUILTIN_INTENT_HELP
        if _IDENTITY_RE.search(lowered) or _alias_hit(
            _IDENTITY_ALIAS_RES, lowered
        ):
            return BUILTIN_INTENT_IDENTITY
        detail = self._match_capability_detail(lowered)
        if detail is not None:
            return (BUILTIN_INTENT_CAPABILITY_DETAIL, detail)
        if _STATUS_RE.search(lowered) or _alias_hit(
            _STATUS_ALIAS_RES, lowered
        ):
            return BUILTIN_INTENT_STATUS
        # Conversational-turn recall (Phase 5) precedes store recall: it claims
        # only phrases about the recent conversation, and only when a
        # deterministic candidate exists (otherwise it falls through to the
        # unchanged store/memory recall path).
        conversation_recall = self._match_conversation_recall(lowered, context)
        if conversation_recall is not None:
            return (BUILTIN_INTENT_CONVERSATION_RECALL, conversation_recall)
        recall_query = self._match_recall(lowered)
        if recall_query is not None:
            return (BUILTIN_INTENT_RECALL, recall_query)
        if _GREETING_RE.search(lowered):
            return BUILTIN_INTENT_GREETING
        task_type = (
            getattr(spec.task_type, "value", "") if spec is not None else ""
        )
        if task_type in ("", "conversation", "unknown", "question"):
            return BUILTIN_INTENT_UNSUPPORTED
        return None

    def _match_capability_detail(self, lowered: str) -> str | None:
        """Resolve a named-capability reference, or None when unknown.

        Conservative: the candidate name must resolve — case-insensitively,
        allowing ``.``/``_``/``-``/space variants — to a registered
        capability handler or tool. Anything else is not a confident
        match, so the caller falls through to the unsupported response.
        """
        match = _CAPABILITY_DETAIL_RE.search(lowered)
        if match is None:
            return None
        candidate = match.group("name").strip().strip("?.!.,;:'\"()")
        if not candidate:
            return None
        normalized = candidate.lower().replace("-", "_").replace(" ", "_")
        candidates = {normalized}
        if "." not in normalized and "_" not in normalized:
            candidates.add(normalized)
        for name in self._capability_names() | self._tool_names():
            folded = name.lower().replace("-", "_").replace(" ", "_")
            if folded in candidates or normalized in (
                folded,
                folded.replace(".", "_"),
                folded.replace("_", "."),
            ):
                return name
        return None

    def _match_recall(self, lowered: str) -> str | None:
        """Extract a recall query, or None when no confident trigger exists.

        Requires one of the conservative trigger phrases AND a non-trivial
        query remainder (>= 3 alphanumeric characters). A bare "do you
        remember?" with nothing to look up is not a confident recall — it
        falls through to unsupported.
        """
        match = _RECALL_RE.search(lowered)
        if match is None:
            return None
        remainder = _RECALL_RE.sub(" ", lowered)
        remainder = re.sub(r"[^a-z0-9_ ]", " ", remainder)
        tokens = [t for t in remainder.split() if len(t) >= 3]
        if not tokens:
            return None
        return " ".join(tokens[:8])

    def _match_conversation_recall(
        self,
        lowered: str,
        context: ConversationContext | None,
    ) -> tuple[str, str, str] | None:
        """Return ``(source, label, content)`` for a bounded turn recall.

        Consumes only the immutable :class:`ConversationContext` and its
        structured state. Returns ``None`` when the phrase is not a
        conversational-turn recall request, or when no deterministic candidate
        exists — fail closed; the unchanged store recall path then applies.
        """
        if context is None:
            return None

        state = getattr(context, "state", None)
        prior_user = self._prior_turns(context, "user", lowered)
        prior_assistant = self._prior_turns(context, "assistant", lowered)

        if _CONVERSATION_RECALL_USER_RE.search(lowered):
            if prior_user:
                return ("user", _CONVERSATION_RECALL_LABELS["user"], prior_user[-1])
            return None

        if _CONVERSATION_RECALL_ASSISTANT_RE.search(lowered):
            if prior_assistant:
                return (
                    "assistant",
                    _CONVERSATION_RECALL_LABELS["assistant"],
                    prior_assistant[-1],
                )
            return None

        if _CONVERSATION_RECALL_TOPIC_RE.search(lowered):
            subject = self._recent_conversation_subject(prior_user, state)
            if subject:
                return ("topic", _CONVERSATION_RECALL_LABELS["topic"], subject)
            return None

        if _CONVERSATION_RECALL_FINDING_RE.search(lowered):
            if state is not None:
                finding = getattr(state, "latest_result", None)
                if isinstance(finding, str) and finding.strip():
                    return (
                        "finding",
                        _CONVERSATION_RECALL_LABELS["finding"],
                        finding.strip(),
                    )
            return None

        return None

    @staticmethod
    def _prior_turns(
        context: ConversationContext,
        role: str,
        lowered: str,
    ) -> list[str]:
        """Return bounded prior turns of ``role``, excluding the current turn."""
        query_key = " ".join(lowered.split())
        turns: list[str] = []
        for turn in getattr(context, "recent_turns", ()) or ():
            if getattr(turn, "role", "") != role:
                continue
            content = getattr(turn, "content", "")
            if not isinstance(content, str) or not content.strip():
                continue
            # Exclude the current turn (its text matches the live query).
            if " ".join(content.split()).lower() == query_key:
                continue
            turns.append(content.strip())
        return turns

    @staticmethod
    def _recent_conversation_subject(prior_user: list[str], state: Any) -> str:
        """Return the deterministic recent conversation subject, or ''."""
        if state is not None:
            investigation = getattr(state, "current_investigation", None)
            if isinstance(investigation, str) and investigation.strip():
                return investigation.strip()
        for content in reversed(prior_user):
            if _CONVERSATION_SUBJECT_LEAD_RE.search(content.lower()):
                return content
        # L5 — bounded last-resort fallback: the subject established explicitly
        # in an earlier turn. Investigation subjects and lead-cue turns keep
        # precedence, so existing recall behaviour is unchanged.
        if state is not None:
            established = getattr(state, "current_subject", None)
            if isinstance(established, str) and established.strip():
                return established.strip()
        return ""

    @staticmethod
    def _render_conversation_recall(detail: tuple[str, str, str]) -> str:
        """Render a bounded, provenance-labelled conversational recall."""
        _source, label, content = detail
        body = content.strip()
        if len(body) > _MAX_CONVERSATION_RECALL_CHARS:
            body = body[:_MAX_CONVERSATION_RECALL_CHARS].rstrip() + "..."
        return f"{label} {body}"

    def _render(
        self,
        intent: str,
        message_count: int | None = None,
        detail: object | None = None,
    ) -> str:
        if intent == BUILTIN_INTENT_GREETING:
            return self._render_greeting()
        if intent == BUILTIN_INTENT_HELP:
            return self._render_help()
        if intent == BUILTIN_INTENT_IDENTITY:
            return self._render_identity()
        if intent == BUILTIN_INTENT_CAPABILITIES:
            return self._render_capabilities()
        if intent == BUILTIN_INTENT_CAPABILITY_DETAIL:
            return self._render_capability_detail(detail or "")
        if intent == BUILTIN_INTENT_STATUS:
            return self._render_status(message_count=message_count)
        if intent == BUILTIN_INTENT_RECALL:
            return self._render_recall(detail or "")
        if intent == BUILTIN_INTENT_CONVERSATION_RECALL and isinstance(detail, tuple):
            return self._render_conversation_recall(detail)
        if intent == BUILTIN_INTENT_COMMANDS:
            return self._render_commands()
        return self._render_unsupported()

    @staticmethod
    def _render_greeting() -> str:
        return (
            "Hello. I am Atlas, a model-independent operating framework. "
            "I answer deterministically without calling an external AI model. "
            "Ask 'help' to see what I can do."
        )

    @staticmethod
    def _render_help() -> str:
        return (
            "I can help deterministically (no external AI model needed):\n"
            "- Greet me ('hello').\n"
            "- Ask who I am ('who are you').\n"
            "- Ask what I can do ('what capabilities do you have').\n"
            "- Ask about one capability ('explain code_inspector').\n"
            "- Ask for status ('status').\n"
            "- Ask what I remember ('do you remember <topic>').\n"
            "- Ask for commands ('what commands can I use').\n"
            "- Ask me to investigate an issue ('investigate ...').\n"
            "- Ask me to prepare a development proposal ('plan ...' after an "
            "investigation). Proposals always require your explicit approval; "
            "approval never executes anything by itself."
        )

    @staticmethod
    def _render_identity() -> str:
        return (
            "I am Atlas, a long-term, modular AI operating framework — not a "
            "chatbot and not a model wrapper. I coordinate memory, knowledge, "
            "reasoning, planning, learning, tools, and evolution under human "
            "ownership. AI models are tools I may use; they are not my "
            "intelligence. I operate deterministically, fail closed, and "
            "never modify anything without governed approval."
        )

    def _capability_names(self) -> set[str]:
        if self._capability_registry is None:
            return set()
        try:
            return set(self._capability_registry.registered_names)
        except Exception:
            return set()

    def _tool_names(self) -> set[str]:
        return {getattr(t, "name", "") for t in self._listed_tools()}

    def _find_tool(self, name: str) -> Any | None:
        if self._tool_registry is None:
            return None
        try:
            return self._tool_registry.get(name)
        except Exception:
            return None

    def _render_capabilities(self) -> str:
        tools = self._listed_tools()
        capabilities = sorted(self._capability_names())
        if not tools and not capabilities:
            return (
                "No tools or capabilities are currently registered. "
                "Deterministic conversational intents I always support: "
                "greeting, help, identity, status, commands. Governed flows "
                "(investigation, planning, approval, execution) are handled "
                "by the conversation pipeline when wired."
            )
        lines = [
            "Confirmed registered capabilities (deterministic, no model used):",
            "",
        ]
        if capabilities:
            lines.append("Reasoning capabilities:")
            for name in capabilities[:_MAX_TOOLS_LISTED]:
                lines.append(f"- `{name}`")
            extra = len(capabilities) - _MAX_TOOLS_LISTED
            if extra > 0:
                lines.append(f"  ... and {extra} more registered capabilit(ies).")
            lines.append("")
        if tools:
            lines.append("Tools:")
            for tool in tools[:_MAX_TOOLS_LISTED]:
                name = getattr(tool, "name", "?")
                category = getattr(tool, "category", "?")
                desc = getattr(tool, "description", "") or "No description."
                lines.append(f"- **{name}** ({category}): {desc}")
            extra = len(tools) - _MAX_TOOLS_LISTED
            if extra > 0:
                lines.append(f"... and {extra} more registered tool(s).")
        lines.append("")
        lines.append(
            "Ask 'explain <name>' for a registered capability or tool."
        )
        return "\n".join(lines)

    def _render_capability_detail(self, name: str) -> str:
        tool = self._find_tool(name)
        if tool is not None:
            desc = getattr(tool, "description", "") or "No description."
            category = getattr(tool, "category", "?")
            tags = getattr(tool, "tags", ()) or ()
            lines = [
                f"**{name}** (tool, category `{category}`):",
                desc,
            ]
            if tags:
                lines.append(f"Tags: {', '.join(tags)}.")
            lines.append(
                "This is a confirmed registration — the tool exists in the "
                "tool registry. Running it is a governed step, not something "
                "I do from conversation alone."
            )
            return "\n".join(lines)
        if name in self._capability_names():
            return (
                f"`{name}` is a confirmed registered reasoning capability "
                "(capability registry). It is invoked only through the "
                "governed capability path (registry → router → dispatcher), "
                "never directly from conversation."
            )
        return self._render_unsupported()

    def _listed_tools(self) -> list[Any]:
        if self._tool_registry is None:
            return []
        try:
            return list(self._tool_registry.list())
        except Exception:
            return []

    def _render_status(self, message_count: int | None = None) -> str:
        tool_count: int | None = None
        if self._tool_registry is not None:
            try:
                tool_count = len(self._tool_registry.list())
            except Exception:
                tool_count = None
        knowledge_count: int | None = None
        if self._knowledge_manager is not None:
            try:
                base = getattr(self._knowledge_manager, "base", None)
                entries = base.all() if base is not None else None
                knowledge_count = len(entries) if entries is not None else None
            except Exception:
                knowledge_count = None
        lines = [
            "Atlas status (deterministic, no external model contacted):",
            "- Mode: built-in deterministic responses.",
        ]
        lines.append(
            f"- Registered tools: {tool_count}."
            if tool_count is not None
            else "- Registered tools: unknown (no tool registry wired)."
        )
        lines.append(
            f"- Knowledge entries: {knowledge_count}."
            if knowledge_count is not None
            else "- Knowledge entries: unknown (no knowledge manager wired)."
        )
        memory_count: int | None = None
        if self._memory_service is not None:
            try:
                memory_count = len(self._memory_service.list_memories())
            except Exception:
                memory_count = None
        lines.append(
            f"- Stored memories: {memory_count}."
            if memory_count is not None
            else "- Stored memories: unknown (no memory service wired)."
        )
        service_names = self._resolve_service_names()
        if service_names is not None:
            lines.append(
                f"- Registered services ({len(service_names)}): "
                + ", ".join(f"`{n}`" for n in service_names[:24])
                + ("" if len(service_names) <= 24 else ", ...")
            )
        else:
            lines.append("- Registered services: unknown (no container snapshot).")
        if self._started is True:
            lines.append("- Runtime: started.")
        elif self._started is False:
            lines.append("- Runtime: not started (limited surface).")
        else:
            lines.append("- Runtime: unknown (no lifecycle snapshot).")
        if message_count is not None:
            lines.append(f"- Messages in this conversation: {message_count}.")
        return "\n".join(lines)

    def _render_recall(self, query: str) -> str:
        memories = self._search_memories(query)
        entries = self._search_knowledge(query)
        if not memories and not entries:
            sources: list[str] = []
            if self._memory_service is None:
                sources.append("memory service is not wired")
            if self._knowledge_manager is None:
                sources.append("knowledge manager is not wired")
            if sources:
                return (
                    f"No deterministic recall available ({' and '.join(sources)}). "
                    "I cannot invent an answer, so I will not guess."
                )
            return (
                f"No memory or knowledge entry matched '{query}'. "
                "Stored entries are searched verbatim (case-insensitive "
                "keyword match); try different words, or ask 'help' for "
                "what I can do."
            )
        lines = [
            f"Deterministic recall for '{query}' (verbatim keyword match, "
            "no model used):",
            "",
        ]
        for memory in memories[:3]:
            title = getattr(memory, "title", "Memory")
            content = getattr(memory, "content", "")
            source = getattr(memory, "source", "unknown")
            lines.append(f"### Memory: {title}")
            lines.append(str(content)[:500])
            lines.append(f"- Source: {source}")
            lines.append("")
        for entry in entries[:3]:
            title = getattr(entry, "title", "Knowledge")
            content = getattr(entry, "content", "")
            source = getattr(entry, "source", "unknown")
            lines.append(f"### Knowledge: {title}")
            lines.append(str(content)[:500])
            lines.append(f"- Source: {source}")
            lines.append("")
        return "\n".join(lines).strip()

    def _search_memories(self, query: str) -> list[Any]:
        if self._memory_service is None or not query:
            return []
        try:
            results = self._memory_service.search(keyword=query, limit=3)
        except Exception:
            return []
        return list(results or [])

    def _search_knowledge(self, query: str) -> list[Any]:
        if self._knowledge_manager is None or not query:
            return []
        try:
            results = self._knowledge_manager.query(query)
        except Exception:
            return []
        return list(results or [])[:3]

    def _render_commands(self) -> str:
        return (
            "Supported commands and safe next steps (deterministic surfaces only):\n"
            "- Conversational: 'hello', 'help', 'who are you', "
            "'what can you do', 'status', 'explain <capability>', "
            "'do you remember <topic>'.\n"
            "- CLI subcommands (read-only unless noted): `atlas capabilities`, "
            "`atlas validated-knowledge <query>`, `atlas memory search <query>`, "
            "`atlas reasoning trace|causal|hypotheses|verify|meta`, "
            "`atlas toolchain plan|execute`, `atlas research query|verify`, "
            "`atlas proposals list|show|audit`, `atlas evolution pending|show|status`.\n"
            "- Governed development: 'investigate <issue>' produces a read-only "
            "report; 'plan ...' prepares a proposal that requires your explicit "
            "approval; approval never executes; execution needs a separate "
            "explicit step. Nothing here modifies the repository."
        )

    @staticmethod
    def _render_unsupported() -> str:
        return (
            "I operate deterministically without an external AI model, so I "
            "cannot answer that conversationally yet. I do support: greeting, "
            "help, identity ('who are you'), capabilities ('what can you do'), "
            "capability detail ('explain <name>'), status, memory/knowledge "
            "recall ('do you remember <topic>'), and commands ('what commands "
            "can I use'). I can also investigate an issue ('investigate ...') "
            "or prepare a governed development proposal after an "
            "investigation — both require your explicit approval steps."
        )
