# dartfx-workspace

[![PyPI - Version](https://img.shields.io/pypi/v/dartfx-workspace.svg)](https://pypi.org/project/dartfx-workspace)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/dartfx-workspace.svg)](https://pypi.org/project/dartfx-workspace)
[![CI](https://github.com/DataArtifex/dartfx-workspace/actions/workflows/test.yml/badge.svg)](https://github.com/DataArtifex/dartfx-workspace/actions/workflows/test.yml)
[![License](https://img.shields.io/github/license/DataArtifex/dartfx-workspace.svg)](https://github.com/DataArtifex/dartfx-workspace/blob/main/LICENSE.txt)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/DataArtifex/dartfx-workspace)

**Dartfx Workspace** is a high-performance management tool for data storage areas (workspaces). It focuses on organizing and publishing data commodities aligned with FAIR principles, making them easily consumable by both humans and AI agents.

---

## 🚀 Key Features

- **Interactive Shell**: A powerful, contextual command-line interface for navigating and managing file resources.
- **Semantic Knowledge Base**: Automatic generation of RDF metadata (Turtle) using **Dublin Core** and **Schema.org** (`schema:MediaObject`) standards.
- **Cross-Platform**: Fully tested on macOS, Linux, and Windows with consistent path handling.
- **Dynamic Resource Tracking**: Recognizes renames and moves within the workspace using stable UUIDs and BLAKE3 hashes.
- **AI Readiness**: Designed to work seamlessly with AI agents and MCP servers.

## 🛠 Installation

We recommend using [uv](https://github.com/astral-sh/uv) for fast and reliable dependency management.

```bash
# Clone the repository
git clone https://github.com/DataArtifex/dartfx-workspace.git
cd dartfx-workspace

# Sync environment
uv sync
```

## 🐚 The Interactive Shell

The core of the package is an interactive shell built on `prompt_toolkit`. It provides a Unix-like experience for managing your data assets.

```bash
# Start the shell in the current directory
uv run dartfx-workspace .
```

### Common Commands:
- `init --dirs`: Initialize the workspace and create standard directories (`data/`, `docs/`, `meta/`, etc.)
- `scan`: Perform a deep scan of the filesystem to register files in the Knowledge Base.
- `stats`: Show a breakdown of file types, sizes, and registration status.
- `ls -l -h --uuid`: List files with metadata, human-readable sizes, and stable UUIDs.
- `tree -L 2`: Visualize the directory hierarchy.
- `head / tail -n 20`: Inspect the multi-line content of files.

### Registration Status:
The shell uses visual indicators to show if a file is tracked in the Knowledge Base:
- **✔**: Registered resource with persistent metadata.
- **✘**: Unregistered/new file.

## 🧠 Knowledge Base

The Knowledge Base lives in `.dartfx/kb/turtle/files/`. Each file you register gets its own stable URI:
`https://dataartifex.org/workspace/<UUID>`

We integrate multiple vocabularies for maximum interoperability:
- **DCTERMS**: For standard administrative metadata (identifiers, dates).
- **Schema.org**: Mapped to `MediaObject` to ensure compatibility with major data discovery engines.

## 💻 Development

### Running Tests
```bash
uv run pytest
```

### Pre-commit Hooks
The project uses strict linting and formatting via Ruff. Run hooks before committing:
```bash
uv run pre-commit run --all-files
```

### Documentation
Build the full documentation suite (Sphinx/MyST):
```bash
hatch run docs:build
```

---

## 🗺 Roadmap
- [x] Phase 1: Core Workspace Management & Shell.
- [ ] Phase 2: Data Product Management & DCAT Integration.
- [ ] Phase 3: Advanced Inference Engines & Data Provenance.

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

---
© 2024 Data Artifex | [SPECIFICATIONS.md](./SPECIFICATIONS.md)
