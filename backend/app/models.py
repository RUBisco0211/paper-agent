"""Import side effects that register every table on ``Base.metadata``.

Alembic autogenerate and the test schema bootstrap import this module so that
all domain tables are known regardless of which router is loaded.
"""

# Domain tables are imported here as each module is implemented.
