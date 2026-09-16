"""Atlas CLI — validated knowledge retrieval presentation (C6.1).

Presentation-only: renders the result produced by the kernel accessor
``Atlas.validated_knowledge(query)``. Contains NO retrieval/discovery logic and
performs no mutation.
"""

from __future__ import annotations

import json
from typing import Any


def cmd_validated_knowledge(atlas: Any, args: Any) -> str:
    """Render the validated knowledge retrieval result (read-only)."""
    query = str(getattr(args, "query", "") or "")
    result = atlas.validated_knowledge(query)
    if bool(getattr(args, "json", False)):
        return json.dumps(result.to_dict(), indent=2, sort_keys=True)
    return result.to_markdown()
