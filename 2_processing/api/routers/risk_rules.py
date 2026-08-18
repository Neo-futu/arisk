"""Unified CRUD API for regulatory, contract and internal risk rules."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])
RuleType = Literal["regulatory", "contract", "internal"]
LimitDirection = Literal["MIN", "MAX"]
ApplyScope = Literal["portfolio", "trade", "pretrade", "posttrade"]


class RiskRuleCreate(BaseModel):
    rule_type: RuleType
    port_id: str = Field(min_length=1, max_length=16)
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=64)
    dimension: str = Field(min_length=1, max_length=32)
    dimension_key: str | None = Field(default=None, max_length=64)
    lower_limit: float | None = None
    upper_limit: float | None = None
    limit_unit: str = Field(default="PCT", min_length=1, max_length=16)
    limit_direction: LimitDirection | None = None
    clause_ref: str | None = Field(default=None, max_length=128)
    mandate_ref: str | None = Field(default=None, max_length=64)
    client_name: str | None = Field(default=None, max_length=200)
    breach_action: str | None = Field(default=None, max_length=128)
    alert_pct: float | None = Field(default=90, ge=0, le=100)
    is_hard: bool = True
    effective_date: date
    expiry_date: date | None = None
    is_active: bool = True
    description: str | None = None
    created_by: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_rule(self) -> "RiskRuleCreate":
        self.code = self.code.strip().upper()
        self.port_id = self.port_id.strip()
        self.name = self.name.strip()
        if self.expiry_date and self.expiry_date < self.effective_date:
            raise ValueError("expiry_date must not be earlier than effective_date")
        if self.rule_type == "regulatory":
            if not self.source:
                raise ValueError("source is required for regulatory rules")
            if not self.limit_direction:
                raise ValueError("limit_direction is required for regulatory rules")
            value = self.upper_limit if self.limit_direction == "MAX" else self.lower_limit
            if value is None:
                raise ValueError("regulatory rule requires the limit matching its direction")
        elif self.rule_type == "internal":
            if not self.category:
                raise ValueError("category is required for internal rules")
            if self.lower_limit is None and self.upper_limit is None:
                raise ValueError("internal rule requires a lower or upper limit")
        else:
            if not self.mandate_ref:
                raise ValueError("mandate_ref is required for contract rules")
            if self.lower_limit is None and self.upper_limit is None:
                raise ValueError("contract rule requires a lower or upper limit")
        return self


class RiskRuleUpdate(BaseModel):
    port_id: str | None = Field(default=None, min_length=1, max_length=16)
    code: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=64)
    dimension: str | None = Field(default=None, min_length=1, max_length=32)
    dimension_key: str | None = Field(default=None, max_length=64)
    lower_limit: float | None = None
    upper_limit: float | None = None
    limit_unit: str | None = Field(default=None, min_length=1, max_length=16)
    limit_direction: LimitDirection | None = None
    clause_ref: str | None = Field(default=None, max_length=128)
    mandate_ref: str | None = Field(default=None, max_length=64)
    client_name: str | None = Field(default=None, max_length=200)
    breach_action: str | None = Field(default=None, max_length=128)
    alert_pct: float | None = Field(default=None, ge=0, le=100)
    is_hard: bool | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    is_active: bool | None = None
    description: str | None = None
    updated_by: str | None = Field(default=None, max_length=64)


class RuleApplicationCreate(BaseModel):
    rule_type: RuleType
    rule_id: int = Field(gt=0)
    apply_scope: ApplyScope
    port_id: str | None = Field(default=None, max_length=16)
    strategy_code: str | None = Field(default=None, max_length=64)
    instrument_type: str | None = Field(default=None, max_length=32)
    trade_side: Literal["BUY", "SELL", "BOTH"] | None = None
    priority: int = Field(default=100, ge=1, le=1000)
    effective_date: date
    expiry_date: date | None = None
    is_active: bool = True
    note: str | None = None
    created_by: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_application(self) -> "RuleApplicationCreate":
        if self.expiry_date and self.expiry_date < self.effective_date:
            raise ValueError("expiry_date must not be earlier than effective_date")
        if self.apply_scope == "portfolio" and not self.port_id:
            raise ValueError("port_id is required for portfolio scope")
        if self.apply_scope in {"trade", "pretrade", "posttrade"}:
            if not self.port_id and not self.strategy_code and not self.instrument_type:
                raise ValueError("trade-like scope requires port_id, strategy_code or instrument_type")
        return self


class RuleApplicationUpdate(BaseModel):
    apply_scope: ApplyScope | None = None
    port_id: str | None = Field(default=None, max_length=16)
    strategy_code: str | None = Field(default=None, max_length=64)
    instrument_type: str | None = Field(default=None, max_length=32)
    trade_side: Literal["BUY", "SELL", "BOTH"] | None = None
    priority: int | None = Field(default=None, ge=1, le=1000)
    effective_date: date | None = None
    expiry_date: date | None = None
    is_active: bool | None = None
    note: str | None = None
    updated_by: str | None = Field(default=None, max_length=64)


_RULE_UNION = """
SELECT limit_id AS id, 'regulatory'::text AS rule_type,
       port_id, rule_code AS code, rule_name AS name, rule_name_en AS name_en,
       regulation_src AS category, regulation_src AS source,
       dimension, dimension_key,
       CASE WHEN limit_direction = 'MIN' THEN limit_value END AS lower_limit,
       CASE WHEN limit_direction = 'MAX' THEN limit_value END AS upper_limit,
       limit_unit, limit_direction, clause_ref,
       NULL::varchar AS mandate_ref, NULL::varchar AS client_name,
       NULL::varchar AS breach_action, NULL::numeric AS alert_pct,
       TRUE AS is_hard, effective_date, expiry_date,
    is_active, description, created_by, updated_by, created_at, updated_at,
    (SELECT COUNT(*) FROM fsi.para_risk_rule_attachment a WHERE a.rule_type='regulatory' AND a.rule_id=limit_id) AS attachment_count
