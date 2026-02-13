#!/usr/bin/env python3

import re
import tomllib
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
import yaml
from packaging.requirements import Requirement

REPOSITORIES = "repos"
REPOSITORY = "repo"
MYPY_REPOSITORY = "https://github.com/pre-commit/mirrors-mypy"
HOOKS = "hooks"
ADDITIONAL_DEPENDENCIES = "additional_dependencies"

CAPTURE_GROUP_URL = "url"
CAPTURE_GROUP_PACKAGE = "package"
CAPTURE_GROUP_VERSION = "version"


class AdditionalMypyDependency(ABC):
    @abstractmethod
    def __hash__(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def __eq__(self, other: object) -> bool:
        raise NotImplementedError

    @abstractmethod
    def serialize(self) -> str:
        raise NotImplementedError


class Package(AdditionalMypyDependency):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str | None:
        raise NotImplementedError

    @property
    @abstractmethod
    def marker(self) -> str | None:
        raise NotImplementedError

    def __hash__(self) -> int:
        # Include marker in hash so platform-specific versions are distinct
        return hash((self.name, self.version, self.marker))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Package):
            return False
        return (self.name, self.version, self.marker) == (
            other.name,
            other.version,
            other.marker,
        )


class TypeStubPackage(Package):
    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str | None:
        return self._version

    @property
    def marker(self) -> str | None:
        return self._marker

    def __init__(
        self, name: str, version: str | None, marker: str | None = None
    ) -> None:
        self._name = name
        self._version = version
        self._marker = marker

    def serialize(self) -> str:
        result = self.name
        if self.marker:
            result += f"; {self.marker}"
        return result


class NormalPackage(Package):
    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str | None:
        return self._version

    @property
    def marker(self) -> str | None:
        return self._marker

    def __init__(
        self, name: str, version: str | None, marker: str | None = None
    ) -> None:
        self._name = name
        self._version = version
        self._marker = marker

    def serialize(self) -> str:
        result = self.name
        if self.version:
            result += "==" + self.version
        if self.marker:
            result += f"; {self.marker}"
        return result


@dataclass
class ExtraIndexUrl(AdditionalMypyDependency):
    url: str

    def __hash__(self) -> int:
        return hash(self.url)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ExtraIndexUrl):
            return False
        return self.url == other.url

    def serialize(self) -> str:
        return f"--extra-index-url={self.url}"


class CustomDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super(CustomDumper, self).increase_indent(flow, False)

    def choose_scalar_style(self) -> str:
        # Get the default style choice
        style = super().choose_scalar_style()

        # If the default choice is single quotes, change to double quotes
        if style == "'":
            return '"'

        return style


def parse_multiple_requirements_file(
    files: Iterable[Path],
) -> set[AdditionalMypyDependency]:
    packages = set()
    for _file in files:
        packages.update(parse_requirements_file(_file))
    return packages


def parse_requirement_with_marker(
    requirement_line: str,
) -> AdditionalMypyDependency | None:
    """Parse requirement preserving environment marker.

    Args:
        requirement_line (str): PEP 508 requirement string (e.g.,
            'numpy==2.1.1; sys_platform != "win32"').

    Returns:
        AdditionalDependency | None:  A Package or ExtraIndexUrl object, or None if
            parsing fails.
    """
    # Handle extra-index-url separately
    if match_extra_index_url := pattern_extra_index_url.match(requirement_line):
        return create_extra_index_url(
            match_extra_index_url.group(CAPTURE_GROUP_URL).strip()
        )

    try:
        # Parse as full PEP 508 requirement with potential marker
        req = Requirement(requirement_line)
        package_name = req.name

        # Extract version if specified (assumes == operator)
        version = None
        if req.specifier:
            for spec in req.specifier:
                if spec.operator == "==":
                    version = spec.version
                    break

        # Preserve marker as string
        marker = str(req.marker) if req.marker else None

        return create_package(name=package_name, version=version, marker=marker)
    except Exception:
        # Fallback: use original regex-based parsing without marker
        return parse_requirement(requirement_line)


