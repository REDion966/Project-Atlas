"""Atlas CLI — read-only architecture-model presentation (Phase 1.2).

Presentation-only: it renders the architecture self-knowledge model produced by
the kernel accessor. It contains NO discovery logic.
"""

from __future__ import annotations

import json
from typing import Any


def cmd_architecture(atlas: Any, args: Any) -> str:
    """Render the architecture self-knowledge model (read-only)."""
    model = atlas.architecture_model()
    if bool(getattr(args, "json", False)):
        return json.dumps(model.to_dict(), indent=2, sort_keys=True)
    return model.to_markdown()
