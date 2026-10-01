"""Runtime configuration, read from environment variables at call time."""
import os


def database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./trades.db")


def expiry_interval_minutes() -> int:
    return int(os.getenv("EXPIRY_JOB_INTERVAL_MINUTES", "60"))


def scheduler_enabled() -> bool:
    return os.getenv("ENABLE_SCHEDULER", "true").strip().lower() in {"1", "true", "yes"}