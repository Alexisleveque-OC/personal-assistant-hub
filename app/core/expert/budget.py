"""Budget mensuel de l'expert Claude : enregistrement du coût de chaque appel et garde-fou (CLAUDE_MONTHLY_BUDGET_USD)."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from app.config import settings
from app.core.expert.llm import ExpertUsage
from app.core.expert.pricing import usage_cost_usd


def month_start_iso(now: Optional[datetime] = None) -> str:
    """Début du mois civil en cours (UTC), au format ISO comparé aux horodatages de llm_usage."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def month_usage(db: Any) -> Dict[str, Any]:
    totals = db.get_llm_usage_totals(month_start_iso())
    budget = settings.claude_monthly_budget_usd
    cost = round(totals["cost_usd"], 4)
    return {
        "month_cost_usd": cost, "budget_usd": budget, "remaining_usd": round(max(budget - cost, 0.0), 4),
        "calls": totals["calls"],
    }


def budget_exhausted_reason(db: Any) -> Optional[str]:
    """Raison explicite si le budget du mois est atteint (l'expert n'est alors plus proposé), sinon None."""
    usage = month_usage(db)
    if usage["month_cost_usd"] < usage["budget_usd"]:
        return None
    return (
        f"budget mensuel de l'expert Claude atteint ({usage['month_cost_usd']:.2f} $ sur {usage['budget_usd']:.2f} $)"
    )


def record_usages(db: Any, usages: Sequence[ExpertUsage], session_id: Optional[str]) -> float:
    """Enregistre chaque appel facturé ; renvoie le coût total du tour en $."""
    total = 0.0
    for usage in usages:
        cost = usage_cost_usd(usage)
        total += cost
        db.add_llm_usage(
            usage.model or "inconnu", usage.input_tokens, usage.output_tokens, usage.cache_read_input_tokens,
            usage.cache_creation_input_tokens, cost, session_id,
        )
    return total


def usages_payload(usages: List[ExpertUsage]) -> List[Dict[str, Any]]:
    return [u.model_dump() for u in usages]
