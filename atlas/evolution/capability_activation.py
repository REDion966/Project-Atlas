"""Atlas Evolution — Governed Capability Activation (Phase 5.3, gap G1).

After an OWNER-authorized promotion applies a change set, this module closes
the FINAL link of the direct-evolution lifecycle: it makes a newly promoted
capability module discoverable and invocable at runtime, by registering its
handlers on the EXISTING :class:`~atlas.reasoning.execution.registry.CapabilityRegistry`.

It is a bounded, path-confined, fail-closed seam for ONE known artifact shape —
the deterministic scaffold capability-handler factory module (a module-level
``CAPABILITY_NAME`` constant plus a class exposing ``handlers()``/``register()``
whose handlers return a small dict). Anything else in a promotion is NOT a
capability and is left untouched; a module that DECLARES the capability contract
but is malformed/invalid is refused fail-closed.

Security boundaries:
  * only ``.py`` files beneath the live repository root are considered;
  * architecture-sensitive prefixes are refused;
  * the on-disk module must byte-match the validated artifact's post content
    (no drift between promotion validation and activation);
  * the module is AST-validated for the exact supported contract BEFORE import
    (importlib executes only the known, validated shape);
  * handlers are adapted to the existing ``ExecutionResult`` contract and
    registered on the existing registry — no parallel registry/framework;
  * never referenced from ``tick()``; runs only inside the OWNER-gated
    promotion lifecycle (the Development Envelope can never reach it).

Model-independent: no AI, no network, stdlib only.
"""

from __future__ import annotations

import ast
import importlib.util
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from atlas.evolution.autonomy.code_sandbox import SandboxPathError
from atlas.evolution.promotion_artifact import _resolve, hash_content
from atlas.evolution.promotion_gate import ARCHITECTURE_SENSITIVE_PREFIXES

#: Module-level constant every supported capability module must declare.
CAPABILITY_CONTRACT_MARKER: str = "CAPABILITY_NAME"

#: Required factory methods on the supported capability class.
_REQUIRED_METHODS: frozenset[str] = frozenset({"handlers", "register"})


class CapabilityActivationError(RuntimeError):
    """Raised when a declared capability artifact cannot be activated."""


@dataclass(frozen=True, slots=True)
class CapabilityModuleContract:
    """A validated capability-module contract (pure data)."""

    module_path: str
    class_name: str
    capability_name: str


@dataclass(frozen=True, slots=True)
class CapabilityActivationResult:
    """Outcome of one capability-activation attempt."""

    activated: bool
    capabilities: tuple[str, ...] = ()
    reason: str = ""
    audit_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "activated": self.activated,
            "capabilities": list(self.capabilities),
            "reason": self.reason,
            "audit_id": self.audit_id,
        }


def _detect_contract(module_text: str) -> CapabilityModuleContract | None:
    """AST-detect the supported capability contract in ``module_text``.

    Returns ``None`` when the module does not DECLARE the contract (so it is
    simply not a capability). Raises when the module declares the contract but
    is malformed. Performs no execution.
    """
    try:
        tree = ast.parse(module_text)
    except SyntaxError as exc:
        raise CapabilityActivationError(f"module does not parse: {exc}") from exc

    declared_name: str | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == CAPABILITY_CONTRACT_MARKER:
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        declared_name = node.value.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == CAPABILITY_CONTRACT_MARKER:
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    declared_name = node.value.value

    if declared_name is None:
        return None  # not a capability module

    if not declared_name.strip():
        raise CapabilityActivationError("declared CAPABILITY_NAME is empty")

    class_name: str | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = {
                child.name for child in node.body if isinstance(child, ast.FunctionDef)
            }
            if _REQUIRED_METHODS <= methods:
                class_name = node.name
                break
    if class_name is None:
        raise CapabilityActivationError(
            "declared capability module has no class exposing handlers()/register()"
        )
    return CapabilityModuleContract(
        module_path="", class_name=class_name, capability_name=declared_name
    )


def _module_alias(capability_name: str) -> str:
    """Deterministic private module alias for a loaded capability module."""
    safe = re.sub(r"[^0-9a-zA-Z_]", "_", capability_name)
    return f"_atlas_activated_{safe}"


