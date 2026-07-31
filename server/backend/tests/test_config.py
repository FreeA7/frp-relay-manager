import pytest

from app.config import _port_set


def test_port_set_parses_ports_and_ranges():
    assert _port_set("20001, 20003-20005") == frozenset({20001, 20003, 20004, 20005})


@pytest.mark.parametrize("value", ["invalid", "0", "65536", "20002-20001"])
def test_port_set_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        _port_set(value)
