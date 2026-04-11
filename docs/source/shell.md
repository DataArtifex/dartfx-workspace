# Interactive Shell User Guide

The `dartfx-workspace` package includes a powerful, interactive bash-like shell designed for managing FAIR data workspaces. It combines standard filesystem operations with deep integration into the RDF Knowledge Base.

## Starting the Shell

To enter the interactive shell, run the following command from your terminal:

```bash
uv run dartfx-workspace [path]
```

If no path is provided, it defaults to the current directory.

---

## Core Workspace Commands

### `init`
Initializes a new workspace by creating the `.dartfx` metadata directory.
*   **Flags**:
    *   `--dirs`: Automatically creates a standard recommended directory structure (`data/`, `docs/`, `code/`, `meta/`, `work/`).

### `scan`
Scans the entire workspace and synchronizes file metadata with the RDF Knowledge Base. It identifies new files, tracks renames/moves (via BLAKE3 hashes), and removes stale registration entries.

### `stats`
Displays a comprehensive breakdown of the workspace, including:
*   A **File Type Breakdown** table showing counts and total disk space per type (data, code, metadata, etc.).
*   A **Registration Summary** comparing "Registered" vs. "Unregistered" files.

---

## File Navigation and Inspection

### `ls`
Lists directory contents with advanced metadata overlays.
*   **Flags**:
    *   `-l`, `--long`: Show a detailed table including mode, size, modification time, registration status, and detected type.
    *   `-a`, `--all`: Include hidden files (names starting with `.`).
    *   `-h`, `--human-readable`: Display file sizes in friendly units (KB, MB, GB).
    *   `--uuid`: Show the stable UUID for registered files. (Prefix in short format, dedicated column in long format).
*   **Patterns**: supports glob matching (e.g., `ls data/*.csv` or `ls *.ttl`).
*   **Visual Cues**: In short format, registered files are prefixed with a green **✔**, and unregistered files with a red **✘**.

### `tree`
Recursively displays the directory structure as a visual tree.
*   **Flags**:
    *   `-L <level>`: Limit the recursion depth (e.g., `tree -L 1`).
    *   `--uuid`: Append the stable UUID to registered file labels.
*   **Filtering**: Automatically suppresses hidden directories and standard system folders like `.git` or `.venv`.

### `head` and `tail`
Quickly inspect the contents of a file.
*   **Flags**:
    *   `-n <number>`: Number of lines to display (default is 10).
    *   Example: `head -n 20 data.csv`

---

## Standard Filesystem Operations

The shell provides standard utilities that operate relative to the workspace root (`/`):

*   **`cd <dir>`**: Change the current working directory.
*   **`pwd`**: Print the current working directory relative to the workspace root.
*   **`mkdir <dir>`**: Create new directories.
*   **`mv <src> <dst>`**: Move or rename files/directories.
*   **`cp <src> <dst>`**: Copy files or directories.
*   **`rm <path>`**: Remove files or directories.

---

## Utility Commands

*   **`clear`**: Clears the terminal screen.
*   **`help`** or **`?`**: Displays a summary of all available commands.
*   **`exit`** or **`quit`**: Terminate the shell session. (Includes a safety confirmation prompt).

---

## Visual Legend
*   **✔ (Green)**: File is indexed and registered in the RDF Knowledge Base.
*   **✘ (Red)**: File exists on disk but is not yet registered (run `scan` to index).
*   **[dim](type)**: The detected classification of the file (e.g., `data`, `code`).
*   **Bold Blue**: Indicates a directory.
