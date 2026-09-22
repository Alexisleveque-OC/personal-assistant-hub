"""Module de sécurité et d'authentification par clé API."""
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Clé secrète requise pour authentifier les requêtes distantes.",
)


async def verify_api_key(
    api_key: Optional[str] = Security(api_key_header),
) -> Optional[str]:
    """Valide la présence et l'exactitude de la clé API.
    
    - Si `settings.api_key` est vide ou non définie : mode permissif (accès autorisé).
    - Si `settings.api_key` est définie : vérification stricte du header `X-API-Key`.
    """
    configured_key = settings.api_key.strip() if settings.api_key else ""
    if not configured_key:
        return None

    if not api_key or api_key.strip() != configured_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key
