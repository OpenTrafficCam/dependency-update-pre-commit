"""Tests for parsing requirements from various sources."""

import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from dependency_update_pre_commit.update_mypy_dependencies import (
    NormalPackage,
    TypeStubPackage,
    parse_pyproject_toml,
    parse_requirement,
    parse_requirements_file,
)


class TestParseRequirement:
    """Tests for parse_requirement() function."""

    def test_parse_requirement_with_version(self, mock_pypi: None) -> None:
        requirement = "requests==2.32.0"

        result = parse_requirement(requirement)

        assert isinstance(result, (NormalPackage, TypeStubPackage))
        expected = ExpectedPackage(name="requests", version="2.32.0", marker=None)
        assert_package_matches(result, expected)

    def test_parse_requirement_without_version(self, mock_pypi: None) -> None:
        requirement = "pytest"

        result = parse_requirement(requirement)

        assert isinstance(result, (NormalPackage, TypeStubPackage))
        expected = ExpectedPackage(name="pytest", version=None, marker=None)
        assert_package_matches(result, expected)


class TestParseRequirementsFile:
    def test_parse_basic_requirements(self, mock_pypi: None) -> None:
        given = GivenRequirementsFile(
            file_content=("requests==2.32.0\npytest>=8.0.0\nnumpy\n"),
            expected_packages=[
                ExpectedPackage("requests", "2.32.0", None),
                ExpectedPackage("pytest", "8.0.0", None),
                ExpectedPackage("numpy", None, None),
            ],
        )

        temp_file = create_temp_file(given.file_content, ".txt")
        try:
            result = parse_requirements_file(temp_file)

            packages = [
                p for p in result if isinstance(p, (NormalPackage, TypeStubPackage))
            ]
            assert len(packages) == len(given.expected_packages)

            for expected in given.expected_packages:
                matching = [
                    p
                    for p in packages
                    if p.name == expected.name or p.name == f"types-{expected.name}"
                ]
                assert (
                    len(matching) == 1
                ), f"Expected one package named '{expected.name}'"
                assert_package_matches(matching[0], expected)
        finally:
            temp_file.unlink()

    def test_parse_ignores_comments_and_blanks(self, mock_pypi: None) -> None:
        given = GivenRequirementsFile(
            file_content=(
                "# This is a comment\n"
                "requests==2.32.0\n"
                "\n"
                "  \n"
                "# Another comment\n"
                "pytest>=8.0.0\n"
            ),
            expected_packages=[
                ExpectedPackage("requests", "2.32.0", None),
                ExpectedPackage("pytest", "8.0.0", None),
            ],
        )

        temp_file = create_temp_file(given.file_content, ".txt")
        try:
            result = parse_requirements_file(temp_file)

            packages = [
                p for p in result if isinstance(p, (NormalPackage, TypeStubPackage))
            ]
            assert len(packages) == len(given.expected_packages)

            # Verify each expected package
            for expected in given.expected_packages:
                matching = [
                    p
                    for p in packages
                    if p.name == expected.name or p.name == f"types-{expected.name}"
                ]
                assert len(matching) == 1
                assert_package_matches(matching[0], expected)
        finally:
            temp_file.unlink()