class CapabilityActivator:
    """Bounded, path-confined, fail-closed capability activator.

    Args:
        repo_root: The live repository root (path confinement).
        capability_registry: The EXISTING ``CapabilityRegistry``.
        audit_recorder: Optional ``callable(result) -> str`` invoked after a
            successful activation (returns an audit id).
        sensitive_prefixes: Module prefixes that may never be activated.
    """

    def __init__(
        self,
        repo_root: str | Path,
        capability_registry: Any,
        *,
        audit_recorder: Callable[[Any], str] | None = None,
        sensitive_prefixes: Iterable[str] = ARCHITECTURE_SENSITIVE_PREFIXES,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._registry = capability_registry
        self._audit_recorder = audit_recorder
        self._sensitive_prefixes = tuple(sensitive_prefixes)

    def __call__(self, artifact: Any) -> CapabilityActivationResult:
        """Callable alias of :meth:`activate` (the executor's activator seam)."""
        return self.activate(artifact)

    def activate(self, artifact: Any) -> CapabilityActivationResult:
        """Activate the capability in ``artifact`` (or report N/A).

        Returns a result with ``activated=False`` when the artifact contains no
        declared capability module. Raises :class:`CapabilityActivationError`
        on any malformed/invalid/unsupported declared capability, so the caller
        can fail the promotion closed.
        """
        if self._registry is None:
            raise CapabilityActivationError("capability registry is unavailable")
        if not self._repo_root.is_dir():
            raise CapabilityActivationError("repository root is unavailable")
        files = tuple(getattr(artifact, "files", ()) or ())
        if not files:
            return CapabilityActivationResult(False, reason="no promoted files")

        contracts: list[tuple[Any, CapabilityModuleContract]] = []
        for entry in files:
            path = str(getattr(entry, "path", "") or "")
            if not path.endswith(".py"):
                continue
            contract = _detect_contract(str(getattr(entry, "post_content", "") or ""))
            if contract is None:
                continue
            contracts.append((entry, contract))

        if not contracts:
            return CapabilityActivationResult(
                False, reason="artifact declares no capability module"
            )

        activated: list[str] = []
        for entry, contract in contracts:
            activated.extend(self._activate_one(entry, contract))

        result = CapabilityActivationResult(
            True,
            capabilities=tuple(sorted(dict.fromkeys(activated))),
            reason="capability registered",
        )
        if callable(self._audit_recorder):
            try:
                result = CapabilityActivationResult(
                    True,
                    capabilities=result.capabilities,
                    reason=result.reason,
                    audit_id=str(self._audit_recorder(result) or ""),
                )
            except Exception:
                pass
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _activate_one(self, entry: Any, contract: CapabilityModuleContract) -> list[str]:
        path = str(entry.path).replace("\\", "/")
        dotted = posixpath.splitext(path)[0].replace("/", ".")
        if any(dotted.startswith(prefix) for prefix in self._sensitive_prefixes):
            raise CapabilityActivationError(
                f"refusing to activate architecture-sensitive module {path!r}"
            )
        try:
            target = _resolve(self._repo_root, path)
        except SandboxPathError as exc:
            raise CapabilityActivationError(
                f"path rejected: {path!r} ({exc})"
            ) from exc
        if not target.is_file():
            raise CapabilityActivationError(f"activated module missing on disk: {path!r}")
        # No drift between the validated artifact content and the live file.
        if hash_content(target.read_text(encoding="utf-8")) != str(entry.post_hash):
            raise CapabilityActivationError(
                f"on-disk content drifted from the validated artifact: {path!r}"
            )

        module = self._import_confined_module(target, contract.capability_name)
        factory_cls = getattr(module, contract.class_name, None)
        if factory_cls is None or not callable(factory_cls):
            raise CapabilityActivationError(
                f"declared class {contract.class_name!r} not found in {path!r}"
            )
        try:
            factory = factory_cls()
            handlers = factory.handlers()
        except Exception as exc:
            raise CapabilityActivationError(
                f"capability factory failed to initialise: {type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(handlers, dict) or not handlers:
            raise CapabilityActivationError("capability factory exposed no handlers")

        names: list[str] = []
        for name, handler in handlers.items():
            if not isinstance(name, str) or not name.strip():
                raise CapabilityActivationError("capability name must be a non-empty string")
            if not callable(handler):
                raise CapabilityActivationError(f"handler for {name!r} is not callable")
            if self._registry.has(name):
                raise CapabilityActivationError(
                    f"capability {name!r} is already registered (refusing to overwrite)"
                )
            names.append(name)

        registered: list[str] = []
        try:
            for name in names:
                self._registry.register(
                    name, self._adapt_handler(name, handlers[name])
                )
                registered.append(name)
        except Exception as exc:
            for name in registered:  # never leave a partial registration
                try:
                    self._registry.unregister(name)
                except Exception:
                    pass
            raise CapabilityActivationError(
                f"capability registration failed: {type(exc).__name__}: {exc}"
            ) from exc
        return registered

    @staticmethod
    def _import_confined_module(target: Path, capability_name: str) -> Any:
        """Import the confined, contract-validated module (known shape only)."""
        alias = _module_alias(capability_name)
        try:
            spec = importlib.util.spec_from_file_location(alias, str(target))
            if spec is None or spec.loader is None:
                raise CapabilityActivationError("could not build an import spec")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except CapabilityActivationError:
            raise
        except Exception as exc:
            raise CapabilityActivationError(
                f"capability module failed to import: {type(exc).__name__}: {exc}"
            ) from exc
        return module

    @staticmethod
    def _adapt_handler(capability_name: str, handler: Callable) -> Callable:
        """Adapt a scaffold handler to the existing ExecutionResult contract."""
        from atlas.reasoning.execution.models import ExecutionResult

        def _invoke(params: Any) -> ExecutionResult:
            try:
                outcome = handler(params if isinstance(params, dict) else {})
            except Exception as exc:
                return ExecutionResult(
                    capability=capability_name,
                    success=False,
                    error=str(exc),
                    metadata={"source": "activated"},
                )
            if isinstance(outcome, ExecutionResult):
                return outcome
            if isinstance(outcome, dict):
                return ExecutionResult(
                    capability=capability_name,
                    success=bool(outcome.get("status") == "ok"),
                    output=dict(outcome),
                    metadata={"source": "activated"},
                )
            return ExecutionResult(
                capability=capability_name,
                success=False,
                error="unsupported capability handler return type",
                metadata={"source": "activated"},
            )

        return _invoke
