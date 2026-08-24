"""Shared fixtures: synthetic SER files covering the interesting formats."""

from __future__ import annotations

import pytest

from serview.ser import ColourID

from .tools.make_test_ser import make_ser


@pytest.fixture(scope="session")
def mono8_ser(tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("ser") / "mono8.ser"
    return make_ser(str(path), 64, 48, 10, 8, ColourID.MONO, fps=25)


@pytest.fixture(scope="session")
def mono16_ser(tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("ser") / "mono16.ser"
    return make_ser(str(path), 40, 32, 6, 16, ColourID.MONO, fps=10)


@pytest.fixture(scope="session")
def bayer12_ser(tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("ser") / "bayer12.ser"
    return make_ser(str(path), 64, 48, 8, 12, ColourID.BAYER_RGGB, fps=30)


@pytest.fixture(scope="session")
def rgb8_ser(tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("ser") / "rgb8.ser"
    return make_ser(str(path), 32, 24, 5, 8, ColourID.RGB, fps=20)
