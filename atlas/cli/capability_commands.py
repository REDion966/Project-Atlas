"""Atlas CLI — read-only capability model presentation (C5.1).

Presentation-only: it renders the canonical capability model produced by the
kernel accessor. It contains NO capability discovery logic.
"""

from __future__ import annotations

import json
from typing import Any


def cmd_capabilities(atlas: Any, args: Any) -> str:
    """Render the canonical capability model (read-only)."""
    model = atlas.capability_model()
    if bool(getattr(args, "json", False)):
        return json.dumps(model.to_dict(), indent=2, sort_keys=True)
    return model.to_markdown()
