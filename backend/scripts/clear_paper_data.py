"""Clear paper data so existing rows get rebuilt under the new rules.

Accounts, credentials and projects are kept. Papers, entries, chunks and import
state are removed. The object store is left alone: its keys are derived from the
file hash, so stored files and artifacts stay valid caches for a re-upload.

AgentScope keeps its own database, so its schedules and sessions are removed
first. Deleting the business bindings first would leave sessions that still
exist but no longer appear in the list, and schedules that can no longer
resolve a scope.
"""

from sqlalchemy import create_engine, text

from app.platform.config import settings
from app.platform.database import engine
from app.platform.logging import configure_logging

BUSINESS_TABLES = (
    "session_bound_citations",
    "session_bindings",
    "schedule_bindings",
    "project_papers",
    "import_approvals",
    "paper_imports",
    "import_stages",
    "chunks",
    "user_papers",
    "papers",
)

# Children before parents; a session's messages and team rows go with it.
AGENTSCOPE_TABLES = (
    "messages",
    "teams",
    "schedules",
    "sessions",
)


def agentscope_engine():
    base = settings.database_url.rsplit("/", 1)[0]
    return create_engine(f"{base}/paper_agent_as")


def main() -> None:
    configure_logging()

    with agentscope_engine().begin() as connection:
        for table in AGENTSCOPE_TABLES:
            removed = connection.execute(text(f"DELETE FROM {table}")).rowcount
            print(f"cleared agentscope {table} ({removed})")

    with engine.begin() as connection:
        for table in BUSINESS_TABLES:
            removed = connection.execute(text(f"DELETE FROM {table}")).rowcount
            print(f"cleared {table} ({removed})")

    print(f"database: {settings.database_url.rsplit('@', 1)[-1]}")


if __name__ == "__main__":
    main()
