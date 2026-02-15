"""
Database model registry.

Importing this module ensures all table models are registered with
SQLModel's metadata, which is required before calling ``create_all()``
or generating Alembic migrations.
"""

from app.models.fund import Fund  # noqa: F401
from app.models.investor import Investor  # noqa: F401
from app.models.investment import Investment  # noqa: F401