FROM fsi.para_risk_limit_regulatory
UNION ALL
SELECT limit_id, 'contract'::text,
       port_id, rule_code, rule_name, rule_name_en,
       'CONTRACT'::varchar, mandate_ref,
       dimension, dimension_key, lower_limit, upper_limit,
       limit_unit,
       CASE WHEN upper_limit IS NOT NULL AND lower_limit IS NULL THEN 'MAX'
            WHEN lower_limit IS NOT NULL AND upper_limit IS NULL THEN 'MIN'
            ELSE NULL END,
       clause_ref, mandate_ref, client_name, breach_action,
       NULL::numeric, TRUE, begin_date, end_date,
    is_active, description, created_by, updated_by, created_at, updated_at,
    (SELECT COUNT(*) FROM fsi.para_risk_rule_attachment a WHERE a.rule_type='contract' AND a.rule_id=limit_id) AS attachment_count
FROM fsi.para_risk_limit_contract
UNION ALL
SELECT limit_id, 'internal'::text,
       port_id, limit_code, limit_name, limit_name_en,
       limit_category, 'INTERNAL'::varchar,
       dimension, dimension_key, lower_limit, upper_limit,
       limit_unit,
       CASE WHEN upper_limit IS NOT NULL AND lower_limit IS NULL THEN 'MAX'
            WHEN lower_limit IS NOT NULL AND upper_limit IS NULL THEN 'MIN'
            ELSE NULL END,
       NULL::varchar, NULL::varchar, NULL::varchar, NULL::varchar,
       alert_pct, is_hard, begin_date, end_date,
       is_active, description, created_by, updated_by, created_at, updated_at,
       (SELECT COUNT(*) FROM fsi.para_risk_rule_attachment a WHERE a.rule_type='internal' AND a.rule_id=limit_id) AS attachment_count
