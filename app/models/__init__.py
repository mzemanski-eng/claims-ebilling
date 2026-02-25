# Import all models here so Alembic's env.py can discover them via Base.metadata
from app.models.base import Base  # noqa: F401
from app.models.taxonomy import TaxonomyItem  # noqa: F401
from app.models.supplier import User, Carrier, Supplier, Contract, RateCard, Guideline  # noqa: F401
from app.models.invoice import Invoice, InvoiceVersion, LineItem, RawExtractionArtifact  # noqa: F401
from app.models.mapping import MappingRule  # noqa: F401
from app.models.validation import ValidationResult, ExceptionRecord  # noqa: F401
from app.models.audit import AuditEvent  # noqa: F401
