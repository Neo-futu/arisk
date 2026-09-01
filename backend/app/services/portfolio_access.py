"""Central role/menu and portfolio-scope authorization helpers."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.models import User

PortfolioAccessLevel = Literal["VIEW", "MANAGE"]

_ACCESS_RANK: dict[str, int] = {"VIEW": 1, "MANAGE": 2}


def get_user_permission_codes(session: Session, user_id: uuid.UUID) -> set[str]:
    rows = session.execute(
        text(
            """
            SELECT DISTINCT p.code
            FROM iam.user_role ur
            JOIN iam.role r ON r.id = ur.role_id AND r.is_active = TRUE
            JOIN iam.role_permission rp ON rp.role_id = r.id
            JOIN iam.permission p ON p.id = rp.permission_id
            WHERE ur.user_id = :user_id
            """
        ),
        {"user_id": user_id},
    ).scalars()
    return {str(code) for code in rows}


def get_user_menu_paths(session: Session, user_id: uuid.UUID) -> set[str]:
    rows = session.execute(
        text(
            """
            SELECT DISTINCT m.path
            FROM iam.user_role ur
            JOIN iam.role r ON r.id = ur.role_id AND r.is_active = TRUE
            JOIN iam.role_menu rm ON rm.role_id = r.id
            JOIN iam.menu m ON m.id = rm.menu_id AND m.is_active = TRUE
                AND m.release_stage = 'GA'
            WHERE ur.user_id = :user_id AND m.path IS NOT NULL
            """
        ),
        {"user_id": user_id},
    ).scalars()
    return {str(path) for path in rows if path}


def has_global_permission(session: Session, user: User, permission_code: str) -> bool:
    return bool(user.is_superuser or permission_code in get_user_permission_codes(session, user.id))


def ensure_global_permission(session: Session, user: User, permission_code: str) -> None:
    if not has_global_permission(session, user, permission_code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission_code}",
        )


def get_portfolio_access_level(
    session: Session,
    user: User,
    port_id: str,
) -> PortfolioAccessLevel | None:
    if user.is_superuser:
        return "MANAGE"

    level = session.execute(
        text(
            """
            SELECT access_level
            FROM iam.user_portfolio_access
            WHERE user_id = :user_id AND port_id = :port_id
            """
        ),
        {"user_id": user.id, "port_id": port_id},
    ).scalar_one_or_none()
    if level in _ACCESS_RANK:
        return level  # type: ignore[return-value]
    return None


def ensure_portfolio_access(
    session: Session,
    user: User,
    port_id: str,
    required_level: PortfolioAccessLevel = "VIEW",
    *,
    permission_code: str | None = None,
) -> PortfolioAccessLevel:
    required_permission = permission_code or (
        "portfolio.manage" if required_level == "MANAGE" else "portfolio.view"
    )
    ensure_global_permission(session, user, required_permission)

    granted_level = get_portfolio_access_level(session, user, port_id)
    if granted_level is None or _ACCESS_RANK[granted_level] < _ACCESS_RANK[required_level]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{required_level} access to portfolio {port_id} is required"
            ),
        )
    return granted_level


def get_portfolio_people(
    session: Session, port_ids: list[str]
) -> dict[str, dict[str, str | None]]:
    """Per-portfolio people, distinguishing two identities:

    - manager_name: the portfolio's business fund manager(s) from FSI master data
      (fsi.para_portfolio_manager → fsi.para_person), lead manager first.
    - manage_users: platform login accounts (iam.user) granted MANAGE access.
    """
    if not port_ids:
        return {}

    manager_rows = session.execute(
        text(
            """
            SELECT pm.port_id,
                   string_agg(pp.person_name, '、' ORDER BY pm.is_lead DESC, pp.person_name)
                     AS manager_name
            FROM fsi.para_portfolio_manager pm
            JOIN fsi.para_person pp
              ON pp.person_id = pm.person_id AND pp.is_active = TRUE
            WHERE pm.port_id = ANY(:ids)
              AND pm.end_date IS NULL
              AND pm.role IN ('FUND_MANAGER', 'DEPUTY_MANAGER')
            GROUP BY pm.port_id
            """
        ),
        {"ids": port_ids},
    ).mappings().all()

    manage_user_rows = session.execute(
        text(
            """
            SELECT a.port_id,
                   string_agg(COALESCE(NULLIF(u.full_name, ''), u.email), '、' ORDER BY u.email)
                     AS manage_users
            FROM iam.user_portfolio_access a
            JOIN iam."user" u ON u.id = a.user_id AND u.is_active = TRUE
            WHERE a.port_id = ANY(:ids) AND a.access_level = 'MANAGE'
            GROUP BY a.port_id
            """
        ),
        {"ids": port_ids},
    ).mappings().all()

    people: dict[str, dict[str, str | None]] = {
        pid: {"manager_name": None, "manage_users": None} for pid in port_ids
    }
    for row in manager_rows:
        people[str(row["port_id"])]["manager_name"] = row["manager_name"]
    for row in manage_user_rows:
        people[str(row["port_id"])]["manage_users"] = row["manage_users"]
    return people


def list_accessible_portfolios(session: Session, user: User) -> list[dict[str, object]]:
    """Return active portfolios visible to the user, including effective access."""
    if user.is_superuser:
        rows = session.execute(
            text(
                """
                SELECT port_id, port_name, port_name_en, port_type::text AS port_type,
                       base_currency, 'MANAGE' AS access_level
                FROM fsi.para_portfolio
                WHERE is_active = TRUE
                ORDER BY port_id
                """
            )
        ).mappings().all()
    else:
        if not has_global_permission(session, user, "portfolio.view"):
            return []
        rows = session.execute(
            text(
                """
                SELECT p.port_id, p.port_name, p.port_name_en,
                       p.port_type::text AS port_type, p.base_currency,
                       a.access_level
                FROM iam.user_portfolio_access a
                JOIN fsi.para_portfolio p ON p.port_id = a.port_id
                WHERE a.user_id = :user_id AND p.is_active = TRUE
                ORDER BY p.port_id
                """
            ),
            {"user_id": user.id},
        ).mappings().all()

    port_ids = [str(row["port_id"]) for row in rows]
    people = get_portfolio_people(session, port_ids)

    return [
        {
            "port_id": str(row["port_id"]),
            "port_name": str(row["port_name"]),
            "port_name_en": row["port_name_en"],
            "port_type": str(row["port_type"]),
            "base_currency": str(row["base_currency"]).strip(),
            "access_level": str(row["access_level"]),
            "manager_name": people.get(str(row["port_id"]), {}).get("manager_name"),
            "manage_users": people.get(str(row["port_id"]), {}).get("manage_users"),
        }
        for row in rows
    ]
