"""
General utilities and provenance/applicability helpers for dartfx-workspace.
"""

from pathlib import Path

SYSTEM_GENERATED_PATTERNS: tuple[tuple[str, str], ...] = (
    (".stats.csv.data.jsonl", "qsv"),
    (".stats.csv.json", "qsv"),
    (".stats.csv", "qsv"),
    (".freqs.long.csv", "qsv"),
    (".freq.long.csv", "qsv"),
    (".freqs.csv", "qsv"),
    ("freq.csv", "qsv"),
    (".schema.json", "qsv"),
    (".description.md", "qsv"),
    (".idx", "qsv"),
    (".readstat.json", "readstat"),
)

SUPPORTED_READSTAT_SUFFIXES: set[str] = {".dta", ".por", ".sav", ".sas7bdat", ".xpt", ".zsav"}
SUPPORTED_FAIRIFY_SUFFIXES: set[str] = {".csv", ".parquet", ".pq"}


def format_size(size_bytes: int) -> str:
    """Formats bytes into human-friendly units (1.2MB, 4.5KB, etc.)."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    size: float = float(size_bytes)
    for unit in ["K", "M", "G", "T", "P"]:
        size /= 1024
        if size < 1024:
            return f"{size:.1f}{unit}"
    return f"{size:.1f}E"


def detect_system_generated(path_or_name: str | Path) -> tuple[bool, str | None]:
    """
    Detect whether a file name/path matches known system-generated artifacts
    (e.g., QSV fairify outputs or ReadStat metadata exports).
    Returns (is_generated, generated_by).
    """
    p = Path(path_or_name)
    name = p.name.lower()
    parent_name = p.parent.name.lower()

    if name == "data.json" and parent_name.endswith(".stats.csv"):
        return True, "qsv"

    for pattern, tool in SYSTEM_GENERATED_PATTERNS:
        if pattern.startswith("."):
            if name.endswith(pattern):
                return True, tool
        else:
            if name == pattern:
                return True, tool

    return False, None


def is_statistical_file(path_or_name: str | Path) -> bool:
    """Check if file has an extension supported by ReadStat / to_csv (SAS, Stata, SPSS)."""
    return Path(path_or_name).suffix.lower() in SUPPORTED_READSTAT_SUFFIXES


def is_fairifiable_file(
    path_or_name: str | Path,
    *,
    is_generated: bool = False,
    file_format: str = "undetermined",
) -> bool:
    """
    Check if a file can be FAIRified.
    Only user-provided CSV or Parquet files can technically be FAIRified.
    System-generated artifacts (e.g., QSV frequencies, stats, schema, idx) cannot be FAIRified.
    """
    if is_generated:
        return False
    gen, _ = detect_system_generated(path_or_name)
    if gen:
        return False
    ext = Path(path_or_name).suffix.lower()
    return ext in SUPPORTED_FAIRIFY_SUFFIXES or file_format.lower() in {"csv", "parquet"}


def get_fairify_artifacts(source_path: Path | str) -> list[Path]:
    """Return all existing candidate fairify artifact paths for a given source tabular file."""
    p = Path(source_path)
    base = p.stem
    name = p.name
    parent = p.parent

    candidates = [
        parent / f"{name}.stats.csv",
        parent / f"{base}.stats.csv",
        parent / f"{name}.schema.json",
        parent / f"{base}.schema.json",
        parent / f"{base}.freqs.csv",
        parent / f"{name}.freqs.csv",
        parent / f"{base}.freqs.long.csv",
        parent / f"{name}.freqs.long.csv",
        parent / f"{name}.idx",
        parent / f"{base}.idx",
        parent / f"{base}.description.md",
        parent / f"{name}.description.md",
    ]
    seen: set[Path] = set()
    existing: list[Path] = []
    for c in candidates:
        if c.exists() and c not in seen:
            seen.add(c)
            existing.append(c)
    return existing


def is_fairify_up_to_date(source_path: Path | str) -> bool:
    """
    Check if fairify has already been executed on source_path AND
    the source file has NOT been modified since the artifacts were generated.
    """
    p = Path(source_path)
    if not p.exists() or not p.is_file():
        return False

    base = p.stem
    name = p.name
    parent = p.parent

    # Core artifacts check: must have stats and (freqs or schema)
    has_stats = (parent / f"{name}.stats.csv").exists() or (parent / f"{base}.stats.csv").exists()
    has_freqs = (parent / f"{base}.freqs.csv").exists() or (parent / f"{name}.freqs.csv").exists()
    has_schema = (parent / f"{name}.schema.json").exists() or (parent / f"{base}.schema.json").exists()

    if not (has_stats and (has_freqs or has_schema)):
        return False

    try:
        src_mtime = p.stat().st_mtime
        artifacts = get_fairify_artifacts(p)
        if not artifacts:
            return False
        # Artifacts must have been generated at or after source file mtime
        return all(art.stat().st_mtime >= src_mtime for art in artifacts)
    except OSError:
        return False


def get_fairify_status(source_path: Path | str, *, is_generated: bool = False) -> str | None:
    """
    Returns the FAIRify lifecycle status of a file:
      - 'up_to_date': fairify has run and artifacts are fresh
      - 'stale': fairify has run previously, but the source file has been modified since
      - 'available': user CSV/Parquet file ready for fairification
      - None: not applicable (e.g. system generated files, statistical files, non-tabular)
    """
    p = Path(source_path)
    if is_generated or detect_system_generated(p)[0]:
        return None
    if p.suffix.lower() not in SUPPORTED_FAIRIFY_SUFFIXES:
        return None

    base = p.stem
    name = p.name
    parent = p.parent

    has_stats = (parent / f"{name}.stats.csv").exists() or (parent / f"{base}.stats.csv").exists()
    has_freqs = (parent / f"{base}.freqs.csv").exists() or (parent / f"{name}.freqs.csv").exists()
    has_schema = (parent / f"{name}.schema.json").exists() or (parent / f"{base}.schema.json").exists()

    if has_stats and (has_freqs or has_schema):
        if is_fairify_up_to_date(p):
            return "up_to_date"
        return "stale"

    return "available"


def compute_applicable_actions(
    path_or_name: str | Path,
    *,
    is_dir: bool = False,
    is_generated: bool = False,
    file_format: str = "undetermined",
    file_type: str = "-",
    full_path: Path | None = None,
) -> list[str]:
    """
    Determine which operations are applicable to a given file or directory.

    Supported actions:
      - 'fairify': applicable ONLY to user-provided CSV / Parquet files when not already up-to-date.
      - 'tocsv': applicable ONLY to ReadStat-supported statistical files (SAS, Stata, SPSS).
      - 'readstat': applicable ONLY to ReadStat-supported statistical files.
      - 'preview': applicable to files.
      - 'download': applicable to files and directories.
      - 'delete': applicable to files and directories.
    """
    _ = file_type
    if is_dir:
        return ["download", "delete"]

    actions: list[str] = []

    # Check statistical conversion commands
    if is_statistical_file(path_or_name):
        actions.append("tocsv")
        actions.append("readstat")

    # Check FAIRification: available for user CSV/Parquet unless already up-to-date
    if is_fairifiable_file(path_or_name, is_generated=is_generated, file_format=file_format):
        if full_path is not None and full_path.exists():
            if not is_fairify_up_to_date(full_path):
                actions.append("fairify")
        else:
            actions.append("fairify")

    actions.append("preview")
    actions.append("download")
    actions.append("delete")

    return actions
