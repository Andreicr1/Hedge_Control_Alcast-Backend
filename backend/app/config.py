import json
import os
import re
from pathlib import Path
from typing import List

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    app_name: str = Field(default=os.getenv("PROJECT_NAME", "Hedge Control API"))
    environment: str = Field(default=os.getenv("ENVIRONMENT", "dev"), env="ENVIRONMENT")
    build_version: str | None = Field(default=os.getenv("BUILD_VERSION"), env="BUILD_VERSION")
    database_url: str = Field(
        default=os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/alcast_db")
    )
    # API prefix used by FastAPI router include. MUST be configured via API_V1_STR (e.g. "/api/v1").
    api_prefix: str = Field(default="", env="API_V1_STR")
    enable_docs: bool = Field(default=True, env="ENABLE_DOCS")
    secret_key: str = Field(default=os.getenv("SECRET_KEY", "change-me"))
    access_token_expire_minutes: int = Field(
        default=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    )
    algorithm: str = Field(default=os.getenv("ALGORITHM", "HS256"))
    cors_origins: List[str] = Field(default_factory=list, env="CORS_ORIGINS")
    storage_dir: str = Field(default=os.getenv("STORAGE_DIR", "storage"))
    whatsapp_webhook_secret: str | None = Field(default=os.getenv("WHATSAPP_WEBHOOK_SECRET"))
    webhook_secret: str | None = Field(default=os.getenv("WEBHOOK_SECRET"))
    scheduler_enabled: bool = Field(default=os.getenv("SCHEDULER_ENABLED", "true"))

    class Config:
        env_file = ".env"
        case_sensitive = False

        @classmethod
        def parse_env_var(cls, field_name: str, raw_val: str):
            # Pydantic BaseSettings (v1) attempts to JSON-decode complex types (e.g. List[str])
            # before validators run, which can crash on non-JSON values.
            # For CORS_ORIGINS we want to accept JSON, Python-ish list strings, or CSV.
            if field_name == "cors_origins":
                return raw_val
            try:
                return cls.json_loads(raw_val)
            except Exception:
                return raw_val

    @validator("enable_docs", pre=True, always=True)
    def default_enable_docs(cls, value, values):
        if value is None or value == "":
            env = str(values.get("environment", "dev") or "dev").lower()
            return env in {"dev", "development", "test"}
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)

    @validator("cors_origins", pre=True, always=True)
    def parse_and_default_cors_origins(cls, value, values):
        env = str(values.get("environment", "dev") or "dev").lower()

        def _normalize_origin(o: str) -> str:
            s = str(o).strip().strip('"').strip("'")
            # Browsers send the Origin header without a trailing slash.
            if s.endswith("/"):
                s = s[:-1]
            return s

        # If not provided, default to a safe dev/test list; require explicit config in production.
        if value is None or value == "":
            if env in {"prod", "production"}:
                raise ValueError("CORS_ORIGINS must be explicitly set in production")
            return [
                "http://localhost:5173",
                "http://localhost:5174",
                "http://localhost:5175",
                "http://localhost:3000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5174",
                "http://127.0.0.1:5175",
            ]

        if isinstance(value, str):
            s = value.strip()
            # Many .env / docker setups wrap JSON in quotes. Strip a single pair.
            if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                s = s[1:-1].strip()

            # First, try normal JSON (recommended): ["http://...", "http://..."]
            try:
                parsed = json.loads(s)
                if isinstance(parsed, str):
                    return [_normalize_origin(parsed)]
                if isinstance(parsed, list):
                    return [_normalize_origin(v) for v in parsed if str(v).strip()]
                return [_normalize_origin(str(parsed))]
            except json.JSONDecodeError:
                pass

            # Then, accept Python-ish list strings: ['http://...','http://...']
            if s.startswith("[") and s.endswith("]") and ("'") in s and ('"' not in s):
                try:
                    parsed = json.loads(s.replace("'", '"'))
                    if isinstance(parsed, list):
                        return [_normalize_origin(v) for v in parsed if str(v).strip()]
                except json.JSONDecodeError:
                    pass

            # Finally, accept comma-separated origins.
            return [_normalize_origin(v) for v in s.split(",") if str(v).strip()]

        return value

    @validator("api_prefix", pre=True)
    def normalize_api_prefix(cls, v: str) -> str:
        """
        Normalize API prefix coming from env/.env.

        On Windows Git Bash (MSYS), values like "/api/v1" may sometimes appear as a Windows path
        (e.g. "C:/Program Files/Git/api/v1"). When that happens, extract the trailing "/api/..."
        portion so routing keeps working.
        """
        if v is None:
            return ""
        s = str(v).strip()
        if not s:
            return ""

        # If it already looks like an API prefix, keep it.
        if s.startswith("/api/") or s == "/api":
            return s

        # Extract "/api/..." from any path-like string.
        m = re.search(r"(/api/[^\\s]+)$", s.replace("\\", "/"))
        if m:
            return m.group(1)

        # Final fallback: if a bare "api/v1" was provided, normalize to "/api/v1".
        if s.startswith("api/"):
            return f"/{s}"

        return s

    @validator("database_url", pre=True)
    def normalize_database_url(cls, v: str) -> str:
        """Make SQLite relative paths stable across working directories.

        In dev, we often use sqlite URLs like:
        - sqlite+pysqlite:///./dev-local.db

        When running `uvicorn` from another folder (e.g. the frontend), the
        relative path resolves to the wrong place, which looks like "missing
        tables" at runtime. Convert known relative SQLite URLs to an absolute
        path rooted at the backend folder.
        """

        if v is None:
            return v

        s = str(v).strip()
        if not s:
            return s

        # Normalize common Postgres URL schemes for psycopg3.
        # Supabase commonly provides: postgresql://...
        # SQLAlchemy defaults postgresql:// to psycopg2, but we ship psycopg3.
        if s.startswith("postgres://"):
            s = "postgresql://" + s[len("postgres://") :]
        if s.startswith("postgresql://"):
            return "postgresql+psycopg://" + s[len("postgresql://") :]
        if s.startswith("postgresql+psycopg2://"):
            return "postgresql+psycopg://" + s[len("postgresql+psycopg2://") :]

        # Only touch sqlite URLs; keep other schemes intact.
        if not s.startswith("sqlite"):
            return s

        marker = ":///"
        i = s.find(marker)
        if i == -1:
            return s

        path_part = s[i + len(marker) :]

        # Already absolute (e.g. /var/... or C:/...)
        if path_part.startswith("/") or re.match(r"^[A-Za-z]:/", path_part):
            return s

        # Convert common relative patterns.
        if path_part.startswith("./") or path_part.startswith(".\\"):
            backend_root = Path(__file__).resolve().parents[1]
            rel = path_part[2:] if path_part.startswith("./") else path_part[2:]
            abs_path = (backend_root / rel).resolve().as_posix()
            return f"{s[: i + len(marker)]}{abs_path}"

        return s

    @validator("secret_key")
    def validate_secret_key(cls, v: str) -> str:
        if not v or v.startswith("sua-chave-secreta") or v.lower() in {"change-me", "secret"}:
            raise ValueError("SECRET_KEY must be set to a strong value")
        return v


settings = Settings()
