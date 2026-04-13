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

- **Targeted Scanning**: Sync the full workspace or target specific subdirectories with `scan .` for high-performance indexing.
- **Interactive Metadata**: Minimalist `about` command with clickable links to resource-mirrored metadata storage.
- **Robust Persistence**: Atomic Knowledge Base updates for `mv` and `rm` operations, ensuring stable UUIDs across directory renames.
- **Context-Free Classification**: Scientific-grade file type sniffing relying on signatures (SQL, JSONL, SAS, etc.) rather than directory hints.
- **FAIR-Aligned**: Seamless generation of RDF metadata (Turtle) using **Dublin Core** and **Schema.org** standards.

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
- `scan [path]`: Sync the Knowledge Base. Defaults to the current directory and below.
- `stats`: Show a high-level breakdown of file types (Data, Code, Docs) and registration status.
- `ls -l --uuid`: List files with stable UUIDs and registration status (✔/✘).
- `about <file>`: Show detailed FAIR metadata. Includes a clickable 📂 icon that opens the mirrored storage directory.
- `mv / rm`: Standard filesystem operations that automatically update the semantic graph.
- `tree -L 2`: Visualize the directory hierarchy.

## 🧠 Knowledge Base

The Knowledge Base is mirrored at `.dartfx/kb/workspace/`. Each resource has a dedicated directory containing its `resources.ttl` file, making it accessible to external RDF tools and AI agents.
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
