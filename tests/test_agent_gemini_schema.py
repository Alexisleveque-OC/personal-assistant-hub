"""Tests de la conversion Pydantic → schéma de paramètres Gemini (sous-ensemble OpenAPI)."""
from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.agent.gemini_schema import to_gemini_schema


class Color(str, Enum):
    RED = "rouge"
    BLUE = "bleu"


class Inner(BaseModel):
    level: Optional[int] = Field(None, ge=1, le=10, description="Niveau de 1 à 10")


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int = Field(gt=0, description="Identifiant")
    day: date
    color: Optional[Color] = None
    tags: List[str] = Field(default_factory=list)
    inner: Inner


def _walk_keys(node, keys=None):
    keys = set() if keys is None else keys
    if isinstance(node, dict):
        keys.update(node)
        for value in node.values():
            _walk_keys(value, keys)
    elif isinstance(node, list):
        for value in node:
            _walk_keys(value, keys)
    return keys


def test_object_with_required_fields_and_descriptions():
    schema = to_gemini_schema(Args)
    assert schema["type"] == "object"
    assert schema["required"] == ["session_id", "day", "inner"]
    assert schema["properties"]["session_id"] == {"type": "integer", "description": "Identifiant", "minimum": 1}


def test_refs_are_inlined_and_unsupported_keywords_dropped():
    schema = to_gemini_schema(Args)
    assert not _walk_keys(schema) & {"$ref", "$defs", "title", "default", "additionalProperties", "anyOf", "exclusiveMinimum"}
    inner_level = schema["properties"]["inner"]["properties"]["level"]
    assert inner_level == {"type": "integer", "description": "Niveau de 1 à 10", "minimum": 1, "maximum": 10, "nullable": True}


def test_optional_enum_becomes_nullable_string_enum():
    color = to_gemini_schema(Args)["properties"]["color"]
    assert color == {"type": "string", "enum": ["rouge", "bleu"], "nullable": True}


def test_date_is_a_described_string_and_arrays_keep_items():
    props = to_gemini_schema(Args)["properties"]
    assert props["day"]["type"] == "string"
    assert "AAAA-MM-JJ" in props["day"]["description"]
    assert props["tags"] == {"type": "array", "items": {"type": "string"}}
