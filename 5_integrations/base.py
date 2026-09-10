"""External adapter base: auth, permission, retry, failure handling, audit."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .contracts import ExternalRecord, make_record, verify_integrity


class AdapterError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class Unauthorized(AdapterError):
    def __init__(self, message: str = "adapter call is not authorized"):
        super().__init__("AUTH", message, retryable=False)


class Forbidden(AdapterError):
    def __init__(self, permission: str):
        super().__init__("PERMISSION", f"missing permission: {permission}", retryable=False)


class IntegrityError(AdapterError):
    def __init__(self, message: str = "data integrity check failed"):
        super().__init__("INTEGRITY", message, retryable=False)


class Unavailable(AdapterError):
    def __init__(self, message: str = "external system unavailable"):
        super().__init__("UNAVAILABLE", message, retryable=True)


@dataclass
class AdapterContext:
    actor: str = "system"
    authorized: bool = True
    permissions: frozenset[str] = field(
        default_factory=lambda: frozenset({"portfolio.view", "portfolio.oversight", "trade.manage", "quant.read"})
    )
    attempts: int = 3


@dataclass
class AdapterResult:
    ok: bool
    record: ExternalRecord | None = None
    error: dict[str, Any] | None = None
    attempts: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "record": None if self.record is None else self.record.as_dict(),
            "error": self.error,
            "attempts": self.attempts,
        }


def default_audit():
    from importlib import import_module

    return import_module("4_business.risk_governance.audit_log").default_audit()


class ExternalAdapter:
    """Vendor-facing adapter. Business code depends on this type, not SDKs."""

    system = "external"
    required_permission = "portfolio.view"
    record_type = "record"

    def __init__(self, *, fail_mode: str | None = None, audit: Any | None = None, transient_failures: int = 0) -> None:
        self.fail_mode = fail_mode
        self.audit = audit or default_audit()
        self.transient_failures = int(transient_failures)
        self._seen = 0

    def pull(self, payload: dict[str, Any] | None = None, *, context: AdapterContext | None = None) -> AdapterResult:
        return self._invoke("pull", payload or {}, context or AdapterContext(), self._pull_impl)

    def push(self, payload: dict[str, Any], *, context: AdapterContext | None = None) -> AdapterResult:
        return self._invoke("push", payload, context or AdapterContext(), self._push_impl)

    def _guard(self, context: AdapterContext) -> None:
        if not context.authorized:
            raise Unauthorized()
        if self.required_permission not in context.permissions:
            raise Forbidden(self.required_permission)

    def _inject_failure(self) -> None:
        if self._seen < self.transient_failures:
            self._seen += 1
            raise Unavailable("transient")
        if self.fail_mode == "timeout":
            raise Unavailable("timeout")
        if self.fail_mode == "unavailable":
            raise Unavailable("unavailable")
        if self.fail_mode == "auth":
            raise Unauthorized("vendor rejected credentials")

    def _invoke(
        self,
        action: str,
        payload: dict[str, Any],
        context: AdapterContext,
        impl: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> AdapterResult:
        attempts = 0
        last_error: AdapterError | None = None
        try:
            self._guard(context)
        except AdapterError as exc:
            self._audit(action, context, ok=False, code=exc.code)
            return AdapterResult(ok=False, error={"code": exc.code, "message": str(exc)}, attempts=1)

        for _ in range(max(int(context.attempts), 1)):
            attempts += 1
            try:
                self._inject_failure()
                if payload.get("_corrupt"):
                    raise IntegrityError()
                raw = impl(payload)
                record = make_record(self.system, self.record_type, raw)
                if not verify_integrity(record):
                    raise IntegrityError()
                self._audit(action, context, ok=True, code="OK")
                return AdapterResult(ok=True, record=record, attempts=attempts)
            except AdapterError as exc:
                last_error = exc
                if not exc.retryable:
                    break
                time.sleep(0)
        assert last_error is not None
        self._audit(action, context, ok=False, code=last_error.code)
        return AdapterResult(
            ok=False,
            error={"code": last_error.code, "message": str(last_error)},
            attempts=attempts,
        )

    def _pull_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"echo": payload, "system": self.system}

    def _push_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"accepted": True, "system": self.system, **payload}

    def _audit(self, action: str, context: AdapterContext, *, ok: bool, code: str) -> None:
        self.audit.record(
            f"ADAPTER_{action.upper()}",
            actor=context.actor,
            payload={"system": self.system, "ok": ok, "code": code},
        )
