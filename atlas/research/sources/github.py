"""Atlas Research — GitHub Repository Source (external-repository intelligence).

A bounded, deterministic, fail-closed adapter that retrieves a PUBLIC GitHub
repository's structure and source files through GitHub's public API/raw
endpoints, reusing the EXISTING web safety layer
(:class:`atlas.research.sources.web.WebSourceAdapter` + ``WebHostPolicy``) for
scheme validation, host authorization, SSRF protection, redirect revalidation,
timeouts and response-size caps.

Boundaries (mirrors the existing web adapter contract):

* **Authorization is external**: the host policy defaults to deny-by-default
  (``DENY_ALL_HOSTS``). GitHub hosts are only reachable when the operator
  explicitly authorizes them through the EXISTING research host allow-list.
* **No token required** for public repositories; no credentials are ever sent
  or stored.
* **No execution**: acquired source is DATA. Nothing here imports, runs,
  installs, or evaluates external code.
* **Bounded**: capped file counts, per-file and total bytes, path length, tree
  entries, and a strict extension allow-list.
* **Path-safe**: repository paths reject traversal, absolute paths, backslashes
  and control characters.
* **Fail-closed**: malformed targets, unauthorized hosts, oversized/too-many
  files, and transport failures are reported as explicit errors — never a
  fabricated success.

Pure logic over the injected transport. No AI, no kernel, no storage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from atlas.research.source_catalog import (
    CODE_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
)
from atlas.research.sources.web import (
    DENY_ALL_HOSTS,
    WebHostPolicy,
    WebSourceAdapter,
    web_host_policy_from_hosts,
)

#: Canonical public GitHub hosts (API + raw content).
GITHUB_API_HOST: str = "api.github.com"
GITHUB_RAW_HOST: str = "raw.githubusercontent.com"
GITHUB_HOSTS: tuple[str, ...] = (GITHUB_API_HOST, GITHUB_RAW_HOST)

#: Hard bounds (deterministic; audit these, never per-request).
MAX_FILES: int = 200
MAX_FILE_BYTES: int = 200_000
MAX_TOTAL_BYTES: int = 2_000_000
MAX_PATH_CHARS: int = 300
MAX_TREE_ENTRIES: int = 20_000
MAX_RESPONSE_BYTES: int = 1_500_000
MAX_OWNER_CHARS: int = 100
MAX_REF_CHARS: int = 200

_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_PATH_RE = re.compile(r"^[^\x00-\x1f\\]+$")


@dataclass(frozen=True, slots=True)
class RemoteFile:
    """One repository file discovered in the git tree (metadata only)."""

    path: str
    size: int
    kind: str = "blob"

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "size": self.size, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class AcquiredRepository:
    """Bounded, read-only acquisition of one public repository.

    ``files`` holds ``(relative_path, text)`` pairs of the permitted source /
    document files actually retrieved. ``errors`` records everything skipped or
    refused (bounded). ``provenance`` records the endpoints used. External
    content is DATA — it is never executed and never trusted.
    """

    ok: bool
    owner: str = ""
    name: str = ""
    ref: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    files: tuple[tuple[str, str], ...] = ()
    truncated: bool = False
    tree_entries: int = 0
    errors: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def file_count(self) -> int:
        return len(self.files)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "owner": self.owner,
            "name": self.name,
            "ref": self.ref,
            "metadata": dict(self.metadata),
            "file_count": self.file_count,
            "truncated": self.truncated,
            "tree_entries": self.tree_entries,
            "files": [path for path, _ in self.files],
            "errors": list(self.errors),
            "provenance": dict(self.provenance),
        }


def github_host_policy(extra_hosts: Sequence[str] = ()) -> WebHostPolicy:
    """Deny-by-default policy allowing ONLY the canonical GitHub hosts (+ extras).

    Deterministic and explicit: it never enables ``allow_unlisted``, so all
    SSRF/IP protections remain mandatory.
    """
    return web_host_policy_from_hosts(tuple(GITHUB_HOSTS) + tuple(extra_hosts or ()))


def parse_repository_target(target: Any) -> tuple[str, str] | None:
    """Return ``(owner, name)`` for a repository target, or ``None``.

    Accepts ``owner/name``, ``https://github.com/owner/name`` (with optional
    ``.git``), and ``git@github.com:owner/name.git``. Anything else fails
    closed. Owner/name segments are strictly validated.
    """
    if not isinstance(target, str):
        return None
    text = target.strip()
    if not text:
        return None
    # Strip common URL / scp-like prefixes.
    text = re.sub(r"^https?://", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^git@", "", text, flags=re.IGNORECASE)
    text = text.replace(":", "/", 1) if "@" not in text and "://" not in text else text
    text = re.sub(r"^github\.com/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^www\.github\.com/", "", text, flags=re.IGNORECASE)
    text = text.split("?", 1)[0].split("#", 1)[0].strip("/")
    text = text[:-4] if text.lower().endswith(".git") else text
    # Drop any leading path noise (e.g. "repos/") is NOT allowed: require the
    # first two segments to be owner/name.
    parts = [p for p in text.split("/") if p]
    if len(parts) < 2:
        return None
    owner, name = parts[0], parts[1]
    if not _valid_segment(owner) or not _valid_segment(name):
        return None
    return owner, name


def _valid_segment(segment: str) -> bool:
    return (
        isinstance(segment, str)
        and 0 < len(segment) <= MAX_OWNER_CHARS
        and bool(_OWNER_RE.match(segment))
        and segment not in (".", "..")
    )


def safe_repository_path(path: Any) -> str | None:
    """Return a confined relative repository path, or ``None`` (fail-closed).

    Rejects absolute paths, traversal, backslashes, control characters, empty
    segments and over-long paths.
    """
    if not isinstance(path, str):
        return None
    raw = path.strip()
    if not raw or len(raw) > MAX_PATH_CHARS:
        return None
    if raw.startswith("/") or raw.startswith("~"):
        return None
    if not _SAFE_PATH_RE.match(raw):
        return None
    segments = raw.split("/")
    if any(seg in ("", ".", "..") for seg in segments):
        return None
    return raw


class GitHubRepositorySource:
    """Bounded, governed acquisition of a public GitHub repository.

    Args:
        transport: Optional injected single-hop HTTP transport (tests inject a
            fake so no live network is touched).
        host_policy: The host authorization policy. Defaults to
            ``DENY_ALL_HOSTS`` — no GitHub host is reachable until the operator
            explicitly authorizes it.
        resolver: Optional DNS resolver (passed through to the web adapter).
        timeout: Per-request bound (seconds).
        max_bytes: Per-response bound used by the web adapter.
    """

    def __init__(
        self,
        *,
        transport: Any | None = None,
        host_policy: WebHostPolicy | None = None,
        resolver: Callable[[str], tuple[str, ...]] | None = None,
        timeout: float = 10.0,
        max_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        self._adapter = WebSourceAdapter(
            transport=transport,
            host_policy=host_policy or DENY_ALL_HOSTS,
            resolver=resolver,
            timeout=timeout,
            max_bytes=max_bytes,
        )
        self._host_policy = host_policy or DENY_ALL_HOSTS

    @property
    def host_policy(self) -> WebHostPolicy:
        return self._host_policy

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def repository_metadata(self, owner: str, name: str) -> dict[str, Any] | None:
        """Bounded public repository metadata, or ``None`` (fail-closed)."""
        if not _valid_segment(owner) or not _valid_segment(name):
            return None
        payload = self._get_json(
            f"https://{GITHUB_API_HOST}/repos/{owner}/{name}"
        )
        if not isinstance(payload, dict):
            return None
        return {
            "owner": owner,
            "name": name,
            "full_name": str(payload.get("full_name") or f"{owner}/{name}"),
            "description": str(payload.get("description") or "")[:400],
            "default_branch": str(payload.get("default_branch") or "")[:MAX_REF_CHARS],
            "language": str(payload.get("language") or "")[:60],
            "size_kb": int(payload.get("size") or 0),
            "stars": int(payload.get("stargazers_count") or 0),
            "archived": bool(payload.get("archived", False)),
        }

    def repository_tree(
        self, owner: str, name: str, ref: str
    ) -> tuple[RemoteFile, ...] | None:
        """Bounded recursive git-tree listing, or ``None`` (fail-closed)."""
        if not _valid_segment(owner) or not _valid_segment(name) or not self._valid_ref(ref):
            return None
        payload = self._get_json(
            f"https://{GITHUB_API_HOST}/repos/{owner}/{name}/git/trees/{ref}?recursive=1"
        )
        if not isinstance(payload, dict):
            return None
        raw = payload.get("tree")
        if not isinstance(raw, list):
            return None
        out: list[RemoteFile] = []
        for entry in raw[:MAX_TREE_ENTRIES]:
            if not isinstance(entry, dict):
                continue
            path = safe_repository_path(entry.get("path"))
            if path is None:
                continue
            out.append(
                RemoteFile(
                    path=path,
                    size=int(entry.get("size") or 0),
                    kind=str(entry.get("type") or "blob"),
                )
            )
        return tuple(out)

    def fetch_file(self, owner: str, name: str, ref: str, path: str) -> tuple[str, str]:
        """Fetch one confinement-checked file. Returns ``(text, error)``."""
        safe = safe_repository_path(path)
        if safe is None:
            return ("", "unsafe path")
        if not _valid_segment(owner) or not _valid_segment(name) or not self._valid_ref(ref):
            return ("", "invalid repository coordinates")
        text, error = self._get_text(
            f"https://{GITHUB_RAW_HOST}/{owner}/{name}/{ref}/{safe}"
        )
        return (text, error)

    def acquire(
        self,
        target: Any,
        *,
        ref: str = "",
        keywords: Sequence[str] = (),
        max_files: int = MAX_FILES,
        max_file_bytes: int = MAX_FILE_BYTES,
        max_total_bytes: int = MAX_TOTAL_BYTES,
        extensions: frozenset[str] | None = None,
        include_docs: bool = True,
    ) -> AcquiredRepository:
        """Acquire a bounded set of permitted files from a public repository.

        ``keywords`` (when supplied) deterministically PRE-RANK which files to
        retrieve first, so a large repository yields the most relevant material
        within the same bounded budget. Nothing is executed; every refusal is
        recorded in ``errors``.
        """
        parsed = parse_repository_target(target)
        if parsed is None:
            return AcquiredRepository(ok=False, errors=("unrecognised repository target",))
        owner, name = parsed
        provenance: dict[str, Any] = {
            "api_host": GITHUB_API_HOST,
            "raw_host": GITHUB_RAW_HOST,
            "target": f"{owner}/{name}",
        }

        metadata = self.repository_metadata(owner, name)
        if metadata is None:
            return AcquiredRepository(
                ok=False, owner=owner, name=name,
                errors=("repository metadata unavailable (unauthorized or unknown)",),
                provenance=provenance,
            )
        resolved_ref = (ref or metadata.get("default_branch") or "").strip()
        if not resolved_ref:
            return AcquiredRepository(
                ok=False, owner=owner, name=name,
                errors=("no default branch resolved",), provenance=provenance,
            )
        provenance["ref"] = resolved_ref

        tree = self.repository_tree(owner, name, resolved_ref)
        if tree is None:
            return AcquiredRepository(
                ok=False, owner=owner, name=name, ref=resolved_ref,
                metadata=metadata, errors=("repository tree unavailable",),
                provenance=provenance,
            )

        allowed = extensions or (
            (CODE_EXTENSIONS | DOCUMENT_EXTENSIONS) if include_docs else CODE_EXTENSIONS
        )
        candidates = [
            entry
            for entry in tree
            if entry.kind == "blob" and _extension(entry.path) in allowed
        ]
        ranked = _rank_candidates(candidates, keywords)
        truncated = len(ranked) > max_files
        selected = ranked[: max(1, max_files)]

        files: list[tuple[str, str]] = []
        errors: list[str] = []
        total = 0
        for entry in selected:
            if entry.size and entry.size > max_file_bytes:
                errors.append(f"{entry.path}: skipped (file too large)")
                continue
            if total + (entry.size or 0) > max_total_bytes:
                truncated = True
                break
            text, error = self.fetch_file(owner, name, resolved_ref, entry.path)
            if error:
                errors.append(f"{entry.path}: {error}")
                continue
            size = len(text.encode("utf-8", errors="replace"))
            if size > max_file_bytes:
                errors.append(f"{entry.path}: skipped (file too large)")
                continue
            total += size
            files.append((entry.path, text))

        return AcquiredRepository(
            ok=bool(files),
            owner=owner,
            name=name,
            ref=resolved_ref,
            metadata=metadata,
            files=tuple(files),
            truncated=truncated,
            tree_entries=len(tree),
            errors=tuple(errors[:100]),
            provenance=provenance,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _valid_ref(ref: Any) -> bool:
        if not isinstance(ref, str):
            return False
        text = ref.strip()
        return bool(text) and len(text) <= MAX_REF_CHARS and _SAFE_PATH_RE.match(text) is not None

    def _get_json(self, url: str) -> Any | None:
        text, error = self._get_text(url)
        if error:
            return None
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

    def _get_text(self, url: str) -> tuple[str, str]:
        try:
            profile = self._adapter.load(url)
        except ValueError as exc:
            return ("", f"refused ({exc})")
        except Exception as exc:  # fail-closed
            return ("", f"transport error ({type(exc).__name__})")
        load_error = str((profile.metadata or {}).get("load_error") or "")
        if load_error:
            return ("", load_error[:200])
        status = int((profile.metadata or {}).get("http_status") or 0)
        if status and not (200 <= status < 300):
            return ("", f"http {status}")
        return (profile.text, "")


def _extension(path: str) -> str:
    index = path.rfind(".")
    slash = path.rfind("/")
    if index <= slash:
        return ""
    return path[index:].lower()


def _rank_candidates(entries: Sequence[RemoteFile], keywords: Sequence[str]) -> list[RemoteFile]:
    """Deterministically order candidate files: keyword relevance, then path.

    Documentation and shallow paths rank first, so a bounded budget captures the
    highest-signal material. Never semantic; purely lexical and deterministic.
    """
    terms = _normalise_keywords(keywords)

    def score(entry: RemoteFile) -> tuple:
        lowered = entry.path.lower()
        hits = sum(1 for term in terms if term in lowered)
        depth = lowered.count("/")
        is_doc = 1 if _extension(entry.path) in DOCUMENT_EXTENSIONS else 0
        return (-hits, depth, -is_doc, entry.path)

    return sorted(entries, key=score)


def _normalise_keywords(keywords: Sequence[str]) -> tuple[str, ...]:
    out: list[str] = []
    for keyword in keywords or ():
        if isinstance(keyword, str):
            text = keyword.strip().lower()
            if text and text not in out:
                out.append(text)
    return tuple(out[:32])
