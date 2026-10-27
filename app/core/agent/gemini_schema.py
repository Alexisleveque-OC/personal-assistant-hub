"""Conversion d'un modèle Pydantic en schéma de paramètres Gemini (sous-ensemble OpenAPI de `FunctionDeclaration`).

Le JSON Schema de Pydantic utilise `$ref`, `anyOf` pour les `Optional`, `title`, `default`… que Gemini ne
supporte pas : les références sont dépliées, `Optional[X]` devient `X` + `nullable`, le reste est retiré.
La validation stricte reste assurée côté serveur par Pydantic.
"""
from typing import Any, Dict

from pydantic import BaseModel

Schema = Dict[str, Any]
_COPIED_KEYWORDS = ("enum", "minimum", "maximum")
_DATE_HINT = "Date au format AAAA-MM-JJ."


def to_gemini_schema(model: type[BaseModel]) -> Schema:
    raw = model.model_json_schema()
    return _convert(raw, raw.get("$defs", {}))


def _convert(node: Schema, defs: Dict[str, Schema]) -> Schema:
    if "$ref" in node:
        target = defs[node["$ref"].rsplit("/", 1)[-1]]
        return _convert({**target, **{k: v for k, v in node.items() if k != "$ref"}}, defs)

    if "anyOf" in node:
        variants = [v for v in node["anyOf"] if v.get("type") != "null"]
        if len(variants) != 1 or len(variants) == len(node["anyOf"]):
            raise ValueError(f"Union non supportée par le schéma Gemini (seul Optional[X] l'est) : {node['anyOf']}")
        extra = {"description": node["description"]} if "description" in node else {}
        return {**_convert({**variants[0], **extra}, defs), "nullable": True}

    schema_type = node.get("type")
    out: Schema = {"type": schema_type} if schema_type else {}
    description = node.get("description")
    if node.get("format") == "date":
        description = f"{description} {_DATE_HINT}" if description else _DATE_HINT
    elif node.get("format") == "date-time":
        out["format"] = "date-time"
    if description:
        out["description"] = description
    out.update({k: node[k] for k in _COPIED_KEYWORDS if k in node})
    if schema_type == "integer" and "exclusiveMinimum" in node:
        out["minimum"] = node["exclusiveMinimum"] + 1

    if schema_type == "object":
        out["properties"] = {name: _convert(prop, defs) for name, prop in node.get("properties", {}).items()}
        if node.get("required"):
            out["required"] = list(node["required"])
    elif schema_type == "array":
        out["items"] = _convert(node["items"], defs)
    return out
