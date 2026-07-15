from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .schemas import WorkflowMode


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


class Settings:
    def __init__(self) -> None:
        root = ROOT
        self.root = root
        self.service_name = os.getenv("AUTORISK_SERVICE_NAME", "AutoRisk")
        self.api_prefix = os.getenv("AUTORISK_API_PREFIX", "/api/v1")
        raw_mode = os.getenv("AUTORISK_WORKFLOW_MODE", WorkflowMode.FULL_AI.value).upper()
        self.workflow_mode = WorkflowMode(raw_mode)
        self.storage_path = Path(
            os.getenv("AUTORISK_STORAGE_PATH", str(root / "data" / "risk_reports.json"))
        )
        self.audit_path = Path(
            os.getenv("AUTORISK_AUDIT_PATH", str(root / "data" / "audit_events.jsonl"))
        )
        self.feedback_path = Path(
            os.getenv("AUTORISK_FEEDBACK_PATH", str(root / "data" / "feedback_receipts.json"))
        )
        if not self.feedback_path.is_absolute():
            self.feedback_path = root / self.feedback_path
        self.artifact_dir = Path(
            os.getenv("AUTORISK_ARTIFACT_DIR", str(root / "data" / "reports"))
        )
        self.rules_path = Path(
            os.getenv("AUTORISK_RULES_PATH", str(root / "config" / "rules.json"))
        )
        self.cors_origins = [
            item.strip()
            for item in os.getenv("AUTORISK_CORS_ORIGINS", "*").split(",")
            if item.strip()
        ]
        self.api_keys = {
            item.strip()
            for item in os.getenv("AUTORISK_API_KEYS", "autorisk-dev-key").split(",")
            if item.strip()
        }
        self.signing_secret = os.getenv(
            "AUTORISK_SIGNING_SECRET",
            "change-this-development-signing-secret",
        )
        self.ai_review_enabled = os.getenv("AUTORISK_AI_REVIEW_ENABLED", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.ai_provider = os.getenv("AUTORISK_AI_PROVIDER", "deterministic").lower()
        self.llm_base_url = os.getenv("AUTORISK_LLM_BASE_URL", "").rstrip("/")
        self.llm_api_key = os.getenv("AUTORISK_LLM_API_KEY", "")
        self.llm_model = os.getenv("AUTORISK_LLM_MODEL", "")
        self.llm_timeout_seconds = float(os.getenv("AUTORISK_LLM_TIMEOUT_SECONDS", "20"))
        self.callback_enabled = os.getenv("AUTORISK_CALLBACK_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.default_signers = {
            "first": os.getenv("AUTORISK_FIRST_SIGNER", "ai-risk-officer"),
            "second": os.getenv("AUTORISK_SECOND_SIGNER", "ai-mic"),
        }
        self.conclusion_validity_minutes = max(
            1,
            int(os.getenv("AUTORISK_CONCLUSION_VALIDITY_MINUTES", "60")),
        )


settings = Settings()
