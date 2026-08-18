from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

from tools.risk.exposure_domain import ExposureResult, check_mmf_compliance
from tools.risk.rule_limits import DEFAULT_MMF_LIMITS, load_effective_mmf_limits


class _Result:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def fetchall(self) -> list[SimpleNamespace]:
        return self._rows


class _Db:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    async def execute(self, *_args, **_kwargs) -> _Result:
        return _Result(self.rows)


def test_compliance_checker_uses_configured_thresholds() -> None:
    result = ExposureResult(
        fund_id="FUND001",
        as_of_date=date(2026, 6, 25),
        wam_days=55,
        wal_days=100,
        daily_liquid_pct=10,
        weekly_liquid_pct=20,
    )

    flags = check_mmf_compliance(
        result,
        nav=100,
        limits={"MMF_WAM": 50, "MMF_DAILY_LIQUID": 12},
    )

    assert flags == {"WAM_BREACH": True, "DAILY_LIQUID_BREACH": True}


def test_effective_limits_take_strictest_across_rule_types() -> None:
    db = _Db(
        [
            SimpleNamespace(rule_code="MMF_WAM", limit_direction="MAX", limit_value=60),
            SimpleNamespace(rule_code="MMF_WAM", limit_direction="MAX", limit_value=45),
            SimpleNamespace(rule_code="MMF_DAILY_LIQUID", limit_direction="MIN", limit_value=7.5),
            SimpleNamespace(rule_code="MMF_DAILY_LIQUID", limit_direction="MIN", limit_value=12),
            SimpleNamespace(rule_code="MMF_WAL", limit_direction="MIN", limit_value=999),
            SimpleNamespace(rule_code="UNSUPPORTED", limit_direction="MAX", limit_value=1),
        ]
    )

    limits = asyncio.run(load_effective_mmf_limits(db, "FUND001", date(2026, 6, 25)))  # type: ignore[arg-type]

    assert limits["MMF_WAM"] == 45
    assert limits["MMF_DAILY_LIQUID"] == 12
    assert limits["MMF_WAL"] == DEFAULT_MMF_LIMITS["MMF_WAL"]


def test_effective_limits_fall_back_to_defaults() -> None:
    limits = asyncio.run(
        load_effective_mmf_limits(_Db([]), "FUND001", date(2026, 6, 25))  # type: ignore[arg-type]
    )

    assert limits == DEFAULT_MMF_LIMITS