FROM fsi.para_risk_limit_internal
"""


def _allowed_attachment(file_name: str, content_type: str | None) -> bool:
    allowed_types = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    }
    lower_name = file_name.lower()
    allowed_ext = (".pdf", ".doc", ".docx", ".txt")
    return (content_type in allowed_types) or lower_name.endswith(allowed_ext)


def _attachment_dict(row: Any) -> dict[str, Any]:
    return {
        "id": int(row.attachment_id),
        "rule_type": str(row.rule_type),
        "rule_id": int(row.rule_id),
        "file_name": str(row.file_name),
        "content_type": str(row.content_type),
        "file_size": int(row.file_size),
        "note": row.note,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _as_dict(row: Any) -> dict[str, Any]:
    return {
        key: float(value) if isinstance(value, Decimal) else value
        for key, value in row._mapping.items()
    }


async def _get_rule(db: AsyncSession, rule_type: RuleType, rule_id: int) -> dict[str, Any]:
    row = (
        await db.execute(
            text(f"SELECT * FROM ({_RULE_UNION}) rules WHERE rule_type = :rt AND id = :rid"),
            {"rt": rule_type, "rid": rule_id},
        )
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Risk rule not found")
    return _as_dict(row)


@router.get("/", summary="统一查询三类风控规则")
async def list_risk_rules(
    rule_type: RuleType | None = None,
    fund_id: str | None = None,
    active_only: bool = False,
    search: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    params = {
        "rule_type": rule_type,
        "fund_id": fund_id,
        "active_only": active_only,
        "search": f"%{search.strip()}%" if search and search.strip() else None,
        "skip": skip,
        "limit": limit,
    }
    where = """
      WHERE (CAST(:rule_type AS text) IS NULL OR rule_type = CAST(:rule_type AS text))
        AND (CAST(:fund_id AS text) IS NULL OR port_id = CAST(:fund_id AS text))
        AND (:active_only = FALSE OR is_active = TRUE)
                AND (CAST(:search AS text) IS NULL OR code ILIKE CAST(:search AS text) OR name ILIKE CAST(:search AS text) OR COALESCE(name_en, '') ILIKE CAST(:search AS text))
    """
    count = (
        await db.execute(text(f"SELECT COUNT(*) FROM ({_RULE_UNION}) rules {where}"), params)
    ).scalar_one()
    rows = (
        await db.execute(
            text(
                f"SELECT * FROM ({_RULE_UNION}) rules {where} "
                "ORDER BY is_active DESC, rule_type, port_id, code, effective_date DESC "
                "OFFSET :skip LIMIT :limit"
            ),
            params,
        )
    ).fetchall()
    return {"items": [_as_dict(row) for row in rows], "count": int(count)}


@router.get("/summary", summary="风控规则分类统计")
async def risk_rule_summary(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                f"SELECT rule_type, COUNT(*) AS total, "
                f"SUM(CASE WHEN is_active THEN 1 ELSE 0 END) AS active "
                f"FROM ({_RULE_UNION}) rules GROUP BY rule_type ORDER BY rule_type"
            )
        )
    ).fetchall()
    by_type = {str(row.rule_type): {"total": int(row.total), "active": int(row.active or 0)} for row in rows}
    return {
        "by_type": by_type,
        "total": sum(item["total"] for item in by_type.values()),
        "active": sum(item["active"] for item in by_type.values()),
    }


@router.get("/{rule_type}/{rule_id}", summary="查询单条风控规则")
async def get_risk_rule(
    rule_type: RuleType,
    rule_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _get_rule(db, rule_type, rule_id)


@router.post("/", status_code=status.HTTP_201_CREATED, summary="创建风控规则")
async def create_risk_rule(
    payload: RiskRuleCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = payload.model_dump()
    try:
        if payload.rule_type == "regulatory":
            limit_value = payload.upper_limit if payload.limit_direction == "MAX" else payload.lower_limit
            rule_id = (
                await db.execute(
                    text(
                        """
                        INSERT INTO fsi.para_risk_limit_regulatory
                          (port_id, regulation_src, rule_code, rule_name, rule_name_en,
                           dimension, dimension_key, limit_value, limit_unit, limit_direction,
                           clause_ref, effective_date, expiry_date, is_active, description, created_by)
                        VALUES
                          (:port_id, :source, :code, :name, :name_en,
                           :dimension, :dimension_key, :limit_value, :limit_unit, :limit_direction,
                           :clause_ref, :effective_date, :expiry_date, :is_active, :description, :created_by)
                        RETURNING limit_id
                        """
                    ),
                    {**values, "limit_value": limit_value},
                )
            ).scalar_one()
        elif payload.rule_type == "contract":
            rule_id = (
                await db.execute(
                    text(
                        """
                        INSERT INTO fsi.para_risk_limit_contract
                          (port_id, rule_code, rule_name, rule_name_en, mandate_ref, clause_ref,
                           client_name, dimension, dimension_key, lower_limit, upper_limit,
                           limit_unit, breach_action, begin_date, end_date, is_active,
                           description, created_by)
                        VALUES
                          (:port_id, :code, :name, :name_en, :mandate_ref, :clause_ref,
                           :client_name, :dimension, :dimension_key, :lower_limit, :upper_limit,
                           :limit_unit, :breach_action, :effective_date, :expiry_date, :is_active,
                           :description, :created_by)
                        RETURNING limit_id
                        """
                    ),
                    values,
                )
            ).scalar_one()
        else:
            rule_id = (
                await db.execute(
                    text(
                        """
                        INSERT INTO fsi.para_risk_limit_internal
                          (port_id, limit_code, limit_name, limit_name_en, limit_category,
                           dimension, dimension_key, lower_limit, upper_limit, limit_unit,
                           alert_pct, is_hard, begin_date, end_date, is_active,
                           description, created_by)
                        VALUES
                          (:port_id, :code, :name, :name_en, :category,
                           :dimension, :dimension_key, :lower_limit, :upper_limit, :limit_unit,
                           :alert_pct, :is_hard, :effective_date, :expiry_date, :is_active,
                           :description, :created_by)
                        RETURNING limit_id
                        """
                    ),
                    values,
                )
            ).scalar_one()
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate or invalid risk rule") from exc
    return await _get_rule(db, payload.rule_type, int(rule_id))


def _merged_rule(existing: dict[str, Any], patch: RiskRuleUpdate) -> RiskRuleCreate:
    changes = patch.model_dump(exclude_unset=True)
    base = {
        key: existing.get(key)
        for key in RiskRuleCreate.model_fields
        if key not in {"created_by"}
    }
    base["rule_type"] = existing["rule_type"]
    base.update({key: value for key, value in changes.items() if key != "updated_by"})
    base["created_by"] = existing.get("created_by")
    return RiskRuleCreate.model_validate(base)


@router.patch("/{rule_type}/{rule_id}", summary="更新风控规则")
async def update_risk_rule(
    rule_type: RuleType,
    rule_id: int,
    patch: RiskRuleUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    existing = await _get_rule(db, rule_type, rule_id)
    payload = _merged_rule(existing, patch)
    values = payload.model_dump()
    values.update({"rule_id": rule_id, "updated_by": patch.updated_by})
    try:
        if rule_type == "regulatory":
            values["limit_value"] = payload.upper_limit if payload.limit_direction == "MAX" else payload.lower_limit
            sql = """
                UPDATE fsi.para_risk_limit_regulatory SET
                  port_id=:port_id, regulation_src=:source, rule_code=:code,
                  rule_name=:name, rule_name_en=:name_en, dimension=:dimension,
                  dimension_key=:dimension_key, limit_value=:limit_value,
                  limit_unit=:limit_unit, limit_direction=:limit_direction,
                  clause_ref=:clause_ref, effective_date=:effective_date,
                  expiry_date=:expiry_date, is_active=:is_active,
                  description=:description, updated_by=:updated_by, updated_at=NOW()
                WHERE limit_id=:rule_id
            """
        elif rule_type == "contract":
            sql = """
                UPDATE fsi.para_risk_limit_contract SET
                  port_id=:port_id, rule_code=:code, rule_name=:name,
                  rule_name_en=:name_en, mandate_ref=:mandate_ref,
                  clause_ref=:clause_ref, client_name=:client_name,
                  dimension=:dimension, dimension_key=:dimension_key,
                  lower_limit=:lower_limit, upper_limit=:upper_limit,
                  limit_unit=:limit_unit, breach_action=:breach_action,
                  begin_date=:effective_date, end_date=:expiry_date,
                  is_active=:is_active, description=:description,
                  updated_by=:updated_by, updated_at=NOW()
                WHERE limit_id=:rule_id
            """
        else:
            sql = """
                UPDATE fsi.para_risk_limit_internal SET
                  port_id=:port_id, limit_code=:code, limit_name=:name,
                  limit_name_en=:name_en, limit_category=:category,
                  dimension=:dimension, dimension_key=:dimension_key,
                  lower_limit=:lower_limit, upper_limit=:upper_limit,
                  limit_unit=:limit_unit, alert_pct=:alert_pct, is_hard=:is_hard,
                  begin_date=:effective_date, end_date=:expiry_date,
                  is_active=:is_active, description=:description,
                  updated_by=:updated_by, updated_at=NOW()
                WHERE limit_id=:rule_id
            """
        await db.execute(text(sql), values)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate or invalid risk rule") from exc
    return await _get_rule(db, rule_type, rule_id)


@router.delete("/{rule_type}/{rule_id}", summary="停用风控规则")
async def deactivate_risk_rule(
    rule_type: RuleType,
    rule_id: int,
    updated_by: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _get_rule(db, rule_type, rule_id)
    table = {
        "regulatory": "fsi.para_risk_limit_regulatory",
        "contract": "fsi.para_risk_limit_contract",
        "internal": "fsi.para_risk_limit_internal",
    }[rule_type]
    await db.execute(
        text(f"UPDATE {table} SET is_active=FALSE, updated_by=:updated_by, updated_at=NOW() WHERE limit_id=:rid"),
        {"updated_by": updated_by, "rid": rule_id},
    )
    await db.commit()
    return await _get_rule(db, rule_type, rule_id)


@router.get("/{rule_type}/{rule_id}/attachments", summary="查询规则附件")
async def list_risk_rule_attachments(
    rule_type: RuleType,
    rule_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _get_rule(db, rule_type, rule_id)
    rows = (
        await db.execute(
            text(
                """
                SELECT attachment_id, rule_type, rule_id, file_name, content_type, file_size,
                       note, created_by, created_at, updated_at
                FROM fsi.para_risk_rule_attachment
                WHERE rule_type = :rt AND rule_id = :rid
                ORDER BY created_at DESC, attachment_id DESC
                """
            ),
            {"rt": rule_type, "rid": rule_id},
        )
    ).fetchall()
    return {"items": [_attachment_dict(row) for row in rows], "count": len(rows)}


@router.post("/{rule_type}/{rule_id}/attachments", summary="上传规则附件", status_code=status.HTTP_201_CREATED)
async def upload_risk_rule_attachment(
    rule_type: RuleType,
    rule_id: int,
    file: UploadFile = File(...),
    note: str | None = Form(default=None),
    created_by: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _get_rule(db, rule_type, rule_id)
    file_name = (file.filename or "uploaded").strip()
    payload = await file.read()
    content_type = file.content_type or "application/octet-stream"

    if not payload:
        raise HTTPException(status_code=400, detail="Attachment is empty")
    if len(payload) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Attachment size exceeds 10MB")
    if not _allowed_attachment(file_name, content_type):
        raise HTTPException(status_code=415, detail="Only PDF, DOC, DOCX or TXT are allowed")

    row = (
        await db.execute(
            text(
                """
                INSERT INTO fsi.para_risk_rule_attachment
                  (rule_type, rule_id, file_name, content_type, file_size, file_data, note, created_by)
                VALUES
                  (:rt, :rid, :fn, :ct, :size, :data, :note, :created_by)
                RETURNING attachment_id, rule_type, rule_id, file_name, content_type, file_size,
                          note, created_by, created_at, updated_at
                """
            ),
            {
                "rt": rule_type,
                "rid": rule_id,
                "fn": file_name,
                "ct": content_type,
                "size": len(payload),
                "data": payload,
                "note": note,
                "created_by": created_by,
            },
        )
    ).fetchone()
    await db.commit()
    return _attachment_dict(row)


@router.get("/attachment-files/{attachment_id}/download", summary="下载规则附件")
async def download_risk_rule_attachment(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = (
        await db.execute(
            text(
                """
                SELECT file_name, content_type, file_data
                FROM fsi.para_risk_rule_attachment
                WHERE attachment_id = :aid
                """
            ),
            {"aid": attachment_id},
        )
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    headers = {"Content-Disposition": f'attachment; filename="{row.file_name}"'}
    return Response(content=bytes(row.file_data), media_type=str(row.content_type), headers=headers)


@router.delete("/attachment-files/{attachment_id}", summary="删除规则附件")
async def delete_risk_rule_attachment(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                DELETE FROM fsi.para_risk_rule_attachment
                WHERE attachment_id = :aid
                RETURNING attachment_id
                """
            ),
            {"aid": attachment_id},
        )
    ).fetchone()
    await db.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return {"ok": True, "attachment_id": int(row.attachment_id)}


