"""Exposure domain ORM entities (fsi schema)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Float, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ExposureBase(DeclarativeBase):
    """Minimal ORM base for exposure-related snapshots."""


class BalancePortfolioNav(ExposureBase):
    __tablename__ = "balance_portfolio_nav"
    __table_args__ = {"schema": "fsi"}

    port_id: Mapped[str] = mapped_column(String, primary_key=True)
    evaluate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    class_id: Mapped[str | None] = mapped_column(String, nullable=True)
    net_asset: Mapped[float | None] = mapped_column(Numeric, nullable=True)


class BalancePortfolioMmf(ExposureBase):
    __tablename__ = "balance_portfolio_mmf"
    __table_args__ = {"schema": "fsi"}

    port_id: Mapped[str] = mapped_column(String, primary_key=True)
    evaluate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    wam_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    wal_days: Mapped[float | None] = mapped_column(Float, nullable=True)


class BalancePortfolioAsset(ExposureBase):
    __tablename__ = "balance_portfolio_asset"
    __table_args__ = {"schema": "fsi"}

    port_id: Mapped[str] = mapped_column(String, primary_key=True)
    evaluate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    asset_class: Mapped[str] = mapped_column(String, primary_key=True)
    market_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)


class BalanceCash(ExposureBase):
    __tablename__ = "balance_cash"
    __table_args__ = {"schema": "fsi"}

    port_id: Mapped[str] = mapped_column(String, primary_key=True)
    evaluate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    amount_base_ccy: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric, nullable=True)


class BalanceBond(ExposureBase):
    __tablename__ = "balance_bond"
    __table_args__ = {"schema": "fsi"}

    port_id: Mapped[str] = mapped_column(String, primary_key=True)
    evaluate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    asset_subtype: Mapped[str | None] = mapped_column(String, nullable=True)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    market_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    issuer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    issuer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    issuer_group: Mapped[str | None] = mapped_column(String, nullable=True)


class BalanceCd(ExposureBase):
    __tablename__ = "balance_cd"
    __table_args__ = {"schema": "fsi"}

    port_id: Mapped[str] = mapped_column(String, primary_key=True)
    evaluate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    market_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    issuer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    issuer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    issuer_group: Mapped[str | None] = mapped_column(String, nullable=True)


class BalanceDeposit(ExposureBase):
    __tablename__ = "balance_deposit"
    __table_args__ = {"schema": "fsi"}

    port_id: Mapped[str] = mapped_column(String, primary_key=True)
    evaluate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    principal: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    total_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    is_overnight: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String, nullable=True)
    bank_id: Mapped[str | None] = mapped_column(String, nullable=True)
    bank_group: Mapped[str | None] = mapped_column(String, nullable=True)


class BalanceRepo(ExposureBase):
    __tablename__ = "balance_repo"
    __table_args__ = {"schema": "fsi"}

    port_id: Mapped[str] = mapped_column(String, primary_key=True)
    evaluate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    principal: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    repo_type: Mapped[str | None] = mapped_column(String, nullable=True)
    actual_maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
