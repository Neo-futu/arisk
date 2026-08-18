"""IAM role/menu administration and portfolio-scoped access APIs."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import CurrentUser, SessionDep
from app.models import Message, User
from app.services.portfolio_access import (
    ensure_global_permission,
    get_portfolio_people,
    get_user_menu_paths,
    get_user_permission_codes,
    list_accessible_portfolios,
)

router = APIRouter(prefix="/access-control", tags=["Access Control"])


class PortfolioGrantInput(BaseModel):
    port_id: str = Field(min_length=1, max_length=16)
    access_level: Literal["VIEW", "MANAGE"]


class UserAccessUpdate(BaseModel):
    role_ids: list[uuid.UUID] = Field(default_factory=list)
    portfolios: list[PortfolioGrantInput] = Field(default_factory=list)


class RoleAccessUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    permission_ids: list[uuid.UUID] = Field(default_factory=list)
    menu_ids: list[uuid.UUID] = Field(default_factory=list)


class RoleCreateInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    description: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    permission_ids: list[uuid.UUID] = Field(default_factory=list)
    menu_ids: list[uuid.UUID] = Field(default_factory=list)


# Roles seeded by migration; they underpin platform behaviour and cannot be deleted.
BUILTIN_ROLE_CODES = {
    "PORTFOLIO_VIEWER",
    "INVESTMENT_DIRECTOR",
    "INVESTMENT_MANAGER",
    "SYSTEM_ADMIN",
}


def _ensure_access_admin(session: SessionDep, current_user: CurrentUser) -> None:
    ensure_global_permission(session, current_user, "iam.access.manage")


def _role_rows(session: SessionDep) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT r.id, r.name, r.code, r.description, r.is_active,
                   COALESCE(array_agg(DISTINCT rp.permission_id)
                     FILTER (WHERE rp.permission_id IS NOT NULL), '{}') AS permission_ids,
                   COALESCE(array_agg(DISTINCT rm.menu_id)
                     FILTER (WHERE rm.menu_id IS NOT NULL), '{}') AS menu_ids
            FROM iam.role r
            LEFT JOIN iam.role_permission rp ON rp.role_id = r.id
            LEFT JOIN iam.role_menu rm ON rm.role_id = r.id
            GROUP BY r.id, r.name, r.code, r.description, r.is_active
            ORDER BY r.name
            """
        )
    ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "code": row["code"],
            "description": row["description"],
            "is_active": bool(row["is_active"]),
            "permission_ids": [str(value) for value in row["permission_ids"]],
            "menu_ids": [str(value) for value in row["menu_ids"]],
        }
        for row in rows
    ]


@router.get("/me")
def read_my_access(session: SessionDep, current_user: CurrentUser) -> dict[str, Any]:
    role_rows = session.execute(
        text(
            """
            SELECT r.id, r.code, r.name
            FROM iam.user_role ur
            JOIN iam.role r ON r.id = ur.role_id AND r.is_active = TRUE
            WHERE ur.user_id = :user_id
            ORDER BY r.name
            """
        ),
        {"user_id": current_user.id},
    ).mappings().all()

    if current_user.is_superuser:
        permissions = {
            str(code)
            for code in session.execute(text("SELECT code FROM iam.permission")).scalars()
        }
        menu_rows = session.execute(
            text(
                """
                SELECT code, path FROM iam.menu
                WHERE is_active = TRUE
                ORDER BY sort_order, code
                """
            )
        ).mappings().all()
        menu_paths = {str(row["path"]) for row in menu_rows if row["path"]}
        menu_codes = [str(row["code"]) for row in menu_rows]
    else:
        permissions = get_user_permission_codes(session, current_user.id)
        menu_paths = get_user_menu_paths(session, current_user.id)
        menu_codes = [
            str(code)
            for code in session.execute(
                text(
                    """
                    SELECT DISTINCT m.code
                    FROM iam.user_role ur
                    JOIN iam.role r ON r.id = ur.role_id AND r.is_active = TRUE
                    JOIN iam.role_menu rm ON rm.role_id = r.id
                    JOIN iam.menu m ON m.id = rm.menu_id AND m.is_active = TRUE
                    WHERE ur.user_id = :user_id
                    ORDER BY m.code
                    """
                ),
                {"user_id": current_user.id},
            ).scalars()
        ]

    return {
        "user_id": str(current_user.id),
        "is_superuser": current_user.is_superuser,
        "roles": [
            {"id": str(row["id"]), "code": row["code"], "name": row["name"]}
            for row in role_rows
        ],
        "permission_codes": sorted(permissions),
        "menu_codes": menu_codes,
        "menu_paths": sorted(menu_paths),
        "portfolios": list_accessible_portfolios(session, current_user),
        "can_manage_access": bool(
            current_user.is_superuser or "iam.access.manage" in permissions
        ),
    }


