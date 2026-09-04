from __future__ import annotations

import pytest
from pydantic import ValidationError

from bravia_client.config import BraviaConfig
from bravia_client.models import (
    RawInput,
    VolumeCommand,
    merge_inputs,
    parse_raw_inputs,
    port_key,
)


def test_port_key_cec_and_hdmi_share_key():
    assert port_key("extInput:cec?port=1&type=player") == ("hdmi", 1)
    assert port_key("extInput:hdmi?port=1") == ("hdmi", 1)


def test_port_key_non_numeric_port():
    assert port_key("extInput:hdmi?port=abc") == ("hdmi", None)
    assert port_key("extInput:hdmi") == ("hdmi", None)
    assert port_key("weird") == ("unknown", None)


def test_merge_inputs_cec_hdmi_dedup():
    raw = parse_raw_inputs([
        {"uri": "extInput:cec?port=1", "title": "Apple TV", "connection": True},
        {"uri": "extInput:hdmi?port=1", "title": "HDMI 1", "connection": True},
        {"uri": "extInput:hdmi?port=2", "title": "HDMI 2", "connection": False},
    ])
    merged = merge_inputs(raw)
    assert len(merged) == 2
    appletv = next(i for i in merged if i.name == "Apple TV")
    assert appletv.cec is True
    assert appletv.uri.startswith("extInput:cec")
    assert appletv.connected is True


def test_merge_inputs_cec_wins_over_hdmi_connection_false():
    raw = parse_raw_inputs([
        {"uri": "extInput:cec?port=4", "title": "PlayStation 5", "connection": True},
        {"uri": "extInput:hdmi?port=4", "title": "HDMI 4", "connection": False},
    ])
    merged = merge_inputs(raw)
    assert len(merged) == 1
    assert merged[0].name == "PlayStation 5"
    assert merged[0].connected is True
    assert merged[0].cec is True


def test_merge_inputs_plain_hdmi_unconnected_stays_false():
    raw = parse_raw_inputs([{"uri": "extInput:hdmi?port=2", "title": "HDMI 2", "connection": False}])
    merged = merge_inputs(raw)
    assert merged[0].connected is False
    assert merged[0].cec is False


def test_merge_inputs_label_overrides_title():
    raw = parse_raw_inputs([{"uri": "extInput:hdmi?port=2", "title": "HDMI 2", "label": "Console", "connection": True}])
    assert merge_inputs(raw)[0].name == "Console"


def test_merge_inputs_active_flag():
    raw = parse_raw_inputs([
        {"uri": "extInput:cec?port=1", "title": "Apple TV", "connection": True},
        {"uri": "extInput:hdmi?port=2", "title": "HDMI 2", "connection": True},
    ])
    merged = merge_inputs(raw, active_uri="extInput:cec?port=1")
    assert merged[0].active is True
    assert merged[1].active is False


def test_merge_inputs_sorted_by_kind_then_port():
    raw = parse_raw_inputs([
        {"uri": "extInput:hdmi?port=4", "title": "HDMI 4", "connection": False},
        {"uri": "extInput:hdmi?port=2", "title": "HDMI 2", "connection": False},
    ])
    assert [i.port for i in merge_inputs(raw)] == [2, 4]


def test_parse_raw_inputs_non_list_returns_empty():
    assert parse_raw_inputs(None) == []
    assert parse_raw_inputs({"uri": "x"}) == []


def test_volume_command_requires_exactly_one():
    with pytest.raises(ValidationError):
        VolumeCommand(level=10, delta=5)
    with pytest.raises(ValidationError):
        VolumeCommand()
    assert VolumeCommand(level=10).level == 10
    assert VolumeCommand(delta=-5).delta == -5


def test_config_rejects_bad_mac():
    with pytest.raises(ValidationError):
        BraviaConfig(host="x", psk="k", mac="not-a-mac", _env_file=None)
    cfg = BraviaConfig(host="x", psk="k", mac="EE:B2:EB:B7:99:A6", _env_file=None)
    assert cfg.mac_hex == "eeb2ebb799a6"


def test_config_rejects_bad_scheme_and_volume_bounds():
    with pytest.raises(ValidationError):
        BraviaConfig(host="x", psk="k", scheme="ftp", _env_file=None)
    with pytest.raises(ValidationError):
        BraviaConfig(host="x", psk="k", max_volume=101, _env_file=None)
    with pytest.raises(ValidationError):
        BraviaConfig(host="x", psk="k", max_volume=-1, _env_file=None)


def test_raw_input_defaults():
    entry = RawInput(uri="extInput:hdmi?port=1")
    assert entry.title == ""
    assert entry.connection is False
    assert entry.icon is None
