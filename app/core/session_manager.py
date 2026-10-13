"""Gestionnaire de session conversationnelle multi-tours avec persistance et résilience.

Supprime définitivement le mode stateless :
- Maintien d'un buffer d'historique en mémoire vive avec fenêtrage glissant (Sliding Window)
- TTL d'inactivité (par défaut 30 minutes) pour éviter la pollution de contextes obsolètes
- Rechargement automatique de l'historique depuis SQLite (conversation_logs) après redémarrage du serveur
- Résolution contextuelle d'anaphores et de références croisées
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.database import get_database_manager

logger = logging.getLogger(__name__)

DEFAULT_SESSION_TTL_SECONDS = 86400  # 24 heures (continuité de journée sans coupure intempestive)
MAX_HISTORY_TURNS = 20  # 10 échanges complets (user + assistant)


class SessionManager:
    """Gestionnaire de sessions conversationnelles persistant et résilient."""

    def __init__(self, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS):
        self.ttl = timedelta(seconds=ttl_seconds)
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Récupère le contexte actif d'une session ou le restaure depuis SQLite."""
        if not session_id:
            session_id = "default"

        now = datetime.now()

        # 1. Vérification en cache mémoire
        if session_id in self._sessions:
            sess_entry = self._sessions[session_id]
            last_active = sess_entry.get("last_active", now)

            # Vérification de l'expiration TTL (24h)
            if (now - last_active) > self.ttl:
                logger.debug(f"Session '{session_id}' expirée (> {self.ttl.total_seconds()}s). Réinitialisation.")
                sess_entry["context"] = {}
                sess_entry["last_active"] = now
                return sess_entry["context"]

            sess_entry["last_active"] = now
            return sess_entry["context"]

        # 2. Session absente de la RAM : restauration depuis SQLite
        restored_context: Dict[str, Any] = {}
        try:
            db = get_database_manager()
            if db:
                logs_res = db.get_conversation_logs(
                    session_id=session_id,
                    limit=MAX_HISTORY_TURNS // 2,
                )
                items = logs_res.get("items", [])
                if items:
                    # Inverser pour obtenir l'ordre chronologique
                    items_chrono = list(reversed(items))
                    history: List[Dict[str, str]] = []
                    for item in items_chrono:
                        raw_q = (item.get("raw_query") or "").strip()
                        spoken = (item.get("spoken_response") or "").strip()
                        ts = str(item.get("created_at") or now.isoformat())
                        if raw_q:
                            history.append({"role": "user", "text": raw_q, "timestamp": ts})
                        if spoken:
                            history.append({"role": "assistant", "text": spoken, "timestamp": ts})

                    if history:
                        restored_context["history"] = history
                        logger.debug(
                            f"Session '{session_id}' restaurée depuis SQLite ({len(history)} messages)."
                        )
        except Exception as exc:
            logger.debug(f"Impossible de restaurer la session '{session_id}' depuis SQLite: {exc}")

        self._sessions[session_id] = {
            "context": restored_context,
            "last_active": now,
        }
        return restored_context

    def record_turn(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Enregistre un échange (user + assistant) et met à jour l'activité de la session."""
        if not session_id:
            session_id = "default"

        ctx = self.get_session(session_id)
        if extra_context:
            ctx.update(extra_context)

        now = datetime.now()
        history = ctx.setdefault("history", [])
        u_clean = user_text.strip()
        a_clean = assistant_text.strip()

        if u_clean:
            history.append({"role": "user", "text": u_clean, "timestamp": now.isoformat()})
        if a_clean:
            history.append({"role": "assistant", "text": a_clean, "timestamp": now.isoformat()})

        if len(history) > MAX_HISTORY_TURNS:
            ctx["history"] = history[-MAX_HISTORY_TURNS:]

        if session_id in self._sessions:
            self._sessions[session_id]["last_active"] = now
        else:
            self._sessions[session_id] = {
                "context": ctx,
                "last_active": now,
            }

    def clear_session(self, session_id: str) -> None:
        """Réinitialise une session spécifique à vide."""
        if not session_id:
            session_id = "default"
        self._sessions[session_id] = {
            "context": {"history": []},
            "last_active": datetime.now(),
        }

    def clear_all(self) -> None:
        """Réinitialise l'ensemble des sessions en mémoire."""
        self._sessions.clear()

    def as_dict_store(self) -> Dict[str, Dict[str, Any]]:
        """Proxy dictionnaire pour la compatibilité avec l'ancien get_sessions_store()."""
        class SessionStoreProxy(dict):
            def __init__(self, manager: "SessionManager"):
                super().__init__()
                self._manager = manager

            def __getitem__(self, key: str) -> Dict[str, Any]:
                return self._manager.get_session(key)

            def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
                ctx = self._manager.get_session(key)
                ctx.clear()
                ctx.update(value)

            def setdefault(self, key: str, default: Any = None) -> Any:
                return self._manager.get_session(key)

            def get(self, key: str, default: Any = None) -> Any:
                if key in self._manager._sessions:
                    return self._manager.get_session(key)
                return default

            def clear(self) -> None:
                self._manager.clear_all()

        return SessionStoreProxy(self)


_global_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Singleton d'accès au gestionnaire de sessions."""
    global _global_session_manager
    if _global_session_manager is None:
        _global_session_manager = SessionManager()
    return _global_session_manager
