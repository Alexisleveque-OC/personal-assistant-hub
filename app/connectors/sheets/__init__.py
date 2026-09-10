"""Connecteur Google Sheets pour le hub d'assistant personnel."""
from app.connectors.sheets.models import (
    DayMealPlan,
    Recipe,
    ShoppingItem,
    RayonSetting,
    SheetSchemaSnapshot,
)
from app.connectors.sheets.schema_validator import (
    SheetSchemaValidator,
    SheetSchemaError,
    SheetSchemaWorksheetNotFoundError,
    SheetSchemaHeaderDriftError,
    ValidationReport,
)

__all__ = [
    "DayMealPlan",
    "Recipe",
    "ShoppingItem",
    "RayonSetting",
    "SheetSchemaSnapshot",
    "SheetSchemaValidator",
    "SheetSchemaError",
    "SheetSchemaWorksheetNotFoundError",
    "SheetSchemaHeaderDriftError",
    "ValidationReport",
]
