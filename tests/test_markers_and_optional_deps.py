"""Tests for marker preservation and optional dependencies support."""

import tempfile
from pathlib import Path

from dependency_update_pre_commit.update_mypy_dependencies import (
    NormalPackage,
    parse_optional_dependencies,
    parse_pyproject_toml,
    parse_requirement_with_marker,
)


def test_parse_requirement_with_marker() -> None:
    """Test that platform markers are preserved."""
    result = parse_requirement_with_marker('numpy==2.1.1; sys_platform != "win32"')
    assert isinstance(result, NormalPackage)
    assert result.name == "numpy"
    assert result.version == "2.1.1"
    assert result.marker == 'sys_platform != "win32"'


def test_parse_requirement_without_marker() -> None:
    """Test parsing requirement without marker."""
    result = parse_requirement_with_marker("requests==2.32.0")
    # requests has a type stub, so it will be TypeStubPackage
    assert hasattr(result, "marker")
    assert result.marker is None


def test_serialize_package_with_marker() -> None:
    """Test that packages serialize with markers."""
    pkg = NormalPackage(name="numpy", version="2.1.1", marker='sys_platform != "win32"')
    assert pkg.serialize() == 'numpy==2.1.1; sys_platform != "win32"'


def test_serialize_package_without_marker() -> None:
    """Test that packages without markers serialize correctly."""
    pkg = NormalPackage(name="numpy", version="2.1.1", marker=None)
    assert pkg.serialize() == "numpy==2.1.1"


def test_parse_pyproject_toml_preserves_markers() -> None:
    """Test that pyproject.toml parsing preserves markers."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(
            """
[project]
dependencies = [
    "numpy==2.1.1; sys_platform != 'win32'",
    "numpy==1.26.4; sys_platform == 'win32'",
]
"""
        )
        temp_path = Path(f.name)

    try:
        result = parse_pyproject_toml(temp_path)
        # Should have two distinct numpy packages with different markers
        numpy_packages = [p for p in result if hasattr(p, "name") and p.name == "numpy"]
        assert len(numpy_packages) == 2

        # Check that markers are preserved
        markers = {p.marker for p in numpy_packages}
        assert 'sys_platform != "win32"' in markers
        assert 'sys_platform == "win32"' in markers
    finally:
        temp_path.unlink()


def test_parse_optional_dependencies() -> None:
    """Test parsing optional-dependencies."""
    pyproject_data = {
        "project": {
            "optional-dependencies": {
                "inference_cpu": [
                    "torch==2.7.1",
                    "ultralytics==8.3.159",
                ]
            }
        }
    }
    packages = parse_optional_dependencies(pyproject_data, ["inference_cpu"])
    package_names = {p.name for p in packages if hasattr(p, "name")}
    # torch has a type stub (types-torch), ultralytics doesn't
    assert "types-torch" in package_names or "torch" in package_names
    assert "ultralytics" in package_names


def test_parse_optional_dependencies_with_marker() -> None:
    """Test parsing optional dependencies with markers."""
    pyproject_data = {
        "project": {
            "optional-dependencies": {
                "inference_cuda": [
                    "torch==2.7.1",
                    'tensorrt==10.12.0.36; sys_platform != "darwin"',
                ]
            }
        }
    }
    packages = parse_optional_dependencies(pyproject_data, ["inference_cuda"])

    # Find tensorrt package
    tensorrt_pkg = None
    for p in packages:
        if hasattr(p, "name") and p.name == "tensorrt":
            tensorrt_pkg = p
            break

    assert tensorrt_pkg is not None
    assert tensorrt_pkg.marker == 'sys_platform != "darwin"'


def test_parse_pyproject_with_optional_extras() -> None:
    """Test full pyproject.toml parsing with optional extras."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(
            """
[project]
dependencies = [
    "requests==2.32.0",
]

[project.optional-dependencies]
inference = [
    "torch==2.7.1",
    "ultralytics==8.3.159",
]
"""
        )
        temp_path = Path(f.name)

    try:
        # Parse without optional extras
        result_without_extras = parse_pyproject_toml(temp_path, optional_extras=None)
        package_names_without = {p.name for p in result_without_extras if hasattr(p, "name")}
        assert "torch" not in package_names_without
        assert "types-torch" not in package_names_without

        # Parse with optional extras
        result_with_extras = parse_pyproject_toml(temp_path, optional_extras=["inference"])
        package_names_with = {p.name for p in result_with_extras if hasattr(p, "name")}
        # torch has a type stub, so it may be types-torch instead
        assert "torch" in package_names_with or "types-torch" in package_names_with
        assert "ultralytics" in package_names_with
    finally:
        temp_path.unlink()


def test_hash_includes_marker() -> None:
    """Test that hash includes marker so platform-specific versions are distinct."""
    pkg1 = NormalPackage(name="numpy", version="2.1.1", marker='sys_platform != "win32"')
    pkg2 = NormalPackage(name="numpy", version="1.26.4", marker='sys_platform == "win32"')
    pkg3 = NormalPackage(name="numpy", version="2.1.1", marker='sys_platform != "win32"')

    # Different markers should have different hashes
    assert hash(pkg1) != hash(pkg2)

    # Same name, version, and marker should have same hash
    assert hash(pkg1) == hash(pkg3)

    # They should be unequal
    assert pkg1 != pkg2

    # They should be equal
    assert pkg1 == pkg3