@router.post("/regulatory/bootstrap", summary="补齐SFC监管基线规则")
async def bootstrap_regulatory_rules(
    effective_date: date = Query(default=date(2024, 1, 1)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    inserted = (
        await db.execute(
            text(
                """
                WITH ins AS (
                    INSERT INTO fsi.para_risk_limit_regulatory
                        (port_id, regulation_src, rule_code, rule_name, rule_name_en,
                         dimension, limit_value, limit_unit, limit_direction,
                         clause_ref, effective_date, is_active, description)
                    SELECT p.port_id, r.regulation_src, r.rule_code, r.rule_name, r.rule_name_en,
                           r.dimension, r.limit_value, r.limit_unit, r.limit_direction,
                           r.clause_ref, :effective_date, TRUE, r.description
                    FROM fsi.para_portfolio p
                    CROSS JOIN (
                        VALUES
                          ('SFC_MMF_CODE', 'MMF_WAM', '加權平均期限', 'Weighted Average Maturity', 'WAM', 60.0, 'DAYS', 'MAX', 'SFC UT Code 8.2', 'WAM 不得超過 60 天'),
                          ('SFC_MMF_CODE', 'MMF_WAL', '加權平均有效期', 'Weighted Average Life', 'WAL', 120.0, 'DAYS', 'MAX', 'SFC UT Code 8.2', 'WAL 不得超過 120 天'),
                          ('SFC_MMF_CODE', 'MMF_DAILY_LIQUID', '每日流動資產', 'Daily Liquid Assets', 'LIQUIDITY', 7.5, 'PCT', 'MIN', 'SFC UT Code 8.2', '每日流動資產不得低於 7.5% NAV'),
                          ('SFC_MMF_CODE', 'MMF_WEEKLY_LIQUID', '每週流動資產', 'Weekly Liquid Assets', 'LIQUIDITY', 15.0, 'PCT', 'MIN', 'SFC UT Code 8.2', '每週流動資產不得低於 15% NAV'),
                          ('SFC_MMF_CODE', 'MMF_SINGLE_ISSUER', '單一發行人集中度', 'Single Issuer Concentration', 'ISSUER', 10.0, 'PCT', 'MAX', 'SFC UT Code 8.2', '單一發行人暴露不得超過 10% NAV'),
                          ('SFC_MMF_CODE', 'MMF_ISSUER_GROUP', '發行人集團集中度', 'Issuer Group Concentration', 'ISSUER_GROUP', 20.0, 'PCT', 'MAX', 'SFC UT Code 8.2', '同一集團暴露不得超過 20% NAV')
                    ) AS r(regulation_src, rule_code, rule_name, rule_name_en, dimension,
                           limit_value, limit_unit, limit_direction, clause_ref, description)
                    WHERE p.is_active = TRUE
                    ON CONFLICT (port_id, rule_code, effective_date) DO NOTHING
                    RETURNING 1
                )
                SELECT COUNT(*) AS inserted_count FROM ins
                """
            ),
            {"effective_date": effective_date},
        )
    ).scalar_one()

    total = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fsi.para_risk_limit_regulatory
                WHERE regulation_src = 'SFC_MMF_CODE' AND is_active = TRUE
                """
            )
        )
    ).scalar_one()

    return {
        "inserted": int(inserted),
        "active_regulatory_total": int(total),
        "effective_date": str(effective_date),
    }


@router.get("/regulatory-brief", summary="监管规则简要列表")
async def regulatory_brief(
    fund_id: str | None = None,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    rule_code AS code,
                    MIN(rule_name) AS name,
                    MIN(rule_name_en) AS name_en,
                    MIN(dimension) AS dimension,
                    MIN(limit_unit) AS limit_unit,
                    MIN(clause_ref) AS clause_ref,
                    MIN(description) AS description,
                    SUM(CASE WHEN is_active THEN 1 ELSE 0 END) AS active_count,
                    COUNT(*) AS total_count,
                    CASE
                        WHEN MAX(CASE WHEN limit_direction='MAX' THEN limit_value END) IS NOT NULL
                             AND MAX(CASE WHEN limit_direction='MIN' THEN limit_value END) IS NOT NULL
                            THEN CONCAT(
                                MAX(CASE WHEN limit_direction='MIN' THEN limit_value END),
                                ' <= x <= ',
                                MAX(CASE WHEN limit_direction='MAX' THEN limit_value END),
                                ' ', MIN(limit_unit)
                            )
                        WHEN MAX(CASE WHEN limit_direction='MAX' THEN limit_value END) IS NOT NULL
                            THEN CONCAT('<= ', MAX(CASE WHEN limit_direction='MAX' THEN limit_value END), ' ', MIN(limit_unit))
                        WHEN MAX(CASE WHEN limit_direction='MIN' THEN limit_value END) IS NOT NULL
                            THEN CONCAT('>= ', MAX(CASE WHEN limit_direction='MIN' THEN limit_value END), ' ', MIN(limit_unit))
                        ELSE '-'
                    END AS limit_brief
                FROM fsi.para_risk_limit_regulatory
                WHERE regulation_src = 'SFC_MMF_CODE'
                  AND (CAST(:fund_id AS text) IS NULL OR port_id = CAST(:fund_id AS text))
                  AND (:active_only = FALSE OR is_active = TRUE)
                GROUP BY rule_code
                ORDER BY rule_code
                """
            ),
            {"fund_id": fund_id, "active_only": active_only},
        )
    ).mappings().all()

    return {"items": [dict(row) for row in rows], "count": len(rows)}


