"""Unit tests for LifecycleType enum and properties."""
import pytest

from app.services.lifecycle_types import LifecycleType


def test_annual_is_not_perennial():
    assert LifecycleType.ANNUAL.is_perennial is False
    assert LifecycleType.ANNUAL.is_woody is False
    assert LifecycleType.ANNUAL.has_dormancy is False


def test_perennial_woody_deciduous_properties():
    apple = LifecycleType.PERENNIAL_WOODY_DECIDUOUS

    assert apple.is_perennial is True
    assert apple.is_woody is True
    assert apple.has_dormancy is True


def test_perennial_herbaceous_is_perennial_not_woody():
    strawberry = LifecycleType.PERENNIAL_HERBACEOUS

    assert strawberry.is_perennial is True
    assert strawberry.is_woody is False
    assert strawberry.has_dormancy is True


def test_string_value_compatible_with_db():
    """LifecycleType values must round-trip through string DB column."""
    assert LifecycleType.ANNUAL.value == "annual"
    assert LifecycleType.PERENNIAL_WOODY_DECIDUOUS.value == "perennial_woody_deciduous"
    assert LifecycleType("perennial_herbaceous") == LifecycleType.PERENNIAL_HERBACEOUS


def test_invalid_value_raises():
    with pytest.raises(ValueError):
        LifecycleType("invalid")