@router.get("/catalog")
def read_access_catalog(
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    _ensure_access_admin(session, current_user)

    permissions = [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "code": row["code"],
            "description": row["description"],
        }
        for row in session.execute(
            text("SELECT id, name, code, description FROM iam.permission ORDER BY code")
        ).mappings().all()
    ]
    menus = [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "code": row["code"],
            "path": row["path"],
            "sort_order": int(row["sort_order"]),
            "is_active": bool(row["is_active"]),
        }
        for row in session.execute(
            text(
                """
                SELECT id, name, code, path, sort_order, is_active
                FROM iam.menu ORDER BY sort_order, code
                """
            )
        ).mappings().all()
    ]
    portfolio_rows = session.execute(
        text(
            """
            SELECT port_id, port_name, port_name_en, port_type::text AS port_type,
                   base_currency, is_active
            FROM fsi.para_portfolio ORDER BY is_active DESC, port_id
            """
        )
    ).mappings().all()
    people = get_portfolio_people(session, [str(row["port_id"]) for row in portfolio_rows])
    portfolios = [
        {
            "port_id": str(row["port_id"]),
            "port_name": row["port_name"],
            "port_name_en": row["port_name_en"],
            "port_type": str(row["port_type"]),
            "base_currency": str(row["base_currency"]).strip(),
            "is_active": bool(row["is_active"]),
            "manager_name": people.get(str(row["port_id"]), {}).get("manager_name"),
        }
        for row in portfolio_rows
    ]
    return {
        "roles": _role_rows(session),
        "permissions": permissions,
        "menus": menus,
        "portfolios": portfolios,
    }


