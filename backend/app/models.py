"""Import side effects that register every table on ``Base.metadata``.

Alembic autogenerate and the test schema bootstrap import this module so that
all domain tables are known regardless of which router is loaded.
"""

from .auth import persistence as _auth_persistence  # noqa: F401
from .imports import persistence as _imports_persistence  # noqa: F401
from .ingestion import persistence as _ingestion_persistence  # noqa: F401
from .library import persistence as _library_persistence  # noqa: F401
from .projects import persistence as _projects_persistence  # noqa: F401
from .retrieval import persistence as _retrieval_persistence  # noqa: F401
from .sessions import persistence as _sessions_persistence  # noqa: F401
