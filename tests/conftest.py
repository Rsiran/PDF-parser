"""Shared test fixtures."""

from __future__ import annotations

import os
import pytest
from pathlib import Path

CADELER_REPORTS = Path(
    os.environ.get(
        "CADELER_REPORTS_DIR",
        "/Users/jonas/Library/CloudStorage/OneDrive-Personal"
        "/Desktop/Investering/Cadeler/Reports",
    )
)


@pytest.fixture
def cadeler_1q25():
    """Cadeler Q1 2025 quarterly report (14 pages)."""
    path = CADELER_REPORTS / "1Q25.pdf"
    if not path.exists():
        pytest.skip("Cadeler 1Q25.pdf not available")
    return path


@pytest.fixture
def cadeler_ar24():
    """Cadeler Annual Report 2024 (270 pages)."""
    path = CADELER_REPORTS / "AR24.pdf"
    if not path.exists():
        pytest.skip("Cadeler AR24.pdf not available")
    return path