@router.get("/applications", summary="规则应用配置列表")
async def list_rule_applications(
    apply_scope: ApplyScope | None = None,
    fund_id: str | None = None,
    active_only: bool = True,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    where = """
      WHERE (CAST(:apply_scope AS text) IS NULL OR app.apply_scope = CAST(:apply_scope AS text))
        AND (CAST(:fund_id AS text) IS NULL OR app.port_id = CAST(:fund_id AS text))
        AND (:active_only = FALSE OR app.is_active = TRUE)
    """
    params = {
        "apply_scope": apply_scope,
        "fund_id": fund_id,
        "active_only": active_only,
        "skip": skip,
        "limit": limit,
    }
    from_sql = f"""
        FROM fsi.para_risk_rule_application app
        LEFT JOIN ({_RULE_UNION}) rules
          ON app.rule_type = rules.rule_type AND app.rule_id = rules.id
        {where}
    """
    count = (await db.execute(text(f"SELECT COUNT(*) {from_sql}"), params)).scalar_one()
    rows = (
        await db.execute(
            text(
                f"""
                SELECT app.application_id, app.rule_type, app.rule_id, app.apply_scope,
                       app.port_id, app.strategy_code, app.instrument_type, app.trade_side,
                       app.priority, app.effective_date, app.expiry_date, app.is_active,
                       app.note, app.created_by, app.updated_by, app.created_at, app.updated_at,
                       rules.code AS rule_code, rules.name AS rule_name, rules.name_en AS rule_name_en
                {from_sql}
                ORDER BY app.is_active DESC, app.priority ASC, app.effective_date DESC, app.application_id DESC
                OFFSET :skip LIMIT :limit
                """
            ),
            params,
        )
    ).mappings().all()
    return {"items": [dict(row) for row in rows], "count": int(count)}


@router.post("/applications", summary="创建规则应用配置", status_code=status.HTTP_201_CREATED)
async def create_rule_application(
    payload: RuleApplicationCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _get_rule(db, payload.rule_type, payload.rule_id)
    row = (
        await db.execute(
            text(
                """
                INSERT INTO fsi.para_risk_rule_application
                  (rule_type, rule_id, apply_scope, port_id, strategy_code, instrument_type,
                   trade_side, priority, effective_date, expiry_date, is_active, note, created_by)
                VALUES
                  (:rule_type, :rule_id, :apply_scope, :port_id, :strategy_code, :instrument_type,
                   :trade_side, :priority, :effective_date, :expiry_date, :is_active, :note, :created_by)
                RETURNING application_id
                """
            ),
            payload.model_dump(),
        )
    ).fetchone()
    await db.commit()
    app_id = int(row.application_id)
    created = (
        await db.execute(
            text(
                """
                SELECT application_id, rule_type, rule_id, apply_scope,
                       port_id, strategy_code, instrument_type, trade_side,
                       priority, effective_date, expiry_date, is_active,
                       note, created_by, updated_by, created_at, updated_at
                FROM fsi.para_risk_rule_application
                WHERE application_id = :aid
                """
            ),
            {"aid": app_id},
        )
    ).mappings().one()
    return dict(created)


@router.patch("/applications/item/{application_id}", summary="更新规则应用配置")
async def update_rule_application(
    application_id: int,
    patch: RuleApplicationUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    existing = (
        await db.execute(
            text("SELECT * FROM fsi.para_risk_rule_application WHERE application_id=:aid"),
            {"aid": application_id},
        )
    ).mappings().first()
    if not existing:
        raise HTTPException(status_code=404, detail="Rule application not found")

    changes = patch.model_dump(exclude_unset=True)
    merged = {
        "apply_scope": changes.get("apply_scope", existing["apply_scope"]),
        "port_id": changes.get("port_id", existing["port_id"]),
        "strategy_code": changes.get("strategy_code", existing["strategy_code"]),
        "instrument_type": changes.get("instrument_type", existing["instrument_type"]),
        "trade_side": changes.get("trade_side", existing["trade_side"]),
        "priority": changes.get("priority", existing["priority"]),
        "effective_date": changes.get("effective_date", existing["effective_date"]),
        "expiry_date": changes.get("expiry_date", existing["expiry_date"]),
        "is_active": changes.get("is_active", existing["is_active"]),
        "note": changes.get("note", existing["note"]),
        "updated_by": changes.get("updated_by"),
        "application_id": application_id,
    }
    if merged["expiry_date"] and merged["expiry_date"] < merged["effective_date"]:
        raise HTTPException(status_code=400, detail="expiry_date must not be earlier than effective_date")

    await db.execute(
        text(
            """
            UPDATE fsi.para_risk_rule_application SET
              apply_scope=:apply_scope,
              port_id=:port_id,
              strategy_code=:strategy_code,
              instrument_type=:instrument_type,
              trade_side=:trade_side,
              priority=:priority,
              effective_date=:effective_date,
              expiry_date=:expiry_date,
              is_active=:is_active,
              note=:note,
              updated_by=:updated_by,
              updated_at=NOW()
            WHERE application_id=:application_id
            """
        ),
        merged,
    )
    await db.commit()
    updated = (
        await db.execute(
            text("SELECT * FROM fsi.para_risk_rule_application WHERE application_id=:aid"),
            {"aid": application_id},
        )
    ).mappings().one()
    return dict(updated)


@router.delete("/applications/item/{application_id}", summary="停用规则应用配置")
async def deactivate_rule_application(
    application_id: int,
    updated_by: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                UPDATE fsi.para_risk_rule_application
                SET is_active=FALSE, updated_by=:updated_by, updated_at=NOW()
                WHERE application_id=:aid
                RETURNING application_id, is_active
                """
            ),
            {"aid": application_id, "updated_by": updated_by},
        )
    ).mappings().first()
    await db.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Rule application not found")
    return dict(row)
