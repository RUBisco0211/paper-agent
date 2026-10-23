"""Clear paper data so existing rows get rebuilt under the new parsing rules.

Accounts, credentials and the object store are untouched: the stored PDFs and
MinerU artefacts stay cached by content hash.

AgentScope keeps its own database, so its schedules and sessions are removed
first (0043). Deleting the business bindings first would leave sessions that
still exist but no longer appear in the list, and schedules that can no longer
resolve a scope.
"""

from sqlalchemy import create_engine, text

from app.platform.config import settings
from app.platform.database import engine

BUSINESS_TABLES = (
    "session_bound_citations",
    "session_bindings",
    "schedule_bindings",
    "project_papers",
    "import_approvals",
    "paper_imports",
    "ingestion_stages",
    "ingestion_jobs",
    "chunks",
    "user_papers",
    "papers",
    "projects",
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
