"""Erreur métier commune aux outils de l'agent : son message est renvoyé tel quel au modèle (jamais masqué)."""


class ToolError(Exception):
    """Erreur métier explicite renvoyée à l'agent pour qu'il se corrige ou informe l'utilisateur."""
