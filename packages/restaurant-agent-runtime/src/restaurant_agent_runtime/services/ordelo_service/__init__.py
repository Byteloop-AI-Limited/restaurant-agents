"""
Ordelo backend REST API service for customer operations
  . Provides OrdeloService class with async methods for customer CRUD
  . Integrates with Ordelo customer-hooks endpoints
  . Handles address updates and consent mapping
"""

__all__ = ["OrdeloService"]

from .ordelo_service import OrdeloService
