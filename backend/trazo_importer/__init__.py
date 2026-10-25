"""Importación de cartas Gantt para Trazo.

El paquete no depende de la base de datos: normaliza y valida un libro antes
de entregarlo a la capa de persistencia. Esto permite que el caso de uso sea
transaccional tanto con SQLAlchemy como con un repositorio de prueba.
"""

from .models import CanonicalWorkbook, ValidationIssue, ValidationReport
from .service import ImportFormatError, ImportResult, ImportService, InMemoryImportStore

__all__ = [
    "CanonicalWorkbook",
    "ImportFormatError",
    "ImportResult",
    "ImportService",
    "InMemoryImportStore",
    "ValidationIssue",
    "ValidationReport",
]
