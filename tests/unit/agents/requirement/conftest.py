"""Shared fixtures for the requirement agent tests.

``requirement_baseline.json`` is a verbatim capture of the ``VSR-Dreamcar``
project's baseline serial ``3`` (17 requirements, four levels deep, with both
populated and empty UDF values), so the tests exercise the real payload shape.
"""

import itertools
import json
from pathlib import Path

import pytest

from testbench_ai_service.agents.requirement.model import Baseline, Requirement

FIXTURE = Path(__file__).parents[2] / "data" / "requirement_baseline.json"


@pytest.fixture
def baseline() -> Baseline:
    return Baseline.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


@pytest.fixture
def make_requirement():
    """Build a requirement with a distinct node key, for ranking and budget tests."""
    counter = itertools.count(1)

    def _make(
        extended_id: str,
        name: str = "",
        udf_values: tuple[str, ...] = (),
    ) -> Requirement:
        serial = str(next(counter))
        return Requirement(
            key={"serial": serial},
            requirementKey={"serial": f"r{serial}"},
            baselineKey={"serial": "3"},
            id=extended_id,
            extendedID=extended_id,
            name=name or extended_id,
            udfs=[
                {"name": f"UDF {index}", "type": "ShortTextfield", "value": value}
                for index, value in enumerate(udf_values)
            ],
        )

    return _make