def parse_pyproject_toml(
    pyproject_file: Path, optional_extras: list[str] | None = None
) -> set[AdditionalMypyDependency]:
    """Parse pyproject.toml and extract package names from dependencies.

    Args:
        pyproject_file (Path): Path to pyproject.toml.
        optional_extras (list[str]): List of optional extras to include
            (e.g., ['inference_cpu']).

    Returns:
        set[AdditionalMypyDependency]: Set of packages to include in mypy's
            additional_dependencies.
    """
    if not pyproject_file.exists():
        return set()

    with open(pyproject_file, "rb") as file:
        pyproject_data = tomllib.load(file)

    packages = set()

    # Extract from [project.dependencies]
    if "project" in pyproject_data and "dependencies" in pyproject_data["project"]:
        for dependency in pyproject_data["project"]["dependencies"]:
            # CHANGED: Use new parser that preserves markers
            package = parse_requirement_with_marker(dependency)
            if package:
                packages.add(package)

    # Extract from [dependency-groups.dev]
    if (
        "dependency-groups" in pyproject_data
        and "dev" in pyproject_data["dependency-groups"]
    ):
        for dependency in pyproject_data["dependency-groups"]["dev"]:
            # CHANGED: Use new parser that preserves markers
            package = parse_requirement_with_marker(dependency)
            if package:
                packages.add(package)

    # NEW: Extract from [project.optional-dependencies] if specified
    if optional_extras:
        optional_packages = parse_optional_dependencies(pyproject_data, optional_extras)
        packages.update(optional_packages)

    return packages


def get_extra_index_urls(
    pyproject_data: dict, extra_names: list[str]
) -> set[ExtraIndexUrl]:
    """Extract extra index URLs for specified optional extras from pyproject.toml.

    Args:
        pyproject_data (dict): Parsed pyproject.toml data.
        extra_names (list[str]): List of extra names (e.g., ['inference_cpu']).

    Returns:
        set[ExtraIndexUrl]: Set of ExtraIndexUrl objects.
    """
    index_urls = set()

    # Get [tool.uv.sources] if it exists (uv-specific config)
    sources = pyproject_data.get("tool", {}).get("uv", {}).get("sources", {})

    # Get [tool.uv.index] if it exists
    indexes = pyproject_data.get("tool", {}).get("uv", {}).get("index", [])
    index_map = {idx.get("name"): idx.get("url") for idx in indexes}

    # Check if any dependencies in the extras reference special indexes
    # This is a heuristic - if package sources reference an index, include that index
    optional_deps = pyproject_data.get("project", {}).get("optional-dependencies", {})

    for extra_name in extra_names:
        if extra_name not in optional_deps:
            continue

        # Get package names from this extra
        for dep in optional_deps[extra_name]:
            package_name = (
                dep.split(";")[0].split("=")[0].split("<")[0].split(">")[0].strip()
            )

            # Check if this package has a custom source
            if package_name in sources:
                source_config = sources[package_name]
                # Handle list of sources
                if isinstance(source_config, list):
                    for src in source_config:
                        if "index" in src:
                            index_name = src["index"]
                            if index_name in index_map:
                                index_urls.add(ExtraIndexUrl(index_map[index_name]))
                # Handle single source
                elif isinstance(source_config, dict) and "index" in source_config:
                    index_name = source_config["index"]
                    if index_name in index_map:
                        index_urls.add(ExtraIndexUrl(index_map[index_name]))

    return index_urls


def parse_optional_dependencies(
    pyproject_data: dict, extra_names: list[str]
) -> set[AdditionalMypyDependency]:
    """Parse specified optional-dependencies extras from pyproject.toml.

    Args:
        pyproject_data (dict): Parsed pyproject.toml data
        extra_names (list[str]): List of extra names to include
            (e.g., ['inference_cpu']).

    Returns:
        set[AdditionalMypyDependency]: Set of packages and extra index URLs from
            the specified extras.
    """
    packages = set()

    optional_deps = pyproject_data.get("project", {}).get("optional-dependencies", {})

    for extra_name in extra_names:
        if extra_name not in optional_deps:
            print(
                f"Warning: Optional extra '{extra_name}' not found in "
                "[project.optional-dependencies]"
            )
            continue

        for dependency in optional_deps[extra_name]:
            package = parse_requirement_with_marker(dependency)
            if package:
                packages.add(package)

    # Add extra index URLs if needed
    index_urls = get_extra_index_urls(pyproject_data, extra_names)
    packages.update(index_urls)

    return packages


def parse_requirements_file(requirements_file: Path) -> set[AdditionalMypyDependency]:
    """Parse requirements.txt and extract package names using regex."""
    if not requirements_file.exists():
        return set()
    with open(requirements_file, "r") as file:
        lines = file.readlines()

    packages = set()
    for line in lines:
        line = line.strip()
        if (
            line and not line.startswith("#") and line != "-r requirements.txt"
        ):  # Ignore empty lines, comments '-r requirements.txt'
            package_name = parse_requirement(line)
            if package_name:
                packages.add(package_name)

    return packages


pattern_package = re.compile(
    r"^(?!--extra-index-url)(?P<package>[a-zA-Z0-9_\-\.]+)(?:[<>=~!]+(?P<version>\S*))?"
)
pattern_extra_index_url = re.compile(r"^--extra-index-url\s+(?P<url>\S+)")


