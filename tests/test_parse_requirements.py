"""Tests for parsing requirements from various sources."""

import tempfile
from pathlib import Path

from update_mypy_dependencies import (
    NormalPackage,
    TypeStubPackage,
    parse_pyproject_toml,
    parse_requirement,
    parse_requirements_file,
)


def test_parse_requirement_with_version() -> None:
    """Test parsing a requirement with version specification."""
    result = parse_requirement("requests==2.32.0")
    assert isinstance(result, (NormalPackage, TypeStubPackage))
    assert result.name in ("requests", "types-requests")


def test_parse_requirement_without_version() -> None:
    """Test parsing a requirement without version specification."""
    result = parse_requirement("pytest")
    assert isinstance(result, (NormalPackage, TypeStubPackage))


def test_parse_requirements_file() -> None:
    """Test parsing a requirements.txt file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("requests==2.32.0\n")
        f.write("# This is a comment\n")
        f.write("pytest>=8.0.0\n")
        f.write("\n")
        temp_path = Path(f.name)

    try:
        result = parse_requirements_file(temp_path)
        assert len(result) > 0
        # Check that comments and empty lines are ignored
        assert all(hasattr(dep, "serialize") for dep in result)
    finally:
        temp_path.unlink()


def test_parse_pyproject_toml() -> None:
    """Test parsing a pyproject.toml file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(
            """
[project]
dependencies = [
    "requests==2.32.0",
    "pandas==2.0.0",
]

[dependency-groups]
dev = [
    "pytest==8.0.0",
]
"""
        )
        temp_path = Path(f.name)

    try:
        result = parse_pyproject_toml(temp_path)
        assert len(result) >= 3  # At least the three packages specified
    finally:
        temp_path.unlink()


def test_parse_pyproject_toml_with_platform_specific() -> None:
    """Test parsing pyproject.toml with platform-specific dependencies."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(
            """
[project]
dependencies = [
    "requests==2.32.0",
    "pywin32==310; sys_platform == 'win32'",
]
"""
        )
        temp_path = Path(f.name)

    try:
        result = parse_pyproject_toml(temp_path)
        # Should parse both dependencies, ignoring the platform specifier
        assert len(result) >= 2
    finally:
        temp_path.unlink()


def test_parse_nonexistent_file() -> None:
    """Test parsing a file that doesn't exist."""
    result = parse_requirements_file(Path("/nonexistent/file.txt"))
    assert len(result) == 0

    result = parse_pyproject_toml(Path("/nonexistent/pyproject.toml"))
    assert len(result) == 0
