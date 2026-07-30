"""
Map services for address resolution and geocoding
  . Provides address resolver utilities
  . Integrates with Google Maps API
  . Handles postcode to address conversion
"""

__all__ = [
    "address_resolver"
]
from .address_resolver import address_resolver