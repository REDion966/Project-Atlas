"""
Atlas Evolution Autonomy — Serialization — Phase 16.4

Version-safe serialization helpers for autonomy dataclasses.

Preserves:
- Enum values by name (stable across reordering).
- Datetimes as ISO 8601 strings.
- Nested frozen dataclasses.

Does NOT:
- Import infrastructure, gateway, or AI modules.
- Mutate input objects.

Pure serialization logic. No business rules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Type, TypeVar, Union, get_type_hints

T = TypeVar("T")


def to_serializable(obj: Any) -> Any:
    """Recursively convert autonomy objects to plain JSON-serializable dicts.

    Enums become their ``name``; datetimes become ISO strings; dataclasses
    become dicts of their fields.
    """
    if isinstance(obj, Enum):
        return obj.name
    if isinstance(obj, datetime):
        return obj.isoformat()
    if is_dataclass(obj) and not isinstance(obj, type):
        return {field.name: to_serializable(getattr(obj, field.name)) for field in fields(obj)}
    if isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_serializable(v) for v in obj]
    return obj


def from_serializable(value: Any, cls: Type[T]) -> T:
    """Deserialize ``value`` into an instance of ``cls``.

    Handles enums, datetimes, dataclasses, Optional, list, and dict.
    """
    if value is None:
        return None  # type: ignore[return-value]

    origin = getattr(cls, "__origin__", None)

    # Optional[X]
    if origin is Union:
        args = cls.__args__  # type: ignore[attr-defined]
        if type(None) in args:
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return from_serializable(value, non_none[0])  # type: ignore[return-value]
        return value  # type: ignore[return-value]

    # list[X]
    if origin in (list, List):
        arg = cls.__args__[0]  # type: ignore[attr-defined]
        return [from_serializable(item, arg) for item in value]  # type: ignore[return-value]

    # dict[K, V]
    if origin in (dict, Dict):
        key_type, val_type = cls.__args__  # type: ignore[attr-defined]
        return {  # type: ignore[return-value]
            from_serializable(k, key_type): from_serializable(v, val_type)
            for k, v in value.items()
        }

    try:
        if isinstance(cls, type) and issubclass(cls, Enum):
            return cls[value]  # type: ignore[return-value]
        if cls is datetime:
            return datetime.fromisoformat(value)  # type: ignore[return-value]
        if isinstance(cls, type) and is_dataclass(cls):
            type_hints = get_type_hints(cls)
            kwargs: dict[str, Any] = {}
            for k, v in value.items():
                field_type = type_hints.get(k, Any)
                kwargs[k] = _deserialize_field(v, field_type)
            return cls(**kwargs)
    except TypeError:
        pass

    return value  # type: ignore[return-value]


def _deserialize_field(value: Any, field_type: Any) -> Any:
    """Deserialize a single field value according to its annotation."""
    if value is None:
        return None

    origin = getattr(field_type, "__origin__", None)

    # Optional[X]
    if origin is Union:
        args = field_type.__args__
        if type(None) in args:
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return _deserialize_field(value, non_none[0])
        return value

    # list[X]
    if origin in (list, List):
        arg = field_type.__args__[0]
        return [_deserialize_field(item, arg) for item in value]

    # dict[K, V]
    if origin in (dict, Dict):
        key_type, val_type = field_type.__args__
        return {
            _deserialize_field(k, key_type): _deserialize_field(v, val_type)
            for k, v in value.items()
        }

    try:
        if isinstance(field_type, type) and issubclass(field_type, Enum):
            return field_type[value]
        if field_type is datetime:
            return datetime.fromisoformat(value)
        if isinstance(field_type, type) and is_dataclass(field_type):
            return from_serializable(value, field_type)
    except TypeError:
        pass

    return value