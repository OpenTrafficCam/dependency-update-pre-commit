# dependency-update-pre-commit

A pre-commit hook that automatically updates mypy's `additional_dependencies` in your `.pre-commit-config.yaml` with the appropriate type stubs based on your project dependencies.

## Features

- **Automatic type stub detection**: Checks PyPI for available type stubs (`types-*` packages) for your dependencies
- **Multiple dependency sources**: Supports both `pyproject.toml` and `requirements.txt` files
- **Platform-specific dependencies**: Handles conditional dependencies (e.g., `pywin32==310; sys_platform == 'win32'`)
- **Preserves YAML formatting**: Updates your pre-commit config while maintaining proper YAML structure

## Installation

Add this to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/OpenTrafficCam/dependency-update-pre-commit
    rev: v0.1.0
    hooks:
      - id: update-mypy-dependencies
```

## Usage

The hook automatically runs when you modify:
- `pyproject.toml`
- `requirements.txt`
- `requirements-dev.txt`

It will:
1. Parse your project dependencies from `pyproject.toml` (preferred) or requirements files
2. Check PyPI for available type stub packages
3. Update the `additional_dependencies` in your mypy hook configuration

### Manual execution

You can also run the hook manually:

```bash
pre-commit run update-mypy-dependencies --all-files
```

Or run the script directly:

```bash
python update_mypy_dependencies.py
```

## Dependency Sources

### pyproject.toml (Preferred)

The hook reads dependencies from:
- `[project.dependencies]` - Production dependencies
- `[dependency-groups.dev]` - Development dependencies (PEP 735 format)

Example:
```toml
[project]
dependencies = [
    "requests==2.32.0",
    "pandas==2.0.0",
]

[dependency-groups]
dev = [
    "pytest==8.0.0",
]
```

### requirements.txt (Fallback)

If `pyproject.toml` is not found, the hook reads from:
- `requirements.txt`
- `requirements-dev.txt`

## How it Works

1. **Dependency Parsing**: Extracts package names and versions from your dependency files
2. **Type Stub Lookup**: For each package, checks if a corresponding `types-{package}` exists on PyPI
3. **Config Update**: Updates the `additional_dependencies` list in the mypy hook section of `.pre-commit-config.yaml`

### Example

Given these dependencies in `pyproject.toml`:
```toml
dependencies = [
    "requests==2.32.0",
    "pandas==2.0.0",
]
```

The hook will update your `.pre-commit-config.yaml`:
```yaml
- repo: https://github.com/pre-commit/mirrors-mypy
  rev: v1.8.0
  hooks:
    - id: mypy
      additional_dependencies:
        - pandas==2.0.0
        - requests==2.32.0
        - types-requests  # Type stub found on PyPI
```

## Requirements

- Python >= 3.11
- PyYAML >= 6.0
- requests >= 2.31.0

## License

GPL-3.0-only

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

If you encounter any issues, please file a bug report at:
https://github.com/OpenTrafficCam/dependency-update-pre-commit/issues