class TestParsePyprojectToml:
    def test_parse_basic_dependencies(self, mock_pypi: None) -> None:
        given = GivenPyprojectToml(
            toml_content=(
                """
                [project]
                dependencies = [
                    "requests==2.32.0",
                    "pandas==2.0.0",
                ]
                """
            ),
            optional_extras=None,
            expected_packages=[
                ExpectedPackage("requests", "2.32.0", None),
                ExpectedPackage("pandas", "2.0.0", None),
            ],
        )

        temp_file = create_temp_file(given.toml_content, ".toml")
        try:
            result = parse_pyproject_toml(temp_file)

            packages = [
                p for p in result if isinstance(p, (NormalPackage, TypeStubPackage))
            ]
            assert len(packages) >= len(given.expected_packages)

            for expected in given.expected_packages:
                matching = [
                    p
                    for p in packages
                    if p.name == expected.name or p.name == f"types-{expected.name}"
                ]
                assert (
                    len(matching) == 1
                ), f"Expected one package named '{expected.name}'"
                assert_package_matches(matching[0], expected)
        finally:
            temp_file.unlink()

    def test_parse_with_platform_markers(self, mock_pypi: None) -> None:
        given = GivenPyprojectToml(
            toml_content=(
                """
                [project]
                dependencies = [
                    "requests==2.32.0",
                    "pywin32==310; sys_platform == 'win32'",
                ]
                """
            ),
            optional_extras=None,
            expected_packages=[
                ExpectedPackage("requests", "2.32.0", None),
                ExpectedPackage("pywin32", "310", 'sys_platform == "win32"'),
            ],
        )

        temp_file = create_temp_file(given.toml_content, ".toml")
        try:
            result = parse_pyproject_toml(temp_file)

            packages = [
                p for p in result if isinstance(p, (NormalPackage, TypeStubPackage))
            ]

            # Check requests
            requests_pkg = [
                p
                for p in packages
                if p.name == "requests" or p.name == "types-requests"
            ]
            assert len(requests_pkg) == 1
            assert_package_matches(
                requests_pkg[0], ExpectedPackage("requests", "2.32.0", None)
            )

            # Check pywin32 with marker
            pywin32_pkg = [p for p in packages if "pywin32" in p.name]
            assert len(pywin32_pkg) == 1
            assert_package_matches(
                pywin32_pkg[0],
                ExpectedPackage("pywin32", "310", 'sys_platform == "win32"'),
            )
        finally:
            temp_file.unlink()

    def test_parse_with_dependency_groups(self, mock_pypi: None) -> None:
        given = GivenPyprojectToml(
            toml_content=(
                """
                [project]
                dependencies = [
                    "requests==2.32.0",
                ]

                [dependency-groups]
                dev = [
                    "pytest==8.0.0",
                ]
                """
            ),
            optional_extras=None,
            expected_packages=[
                ExpectedPackage("requests", "2.32.0", None),
                ExpectedPackage("pytest", "8.0.0", None),
            ],
        )

        temp_file = create_temp_file(given.toml_content, ".toml")
        try:
            result = parse_pyproject_toml(temp_file)

            packages = [
                p for p in result if isinstance(p, (NormalPackage, TypeStubPackage))
            ]

            for expected in given.expected_packages:
                matching = [
                    p
                    for p in packages
                    if p.name == expected.name or p.name == f"types-{expected.name}"
                ]
                assert (
                    len(matching) >= 1
                ), f"Expected package '{expected.name}' not found"
                assert_package_matches(matching[0], expected)
        finally:
            temp_file.unlink()

    def test_parse_with_multiple_platform_versions(self, mock_pypi: None) -> None:
        given = GivenPyprojectToml(
            toml_content=(
                """
                [project]
                dependencies = [
                    "numpy==2.1.1; sys_platform != 'win32'",
                    "numpy==1.26.4; sys_platform == 'win32'",
                ]
                """
            ),
            optional_extras=None,
            expected_packages=[
                ExpectedPackage("numpy", "2.1.1", 'sys_platform != "win32"'),
                ExpectedPackage("numpy", "1.26.4", 'sys_platform == "win32"'),
            ],
        )

        temp_file = create_temp_file(given.toml_content, ".toml")
        try:
            result = parse_pyproject_toml(temp_file)

            packages = [
                p for p in result if isinstance(p, (NormalPackage, TypeStubPackage))
            ]
            numpy_packages = [p for p in packages if p.name == "numpy"]

            # Should have TWO distinct numpy packages
            assert len(numpy_packages) == 2, (
                "Expected 2 numpy packages with different markers, got "
                f"{len(numpy_packages)}"
            )

            # Verify both expected versions exist
            versions = {p.version for p in numpy_packages}
            assert "2.1.1" in versions
            assert "1.26.4" in versions

            # Verify both markers exist
            markers = {p.marker for p in numpy_packages}
            assert 'sys_platform != "win32"' in markers
            assert 'sys_platform == "win32"' in markers
        finally:
            temp_file.unlink()


class TestEdgeCases:
    def test_parse_nonexistent_requirements_file(self) -> None:
        nonexistent_path = Path("/nonexistent/requirements.txt")

        result = parse_requirements_file(nonexistent_path)

        assert len(result) == 0
        assert isinstance(result, set)

    def test_parse_nonexistent_pyproject_toml(self) -> None:
        nonexistent_path = Path("/nonexistent/pyproject.toml")

        result = parse_pyproject_toml(nonexistent_path)

        assert len(result) == 0
        assert isinstance(result, set)


@dataclass
class ExpectedPackage:
    name: str
    version: str | None
    marker: str | None


@dataclass
class GivenRequirementsFile:
    file_content: str
    expected_packages: list[ExpectedPackage]


@dataclass
class GivenPyprojectToml:
    toml_content: str
    optional_extras: list[str] | None
    expected_packages: list[ExpectedPackage]


def create_temp_file(content: str, suffix: str) -> Path:
    """Create a temporary file with given content."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        f.write(content)
        return Path(f.name)


def assert_package_matches(
    actual: NormalPackage | TypeStubPackage,
    expected: ExpectedPackage,
) -> None:
    """Assert that a package matches expected attributes.

    Allows TypeStubPackage with 'types-' prefix substitution.
    """
    # Handle type stub substitution (e.g., 'requests' -> 'types-requests')
    if isinstance(actual, TypeStubPackage):
        expected_name_with_stub = f"types-{expected.name}"
        assert actual.name in (expected.name, expected_name_with_stub), (
            f"Expected name '{expected.name}' or '{expected_name_with_stub}', "
            f"got '{actual.name}'"
        )
    else:
        assert (
            actual.name == expected.name
        ), f"Expected name '{expected.name}', got '{actual.name}'"

    assert (
        actual.version == expected.version
    ), f"Expected version '{expected.version}', got '{actual.version}'"
    assert (
        actual.marker == expected.marker
    ), f"Expected marker '{expected.marker}', got '{actual.marker}'"


@pytest.fixture
def mock_pypi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock PyPI API calls for deterministic testing.

    Defines which packages have type stubs available.
    """
    packages_with_stubs = {
        "requests",
        "pyyaml",
        "redis",
    }

    def mock_check_types_exists(package_name: str) -> bool:
        # Remove 'types-' prefix if present
        if package_name.startswith("types-"):
            base_name = package_name[6:]
            return base_name in packages_with_stubs
        return False

    monkeypatch.setattr(
        "dependency_update_pre_commit.update_mypy_dependencies."
        "__check_types_for_package_exists",
        mock_check_types_exists,
    )
