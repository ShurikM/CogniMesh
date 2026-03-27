"""Marginal cost measurement: UC-04 addition effort comparison."""
from __future__ import annotations

import os

UC04_REST_DIR = os.path.join(
    os.path.dirname(__file__), "..", "uc04", "rest_changes",
)
UC04_MESH_DIR = os.path.join(
    os.path.dirname(__file__), "..", "uc04", "cognimesh_changes",
)

_CODE_EXTENSIONS = (".py", ".sql", ".json")


def _count_files(directory: str) -> int:
    """Count code files (py/sql/json) in *directory*."""
    count = 0
    for name in os.listdir(directory):
        if name.endswith(_CODE_EXTENSIONS) and not name.startswith("."):
            count += 1
    return count


def _count_loc(directory: str) -> int:
    """Count non-blank lines in code files in *directory*."""
    total = 0
    for name in os.listdir(directory):
        if name.endswith(_CODE_EXTENSIONS) and not name.startswith("."):
            path = os.path.join(directory, name)
            with open(path) as fh:  # noqa: S108
                total += sum(1 for line in fh if line.strip())
    return total


class TestMarginalCost:
    """Compare engineering effort to add UC-04 via REST vs CogniMesh."""

    def test_rest_uc04_file_count(self) -> None:
        """REST requires multiple new files for a new UC."""
        assert _count_files(UC04_REST_DIR) >= 3  # noqa: S101

    def test_cognimesh_uc04_file_count(self) -> None:
        """CogniMesh requires exactly one JSON definition."""
        assert _count_files(UC04_MESH_DIR) == 1  # noqa: S101

    def test_rest_uc04_loc(self) -> None:
        """REST needs substantial code for a new UC."""
        loc = _count_loc(UC04_REST_DIR)
        assert loc >= 60  # noqa: S101

    def test_cognimesh_uc04_loc(self) -> None:
        """CogniMesh JSON definition is small."""
        loc = _count_loc(UC04_MESH_DIR)
        assert loc <= 30  # noqa: S101

    def test_marginal_cost_ratio(self) -> None:
        """CogniMesh effort is less than 30% of REST effort."""
        rest_loc = _count_loc(UC04_REST_DIR)
        mesh_loc = _count_loc(UC04_MESH_DIR)
        ratio = mesh_loc / rest_loc
        assert ratio < 0.30  # noqa: S101