def parse_requirement(requirement_line: str) -> AdditionalMypyDependency | None:
    """Extract package name from a requirement line using regex."""
    # Regex pattern to capture the package name, ignoring version specifiers
    if match_extra_index_url := pattern_extra_index_url.match(requirement_line):
        return create_extra_index_url(
            match_extra_index_url.group(CAPTURE_GROUP_URL).strip()
        )

    match = pattern_package.match(requirement_line)
    if not match:
        return None

    package_name = match.group(CAPTURE_GROUP_PACKAGE).strip()
    if package_version := match.group(CAPTURE_GROUP_VERSION):
        package_version = package_version.strip()

    return create_package(name=package_name, version=package_version)


def create_extra_index_url(url: str) -> AdditionalMypyDependency:
    return ExtraIndexUrl(url)


def create_package(
    name: str, version: str | None, marker: str | None = None
) -> AdditionalMypyDependency:
    """Check if a type stub exists for a given package name and return it."""
    types_package_name = f"types-{name}"
    if __check_types_for_package_exists(types_package_name):
        return create_type_stub_package(
            name=types_package_name, version=version, marker=marker
        )

    # Some packages already provide type stubs with their package
    # If they don't pre-commit mypy won't fail
    return create_normal_package(name=name, version=version, marker=marker)


def __check_types_for_package_exists(package_name: str) -> bool:
    response = requests.get(f"https://pypi.org/pypi/{package_name}/json")
    return response.status_code == 200


def create_type_stub_package(
    name: str, version: str | None, marker: str | None = None
) -> AdditionalMypyDependency:
    return TypeStubPackage(name=name, version=version, marker=marker)


def create_normal_package(
    name: str, version: str | None, marker: str | None = None
) -> AdditionalMypyDependency:
    return NormalPackage(name=name, version=version, marker=marker)


def serialize_packages(packages: Iterable[AdditionalMypyDependency]) -> list[str]:
    """Converts packages to a serializable format."""
    return sorted([package.serialize() for package in packages])


def read_precommit_file(precommit_file: Path) -> dict:
    with open(precommit_file, "r") as stream:
        yaml_config = yaml.safe_load(stream)
    return yaml_config


def update_precommit_config(config: dict, type_stubs: list[str]) -> dict:
    updated_config = deepcopy(config)
    for repo in updated_config[REPOSITORIES]:
        if repo[REPOSITORY] == MYPY_REPOSITORY:
            repo[HOOKS][0][ADDITIONAL_DEPENDENCIES] = type_stubs
            break
    return updated_config


def save_precommit_config(config: dict, save_path: Path) -> None:
    with open(save_path, "w") as yaml_file:
        yaml.dump(
            data=config,
            stream=yaml_file,
            Dumper=CustomDumper,
            explicit_start=True,
            default_flow_style=False,
            sort_keys=False,
        )


def display_available_type_stubs(type_stubs: list[str]) -> None:
    if type_stubs:
        print("\nType stubs that can be added to your pre-commit configuration:")
        for stub in type_stubs:
            print(f"- {stub}")
    else:
        print("\n No type stubs to be added to your pre-commit configuration.")


def type_stubs_have_changed(actual: dict, to_compare: dict) -> bool:
    return actual != to_compare


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Update mypy additional_dependencies in .pre-commit-config.yaml"
    )
    parser.add_argument(
        "--optional-extras",
        type=str,
        default="",
        help=(
            "Comma-separated list of optional-dependencies extras to include for type "
            "checking (e.g., 'inference_cpu' or 'inference_cpu,test_extras')"
        ),
    )
    args = parser.parse_args()

    # Parse optional extras from argument
    optional_extras = None
    if args.optional_extras:
        optional_extras = [
            extra.strip() for extra in args.optional_extras.split(",") if extra.strip()
        ]

    pyproject_file = Path("pyproject.toml")
    requirements_file = Path("requirements.txt")
    requirements_dev_file = Path("requirements-dev.txt")
    precommit_file = Path(".pre-commit-config.yaml")

    # Prefer pyproject.toml if it exists, otherwise fall back to requirements.txt
    if pyproject_file.exists():
        additional_dependencies = parse_pyproject_toml(pyproject_file, optional_extras)
    else:
        additional_dependencies = parse_multiple_requirements_file(
            [requirements_file, requirements_dev_file]
        )

    serializable_dependencies = serialize_packages(additional_dependencies)
    precommit_config = read_precommit_file(precommit_file)
    updated_precommit_config = update_precommit_config(
        precommit_config, serializable_dependencies
    )
    save_precommit_config(updated_precommit_config, precommit_file)


if __name__ == "__main__":
    main()
