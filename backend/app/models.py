"""Import side effects that register every table on ``Base.metadata``.

Alembic autogenerate and the test schema bootstrap import this module so that
all domain tables are known regardless of which router is loaded.
"""

from .auth import repo as _auth_repo  # noqa: F401
from .imports import repo as _imports_repo  # noqa: F401
from .library import repo as _library_repo  # noqa: F401
from .pipelines import repo as _pipelines_repo  # noqa: F401
from .platform import mail as _mail  # noqa: F401
from .projects import repo as _projects_repo  # noqa: F401
from .retrieval import repo as _retrieval_repo  # noqa: F401
from .service_credentials import repo as _service_credentials_repo  # noqa: F401
from .sessions import repo as _sessions_repo  # noqa: F401
