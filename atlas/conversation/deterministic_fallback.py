"""Atlas Deterministic Fallback Resolver (Phase 6.1 — Model Independence).

Pure, deterministic fallback resolver that provides useful responses when
external AI model inference is unavailable, unconfigured, unreachable, or fails.

Reuses existing deterministic Atlas facilities:
- KnowledgeManager: deterministic keyword search & ranking over local knowledge base
- ToolRegistry: deterministic listing & discovery of registered tools/capabilities

Fail-closed, pure logic: no AI imports, no network, no storage/schema changes,
no runtime coordinator changes.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from atlas.conversation.message import Message

if TYPE_CHECKING:
    from atlas.conversation.task_intake import TaskSpec
    from atlas.knowledge.knowledge_manager import KnowledgeManager
    from atlas.session.context import SessionContext
    from atlas.tools.registry import ToolRegistry

_TOOL_QUERY_KEYWORDS: frozenset[str] = frozenset(
    {"tool", "tools", "capability", "capabilities", "what can you do", "commands", "help", "list tools"}
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "tell", "me", "about", "what", "is", "the", "a", "an", "can", "you",
        "how", "why", "where", "who", "which", "do", "does", "did", "please",
        "explain", "give", "show", "find", "for", "to", "in", "on", "at", "of",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


class DeterministicFallbackResolver:
    """Deterministic-only fallback resolver for model-degraded operation.

    All collaborators are optional and injected. When collaborators are absent,
    degrades gracefully to a clean, bounded status message.
    """

    def __init__(
        self,
        knowledge_manager: KnowledgeManager | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._knowledge_manager = knowledge_manager
        self._tool_registry = tool_registry

    @property
    def knowledge_manager(self) -> KnowledgeManager | None:
        return self._knowledge_manager

    @property
    def tool_registry(self) -> ToolRegistry | None:
        return self._tool_registry

    def resolve(
        self,
        text: str,
        spec: TaskSpec | None = None,
        session_context: SessionContext | None = None,
        error_context: str | None = None,
    ) -> Message:
        """Deterministically resolve a user request when the model is unavailable.

        1. If text queries stored knowledge and entries match, formats the knowledge result.
        2. If text queries available tools/capabilities, formats the tool registry summary.
        3. Otherwise, returns a bounded model-degraded fallback notice.
        """
        content, fallback_type = self._generate_response_content(text, spec, error_context)
        return Message(
            role="assistant",
            content=content,
            metadata={
                "degraded": True,
                "model_available": False,
                "fallback_source": "deterministic",
                "fallback_type": fallback_type,
                "error_context": error_context,
            },
        )

    def resolve_stream(
        self,
        text: str,
        spec: TaskSpec | None = None,
        session_context: SessionContext | None = None,
        error_context: str | None = None,
    ) -> Iterator[str]:
        """Yield deterministic fallback response content as a stream."""
        msg = self.resolve(text, spec, session_context, error_context)
        yield msg.content

    def _generate_response_content(
        self,
        text: str,
        spec: TaskSpec | None,
        error_context: str | None = None,
    ) -> tuple[str, str]:
        clean_text = (text or "").strip()
        lowered = clean_text.lower()

        # 1. Check for tool/capability queries
        is_tool_query = any(keyword in lowered for keyword in _TOOL_QUERY_KEYWORDS)
        if is_tool_query and self._tool_registry is not None:
            tool_msg = self._format_tool_guidance(lowered)
            if tool_msg is not None:
                return tool_msg, "tool_guidance"

        # 2. Check for matching knowledge in KnowledgeManager
        if self._knowledge_manager is not None and clean_text:
            entries = self._search_knowledge(clean_text, spec)
            if entries:
                return self._format_knowledge_response(entries), "knowledge"

        # 3. If it was a tool query but specific matches were not found, format full tool catalog
        if is_tool_query and self._tool_registry is not None:
            tool_msg = self._format_tool_guidance(lowered, show_all=True)
            if tool_msg is not None:
                return tool_msg, "tool_guidance"

        # 4. General bounded degradation notice
        return self._format_degraded_notice(clean_text, error_context), "degraded_notice"

    def _search_knowledge(self, text: str, spec: TaskSpec | None) -> list[Any]:
        """Multi-strategy search over KnowledgeManager."""
        if self._knowledge_manager is None:
            return []

        seen: set[tuple[str, str]] = set()
        matched: list[Any] = []

        # Strategy A: direct query on KnowledgeManager
        try:
            for entry in self._knowledge_manager.query(text):
                key = (entry.title, entry.content)
                if key not in seen:
                    seen.add(key)
                    matched.append(entry)
        except Exception:
            pass

        if matched:
            return matched

        # Strategy B: candidate terms from spec and tokens
        candidate_terms: list[str] = []
        if spec is not None:
            if spec.intent and spec.intent != text:
                candidate_terms.append(spec.intent)
            if spec.goal and spec.goal != text:
                candidate_terms.append(spec.goal)

        tokens = [t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 3 and t not in _STOPWORDS]
        candidate_terms.extend(tokens)

        for term in candidate_terms:
            try:
                for entry in self._knowledge_manager.query(term):
                    key = (entry.title, entry.content)
                    if key not in seen:
                        seen.add(key)
                        matched.append(entry)
            except Exception:
                pass

        if matched:
            return matched

        # Strategy C: Title and content inspection directly on knowledge base
        base = getattr(self._knowledge_manager, "base", None)
        if base is not None and hasattr(base, "all"):
            try:
                for entry in base.all():
                    blob = f"{entry.title} {entry.content}".lower()
                    if any(term.lower() in blob for term in candidate_terms if len(term) >= 3):
                        key = (entry.title, entry.content)
                        if key not in seen:
                            seen.add(key)
                            matched.append(entry)
            except Exception:
                pass

        return matched

    def _format_knowledge_response(self, entries: list[Any]) -> str:
        """Format retrieved knowledge entries with attribution."""
        top_entries = entries[:3]
        lines = [
            "Deterministic Knowledge Result (external AI unavailable):",
            "",
        ]
        for entry in top_entries:
            title = getattr(entry, "title", "Knowledge Entry")
            content = getattr(entry, "content", "")
            source = getattr(entry, "source", "internal")
            lines.append(f"### {title}")
            lines.append(content)
            lines.append(f"- Source: {source}")
            lines.append("")
        return "\n".join(lines).strip()

    def _format_tool_guidance(self, lowered_query: str, show_all: bool = False) -> str | None:
        """Format available deterministic tools and capabilities."""
        if self._tool_registry is None:
            return None
        tools = self._tool_registry.list()
        if not tools:
            return None

        if not show_all:
            matched_tools = [
                t for t in tools
                if t.name.lower() in lowered_query or any(tag.lower() in lowered_query for tag in t.tags)
            ]
        else:
            matched_tools = []

        if not matched_tools:
            matched_tools = tools

        lines = [
            "Deterministic Capability Guidance (external AI unavailable):",
            "",
            "Registered deterministic tools and capabilities:",
        ]
        for t in matched_tools[:10]:
            desc = t.description or "No description provided."
            lines.append(f"- **{t.name}** ({t.category}): {desc}")
        return "\n".join(lines)

    def _format_degraded_notice(self, text: str, error_context: str | None = None) -> str:
        """Format a clear, bounded degradation notice."""
        lines = [
            "External AI inference is currently unavailable.",
            "Atlas is operating in deterministic-first degraded mode.",
            "",
            "Deterministic capabilities available without AI inference:",
            "- Governed Self-Development requests (`DEVELOPMENT_REQUEST`)",
            "- Registered Tool execution & Orchestration (`ACTION_REQUEST`)",
            "- Local Knowledge retrieval & Memory recall",
            "- Proactive system advisory & Collective governance inspection",
        ]
        return "\n".join(lines)