@router.get("/grants")
def read_access_grants(
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """User → role → portfolio authorization matrix for the admin overview."""
    _ensure_access_admin(session, current_user)

    users = session.execute(
        text(
            """
            SELECT id, email, full_name, is_active, is_superuser
            FROM iam."user"
            ORDER BY is_superuser DESC, email
            """
        )
    ).mappings().all()

    role_rows = session.execute(
        text(
            """
            SELECT ur.user_id, r.id AS role_id, r.code, r.name
            FROM iam.user_role ur
            JOIN iam.role r ON r.id = ur.role_id AND r.is_active = TRUE
            ORDER BY r.name
            """
        )
    ).mappings().all()

    portfolio_rows = session.execute(
        text(
            """
            SELECT a.user_id, a.port_id, a.access_level, p.port_name
            FROM iam.user_portfolio_access a
            LEFT JOIN fsi.para_portfolio p ON p.port_id = a.port_id
            ORDER BY a.port_id
            """
        )
    ).mappings().all()

    roles_by_user: dict[str, list[dict[str, str]]] = {}
    for row in role_rows:
        roles_by_user.setdefault(str(row["user_id"]), []).append(
            {"id": str(row["role_id"]), "code": row["code"], "name": row["name"]}
        )

    portfolios_by_user: dict[str, list[dict[str, str | None]]] = {}
    for row in portfolio_rows:
        portfolios_by_user.setdefault(str(row["user_id"]), []).append(
            {
                "port_id": str(row["port_id"]),
                "port_name": row["port_name"],
                "access_level": str(row["access_level"]),
            }
        )

    return {
        "grants": [
            {
                "user_id": str(row["id"]),
                "email": row["email"],
                "full_name": row["full_name"],
                "is_active": bool(row["is_active"]),
                "is_superuser": bool(row["is_superuser"]),
                "roles": roles_by_user.get(str(row["id"]), []),
                "portfolios": portfolios_by_user.get(str(row["id"]), []),
            }
            for row in users
        ]
    }


@router.get("/users/{user_id}")
def read_user_access(
    user_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    _ensure_access_admin(session, current_user)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role_ids = [
        str(value)
        for value in session.execute(
            text("SELECT role_id FROM iam.user_role WHERE user_id = :user_id"),
            {"user_id": user_id},
        ).scalars()
    ]
    portfolio_rows = session.execute(
        text(
            """
            SELECT port_id, access_level
            FROM iam.user_portfolio_access
            WHERE user_id = :user_id
            ORDER BY port_id
            """
        ),
        {"user_id": user_id},
    ).mappings().all()
    return {
        "user_id": str(user_id),
        "role_ids": role_ids,
        "portfolios": [
            {"port_id": row["port_id"], "access_level": row["access_level"]}
            for row in portfolio_rows
        ],
    }


@router.put("/users/{user_id}")
def update_user_access(
    user_id: uuid.UUID,
    payload: UserAccessUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    _ensure_access_admin(session, current_user)
    target_user = session.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot change your own access grants")

    role_ids = list(dict.fromkeys(payload.role_ids))
    portfolio_grants = {grant.port_id: grant.access_level for grant in payload.portfolios}

    if role_ids:
        valid_role_ids = set(
            session.execute(
                text("SELECT id FROM iam.role WHERE id = ANY(:ids) AND is_active = TRUE"),
                {"ids": role_ids},
            ).scalars()
        )
        if valid_role_ids != set(role_ids):
            raise HTTPException(status_code=422, detail="One or more roles are invalid or inactive")

    permission_codes = set()
    if role_ids:
        permission_codes = {
            str(value)
            for value in session.execute(
                text(
                    """
                    SELECT DISTINCT p.code
                    FROM iam.role_permission rp
                    JOIN iam.permission p ON p.id = rp.permission_id
                    WHERE rp.role_id = ANY(:role_ids)
                    """
                ),
                {"role_ids": role_ids},
            ).scalars()
        }

    if portfolio_grants and "portfolio.view" not in permission_codes and not target_user.is_superuser:
        raise HTTPException(status_code=422, detail="Assigned roles must include portfolio.view")
    if (
        any(level == "MANAGE" for level in portfolio_grants.values())
        and not target_user.is_superuser
        and not {"portfolio.manage", "trade.manage"}.issubset(permission_codes)
    ):
        raise HTTPException(
            status_code=422,
            detail="MANAGE grants require a role with portfolio.manage and trade.manage",
        )

    if portfolio_grants:
        valid_ports = {
            str(value)
            for value in session.execute(
                text(
                    """
                    SELECT port_id FROM fsi.para_portfolio
                    WHERE port_id = ANY(:port_ids) AND is_active = TRUE
                    """
                ),
                {"port_ids": list(portfolio_grants)},
            ).scalars()
        }
        if valid_ports != set(portfolio_grants):
            raise HTTPException(status_code=422, detail="One or more portfolios are invalid or inactive")

    session.execute(text("DELETE FROM iam.user_role WHERE user_id = :user_id"), {"user_id": user_id})
    for role_id in role_ids:
        session.execute(
            text(
                """
                INSERT INTO iam.user_role (user_id, role_id, created_at)
                VALUES (:user_id, :role_id, NOW())
                """
            ),
            {"user_id": user_id, "role_id": role_id},
        )

    session.execute(
        text("DELETE FROM iam.user_portfolio_access WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    for port_id, access_level in portfolio_grants.items():
        session.execute(
            text(
                """
                INSERT INTO iam.user_portfolio_access
                  (user_id, port_id, access_level, granted_by, created_at, updated_at)
                VALUES (:user_id, :port_id, :access_level, :granted_by, NOW(), NOW())
                """
            ),
            {
                "user_id": user_id,
                "port_id": port_id,
                "access_level": access_level,
                "granted_by": current_user.id,
            },
        )
    session.commit()
    return read_user_access(user_id, session, current_user)


@router.put("/roles/{role_id}")
def update_role_access(
    role_id: uuid.UUID,
    payload: RoleAccessUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    ensure_global_permission(session, current_user, "iam.role.manage")
    role = session.execute(
        text("SELECT id, code FROM iam.role WHERE id = :role_id"),
        {"role_id": role_id},
    ).mappings().first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    permission_ids = list(dict.fromkeys(payload.permission_ids))
    menu_ids = list(dict.fromkeys(payload.menu_ids))
    if permission_ids:
        valid_permission_ids = set(
            session.execute(
                text("SELECT id FROM iam.permission WHERE id = ANY(:ids)"),
                {"ids": permission_ids},
            ).scalars()
        )
        if valid_permission_ids != set(permission_ids):
            raise HTTPException(status_code=422, detail="One or more permissions are invalid")
    if menu_ids:
        valid_menu_ids = set(
            session.execute(
                text("SELECT id FROM iam.menu WHERE id = ANY(:ids)"),
                {"ids": menu_ids},
            ).scalars()
        )
        if valid_menu_ids != set(menu_ids):
            raise HTTPException(status_code=422, detail="One or more menus are invalid")

    if role["code"] == "SYSTEM_ADMIN":
        required_codes = {"iam.access.manage", "iam.role.manage"}
        selected_codes = {
            str(value)
            for value in session.execute(
                text("SELECT code FROM iam.permission WHERE id = ANY(:ids)"),
                {"ids": permission_ids},
            ).scalars()
        } if permission_ids else set()
        if not required_codes.issubset(selected_codes):
            raise HTTPException(
                status_code=422,
                detail="SYSTEM_ADMIN must retain iam.access.manage and iam.role.manage",
            )

    session.execute(
        text(
            """
            UPDATE iam.role
            SET name = :name, description = :description, is_active = :is_active
            WHERE id = :role_id
            """
        ),
        {
            "name": payload.name,
            "description": payload.description,
            "is_active": payload.is_active,
            "role_id": role_id,
        },
    )
    session.execute(text("DELETE FROM iam.role_permission WHERE role_id = :role_id"), {"role_id": role_id})
    session.execute(text("DELETE FROM iam.role_menu WHERE role_id = :role_id"), {"role_id": role_id})
    for permission_id in permission_ids:
        session.execute(
            text("INSERT INTO iam.role_permission (role_id, permission_id, created_at) VALUES (:role_id, :permission_id, NOW())"),
            {"role_id": role_id, "permission_id": permission_id},
        )
    for menu_id in menu_ids:
        session.execute(
            text("INSERT INTO iam.role_menu (role_id, menu_id, created_at) VALUES (:role_id, :menu_id, NOW())"),
            {"role_id": role_id, "menu_id": menu_id},
        )
    session.commit()

    updated = next((item for item in _role_rows(session) if item["id"] == str(role_id)), None)
    if updated is None:
        raise HTTPException(status_code=404, detail="Role not found after update")
    return updated


def _validate_permission_menu_ids(
    session: SessionDep,
    permission_ids: list[uuid.UUID],
    menu_ids: list[uuid.UUID],
) -> None:
    if permission_ids:
        valid = set(
            session.execute(
                text("SELECT id FROM iam.permission WHERE id = ANY(:ids)"),
                {"ids": permission_ids},
            ).scalars()
        )
        if valid != set(permission_ids):
            raise HTTPException(status_code=422, detail="One or more permissions are invalid")
    if menu_ids:
        valid = set(
            session.execute(
                text("SELECT id FROM iam.menu WHERE id = ANY(:ids)"),
                {"ids": menu_ids},
            ).scalars()
        )
        if valid != set(menu_ids):
            raise HTTPException(status_code=422, detail="One or more menus are invalid")


@router.post("/roles", status_code=201)
def create_role(
    payload: RoleCreateInput,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    ensure_global_permission(session, current_user, "iam.role.manage")

    code = payload.code.strip().upper()
    if code in BUILTIN_ROLE_CODES:
        raise HTTPException(status_code=422, detail="This role code is reserved for a built-in role")
    existing = session.execute(
        text("SELECT 1 FROM iam.role WHERE code = :code OR name = :name"),
        {"code": code, "name": payload.name},
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="A role with this name or code already exists")

    permission_ids = list(dict.fromkeys(payload.permission_ids))
    menu_ids = list(dict.fromkeys(payload.menu_ids))
    _validate_permission_menu_ids(session, permission_ids, menu_ids)

    role_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO iam.role (id, name, code, description, is_active, created_at)
            VALUES (:id, :name, :code, :description, :is_active, NOW())
            """
        ),
        {
            "id": role_id,
            "name": payload.name,
            "code": code,
            "description": payload.description,
            "is_active": payload.is_active,
        },
    )
    for permission_id in permission_ids:
        session.execute(
            text("INSERT INTO iam.role_permission (role_id, permission_id, created_at) VALUES (:role_id, :permission_id, NOW())"),
            {"role_id": role_id, "permission_id": permission_id},
        )
    for menu_id in menu_ids:
        session.execute(
            text("INSERT INTO iam.role_menu (role_id, menu_id, created_at) VALUES (:role_id, :menu_id, NOW())"),
            {"role_id": role_id, "menu_id": menu_id},
        )
    session.commit()

    created = next((item for item in _role_rows(session) if item["id"] == str(role_id)), None)
    if created is None:
        raise HTTPException(status_code=500, detail="Role not found after creation")
    return created


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Message:
    ensure_global_permission(session, current_user, "iam.role.manage")
    role = session.execute(
        text("SELECT code FROM iam.role WHERE id = :role_id"),
        {"role_id": role_id},
    ).mappings().first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role["code"] in BUILTIN_ROLE_CODES:
        raise HTTPException(status_code=422, detail="Built-in roles cannot be deleted")

    assigned = session.execute(
        text("SELECT COUNT(*) FROM iam.user_role WHERE role_id = :role_id"),
        {"role_id": role_id},
    ).scalar_one()
    if assigned:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete a role still assigned to {assigned} user(s); revoke it first",
        )

    session.execute(text("DELETE FROM iam.role_permission WHERE role_id = :role_id"), {"role_id": role_id})
    session.execute(text("DELETE FROM iam.role_menu WHERE role_id = :role_id"), {"role_id": role_id})
    session.execute(text("DELETE FROM iam.role WHERE id = :role_id"), {"role_id": role_id})
    session.commit()
    return Message(message="Role deleted")
