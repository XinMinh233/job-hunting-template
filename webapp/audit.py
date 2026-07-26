from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog


def audit(
    db: Session,
    action: str,
    *,
    actor_user_id: str | None = None,
    target: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target=target,
            detail_json=json.dumps(detail or {}, ensure_ascii=False),
        )
    )

