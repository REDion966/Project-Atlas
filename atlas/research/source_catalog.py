"""
Atlas Research — Source Catalog (Phase 17.2)

Shared, pure constants describing the source formats the adapter layer can
normalize. Imported by both the source adapters (``atlas/research/sources/``)
and the Research Planner (``atlas/research/planner.py``) so URI-kind inference
and adapter support detection can never drift apart.

No runtime dependencies beyond the standard library.
"""

from atlas.research.models import SourceKind

# Formats treated as human-readable documents.
DOCUMENT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".rst",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".html",
        ".htm",
        ".csv",
        ".xml",
        ".log",
    }
)

# Formats treated as source code.
CODE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".pyi",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".go",
        ".rs",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cs",
        ".rb",
        ".php",
        ".sh",
        ".sql",
        ".kt",
        ".swift",
    }
)

# Every format the adapter layer can normalize (documents + code).
TEXT_EXTENSIONS: frozenset[str] = DOCUMENT_EXTENSIONS | CODE_EXTENSIONS

# Human-readable language family per file extension. Unknown extensions map
# to an empty string (callers may fall back to the raw format suffix).
LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "restructuredtext",
    ".txt": "text",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".html": "html",
    ".htm": "html",
    ".csv": "csv",
    ".xml": "xml",
    ".log": "text",
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "shell",
    ".sql": "sql",
    ".kt": "kotlin",
    ".swift": "swift",
}

# Strict URI schemes the adapter layer understands.
DOCUMENT_SCHEMES: frozenset[str] = frozenset({"", "file"})
CODEBASE_SCHEMES: frozenset[str] = frozenset({"", "file", "code"})
WORKSPACE_SCHEME: str = "workspace"
