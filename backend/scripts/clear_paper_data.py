"""Clear paper data so existing rows get rebuilt under the new parsing rules.

Accounts, credentials and the object store are untouched: the stored PDFs and
MinerU artefacts stay cached by content hash.
"""

from sqlalchemy import text

from app.platform.config import settings
from app.platform.database import engine

TABLES = (
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


def main() -> None:
    with engine.begin() as connection:
        for table in TABLES:
            connection.execute(text(f"DELETE FROM {table}"))
            print(f"cleared {table}")
    print(f"database: {settings.database_url.rsplit('@', 1)[-1]}")


if __name__ == "__main__":
    main()
