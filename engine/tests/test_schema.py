"""A14: invalid methods are rejected with a message that names the field."""

import json
from copy import deepcopy
from decimal import Decimal
from typing import Any

import pytest

from engine.errors import MethodConfigError
from engine.schema import load_method

from .builders import BASE_METHOD

pytestmark = pytest.mark.unit


def _load(changes: dict[str, Any]) -> None:
    raw = deepcopy(BASE_METHOD)
    for dotted, value in changes.items():
        node = raw
        *path, last = dotted.split(".")
        for key in path:
            node = node[key]
        node[last] = value
    load_method(json.dumps(raw))


def test_the_base_method_is_valid() -> None:
    _load({})


def test_a14_weights_must_sum_to_one() -> None:
    with pytest.raises(MethodConfigError, match=r"direct.*sum to 1.*1\.2"):
        _load({"direct.SEE": "0.80"})


def test_a14_overlapping_or_unordered_bands_are_rejected() -> None:
    bands = [
        {"min_pct": 50, "level": 2},
        {"min_pct": 60, "level": 3},
    ]
    with pytest.raises(MethodConfigError, match=r"levels\.bands.*highest to lowest"):
        _load({"levels.bands": bands})
    with pytest.raises(MethodConfigError, match=r"levels\.bands"):
        _load({"levels.bands": [{"min_pct": 60, "level": 3}, {"min_pct": 60, "level": 2}]})


def test_a14_unknown_tool_is_rejected() -> None:
    with pytest.raises(MethodConfigError, match=r"direct.*unknown tool 'EXAM'"):
        _load({"direct.EXAM": "0"})
    with pytest.raises(MethodConfigError, match=r"merge.*unknown tool 'INT9'"):
        _load({"merge.INTERNAL.from": ["INT1", "INT9"]})


@pytest.mark.parametrize("bad", [101, -1])
def test_a14_percent_outside_0_to_100_is_rejected(bad: int) -> None:
    with pytest.raises(MethodConfigError, match=r"tools\.SEE\.question_wise\.pass_pct"):
        _load({"tools.SEE.pass_pct": bad})


def test_a14_band_minimum_outside_0_to_100_is_rejected() -> None:
    with pytest.raises(MethodConfigError, match=r"min_pct"):
        _load({"levels.bands": [{"min_pct": 120, "level": 3}]})


def test_a14_final_weights_must_sum_to_one() -> None:
    with pytest.raises(MethodConfigError, match=r"final.*sum to 1"):
        _load({"final.direct": "0.7"})


def test_a14_a_tool_without_a_weight_is_rejected() -> None:
    with pytest.raises(MethodConfigError, match=r"tool 'SEE'.*no weight"):
        _load({"direct": {"INTERNAL": "0.40", "ASSIGN": "0.30", "QUIZ": "0.30"}})


def test_a_merged_tool_cannot_also_be_weighted() -> None:
    with pytest.raises(MethodConfigError, match=r"'INT1' is merged"):
        _load({"direct": {"INT1": "0.3", "ASSIGN": "0.05", "QUIZ": "0.05", "SEE": "0.6"}})


def test_unknown_keys_and_bad_values_are_rejected() -> None:
    with pytest.raises(MethodConfigError, match="(?i)extra"):
        _load({"surprise": 1})
    with pytest.raises(MethodConfigError, match=r"tools\.SEE"):
        _load({"tools.SEE.boundary": "=="})
    with pytest.raises(MethodConfigError, match=r"fixed_n"):
        _load({"tools.SEE.denominator": "fixed"})


def test_text_that_is_not_json_is_a_config_error() -> None:
    with pytest.raises(MethodConfigError, match="not valid JSON"):
        load_method("{nope")


def test_numbers_in_json_are_read_as_exact_decimals() -> None:
    text = json.dumps(BASE_METHOD).replace('"0.30"', "0.30")
    assert load_method(text).direct["INTERNAL"] == Decimal("0.30")
