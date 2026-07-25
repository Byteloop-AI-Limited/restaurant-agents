"""
Unit tests for Google Maps address resolver without network access
    . Loads address resolver with stubbed config and mocked requests.get
    . Covers postcode normalization, geocode parsing, non-OK responses, and exceptions
    . Verifies UK postcode formatting and address component extraction
  Functions/Classes:
    . resolver_module
    . FakeResponse
    . geocode_payload
    . test_uk_address_formats_postcode
    . test_parse_geocode_response_extracts_components
    . test_get_address_from_postcode_success_formats_request_and_sets_input
    . test_get_address_from_postcode_non_ok_returns_partial_address
    . test_get_address_from_coordinates_exception_returns_minimal_address
"""

import pytest

from tests._stubs.config_stub import build_config_stub
from tests._stubs.loader import load_module


class FakeResponse:
    def __init__(self, json_data, error=None):
        self._json_data = json_data
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self._json_data


@pytest.fixture
def resolver_module(monkeypatch):
    return load_module(
        "test_address_resolver_module",
        "restaurant_agent_core.services/maps_service/address_resolver.py",
        monkeypatch,
        {"config": build_config_stub()},
    )


@pytest.fixture
def geocode_payload():
    return {
        "status": "OK",
        "results": [
            {
                "address_components": [
                    {"long_name": "10", "short_name": "10", "types": ["street_number"]},
                    {"long_name": "High Street", "short_name": "High St", "types": ["route"]},
                    {"long_name": "Orpington", "short_name": "Orpington", "types": ["postal_town"]},
                    {"long_name": "Greater London", "short_name": "London", "types": ["administrative_area_level_2"]},
                    {"long_name": "BR66DN", "short_name": "BR6 6DN", "types": ["postal_code"]},
                    {"long_name": "United Kingdom", "short_name": "GB", "types": ["country"]},
                ],
                "formatted_address": "10 High Street, Orpington BR6 6DN, UK",
                "place_id": "place-1",
                "types": ["street_address"],
                "geometry": {"location": {"lat": 51.3, "lng": 0.1}},
            }
        ],
    }


def test_uk_address_formats_postcode(resolver_module):
    address = resolver_module.UKAddress(postcode="br66dn")

    assert address.postcode == "BR6 6DN"


def test_parse_geocode_response_extracts_components(resolver_module, geocode_payload):
    resolver = resolver_module.AddressResolver("key")

    address = resolver._parse_geocode_response(geocode_payload, latitude=51.3, longitude=0.1)

    assert address.house_number == "10"
    assert address.street_name == "High Street"
    assert address.city == "Orpington"
    assert address.county == "Greater London"
    assert address.postcode == "BR6 6DN"
    assert address.latitude == 51.3
    assert address.longitude == 0.1


def test_get_address_from_postcode_success_formats_request_and_sets_input(monkeypatch, resolver_module, geocode_payload):
    calls = []

    def fake_get(url, params):
        calls.append({"url": url, "params": params})
        return FakeResponse(geocode_payload)

    monkeypatch.setattr(resolver_module.requests, "get", fake_get)

    address = resolver_module.AddressResolver("key").get_address_from_postcode("br66dn")

    assert calls[0]["params"]["address"] == "BR6 6DN, UK"
    assert calls[0]["params"]["key"] == "key"
    assert address.input_postcode == "br66dn"
    assert address.latitude == 51.3


def test_get_address_from_postcode_non_ok_returns_partial_address(monkeypatch, resolver_module):
    monkeypatch.setattr(
        resolver_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"status": "ZERO_RESULTS", "results": []}),
    )

    address = resolver_module.AddressResolver("key").get_address_from_postcode("br66dn")

    assert address.postcode == "BR6 6DN"
    assert address.input_postcode == "br66dn"
    assert address.raw_response == {"status": "ZERO_RESULTS", "results": []}


def test_get_address_from_coordinates_exception_returns_minimal_address(monkeypatch, resolver_module):
    def fake_get(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(resolver_module.requests, "get", fake_get)

    address = resolver_module.AddressResolver("key").get_address_from_coordinates(51.3, 0.1)

    assert address.latitude == 51.3
    assert address.longitude == 0.1
    assert address.raw_response is None
