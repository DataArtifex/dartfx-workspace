"""
Programmatic task runners and async event streaming protocol for dartfx-workspace.
"""

import asyncio
import importlib.util
import os
import shutil
import subprocess
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from dartfx.workspace.core import Workspace
from dartfx.workspace.models import TaskEvent, TaskStatus, TaskType
from dartfx.workspace.utils import (
    SUPPORTED_FAIRIFY_SUFFIXES as SUPPORTED_QSV_FAIRIFY_SUFFIXES,
)
from dartfx.workspace.utils import (
    SUPPORTED_READSTAT_SUFFIXES as SUPPORTED_READSTAT_INPUT_SUFFIXES,
)
from dartfx.workspace.utils import (
    detect_system_generated,
    is_fairify_up_to_date,
)

EventCallback = Callable[[TaskEvent], None]
CancelCheck = Callable[[], bool]


def detect_installed_tools() -> dict[str, dict[str, str | bool | None]]:
    """Inspect external CLI tools and optional analytical libraries in the runtime environment."""
    tools: dict[str, dict[str, str | bool | None]] = {}
    for binary in ("qsv", "readstat", "extract_metadata"):
        path = shutil.which(binary)
        version: str | None = None
        if path and binary == "qsv":
            try:
                res = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5, check=False)
                if res.returncode == 0:
                    version = (res.stdout or res.stderr).strip().splitlines()[0]
            except Exception:
                version = None
        tools[binary] = {"available": bool(path), "path": path, "version": version}

    for mod_name in ("polars", "duckdb", "pyreadstat"):
        spec = importlib.util.find_spec(mod_name)
        tools[mod_name] = {"available": spec is not None, "path": None, "version": None}

    return tools


def _emit(
    on_event: EventCallback | None,
    *,
    task_id: str,
    workspace_id: str,
    task_type: TaskType,
    status: TaskStatus,
    progress_pct: float = 0.0,
    current_step: str = "",
    log_line: str | None = None,
    result: dict[str, str | int | float | bool | list[str] | None] | None = None,
    error: str | None = None,
) -> TaskEvent:
    event = TaskEvent(
        task_id=task_id,
        workspace_id=workspace_id,
        task_type=task_type,
        status=status,
        progress_pct=progress_pct,
        current_step=current_step,
        log_line=log_line,
        result=result,
        error=error,
    )
    if on_event is not None:
        on_event(event)
    return event


def run_scan_task(
    ws: Workspace,
    task_id: str,
    workspace_id: str,
    *,
    target_path: str = ".",
    clean: bool = False,
    on_event: EventCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> TaskEvent:
    """Execute a workspace scan and KB synchronization emitting structured TaskEvents."""
    _emit(
        on_event,
        task_id=task_id,
        workspace_id=workspace_id,
        task_type=TaskType.SCAN,
        status=TaskStatus.RUNNING,
        progress_pct=5.0,
        current_step="Initializing scan",
        log_line=f"Starting scan on target '{target_path}' (clean={clean})",
    )

    try:
        if not ws.is_initialized():
            raise RuntimeError("Workspace is not initialized.")

        resolved_target = ws.resolve_safe_path(target_path)
        if not resolved_target.exists():
            raise FileNotFoundError(f"Scan target not found: {target_path}")

        if clean:
            ws.kb.wipe()
            _emit(
                on_event,
                task_id=task_id,
                workspace_id=workspace_id,
                task_type=TaskType.SCAN,
                status=TaskStatus.RUNNING,
                progress_pct=15.0,
                current_step="Wiped Knowledge Base",
                log_line="Knowledge Base wiped for clean refresh.",
            )

        scanned_files: list[str] = []

        def _status_cb(rel_path_str: str) -> None:
            if cancel_check and cancel_check():
                raise InterruptedError("Scan task cancelled.")
            scanned_files.append(rel_path_str)
            _emit(
                on_event,
                task_id=task_id,
                workspace_id=workspace_id,
                task_type=TaskType.SCAN,
                status=TaskStatus.RUNNING,
                progress_pct=min(90.0, 20.0 + len(scanned_files) * 2.0),
                current_step=f"Scanning {rel_path_str}",
                log_line=f"Indexed: {rel_path_str}",
            )

        ws.scanner.scan(target_path=resolved_target, status_callback=_status_cb)
        stats = ws.stats()

        return _emit(
            on_event,
            task_id=task_id,
            workspace_id=workspace_id,
            task_type=TaskType.SCAN,
            status=TaskStatus.COMPLETED,
            progress_pct=100.0,
            current_step="Scan complete",
            log_line=f"Scan complete: {stats.registered_count} registered files ({stats.total_size_bytes} bytes).",
            result={
                "scanned_count": len(scanned_files),
                "registered_count": stats.registered_count,
                "total_files": stats.total_files,
                "total_size_bytes": stats.total_size_bytes,
            },
        )
    except InterruptedError as exc:
        return _emit(
            on_event,
            task_id=task_id,
            workspace_id=workspace_id,
            task_type=TaskType.SCAN,
            status=TaskStatus.CANCELLED,
            progress_pct=100.0,
            current_step="Cancelled",
            log_line=str(exc),
            error=str(exc),
        )
    except Exception as exc:
        return _emit(
            on_event,
            task_id=task_id,
            workspace_id=workspace_id,
            task_type=TaskType.SCAN,
            status=TaskStatus.FAILED,
            progress_pct=100.0,
            current_step="Scan failed",
            log_line=f"Error: {exc}",
            error=str(exc),
        )


def run_fairify_task(
    ws: Workspace,
    task_id: str,
    workspace_id: str,
    *,
    source_rel_path: str,
    describe: bool = False,
    force: bool = False,
    on_event: EventCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> TaskEvent:
    """Execute the qsv fairify workflow on a workspace tabular file emitting TaskEvents."""
    _emit(
        on_event,
        task_id=task_id,
        workspace_id=workspace_id,
        task_type=TaskType.FAIRIFY,
        status=TaskStatus.RUNNING,
        progress_pct=5.0,
        current_step="Validating fairify inputs",
        log_line=f"Preparing fairify on '{source_rel_path}' (describe={describe}, force={force})",
    )

    try:
        source_path = ws.resolve_safe_path(source_rel_path)
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"Source file not found: {source_rel_path}")
        if not os.access(source_path, os.R_OK):
            raise PermissionError(f"Source file is not readable: {source_rel_path}")
        if source_path.suffix.lower() not in SUPPORTED_QSV_FAIRIFY_SUFFIXES:
            allowed = "|".join(ext.lstrip(".") for ext in sorted(SUPPORTED_QSV_FAIRIFY_SUFFIXES))
            raise ValueError(f"Unsupported source type '{source_path.suffix}'. Expected one of: {allowed}")

        source_is_gen, _ = detect_system_generated(source_path)
        if ws.is_initialized():
            source_kb = ws.kb.get_file_by_path(source_path.relative_to(ws.path).as_posix())
            if source_kb and source_kb.get("is_generated"):
                source_is_gen = True

        if source_is_gen:
            raise ValueError(
                f"Cannot fairify system-generated artifact '{source_rel_path}'. "
                "Only user-provided tabular files can be FAIRified."
            )

        if is_fairify_up_to_date(source_path) and not force:
            raise ValueError(
                f"File '{source_rel_path}' has already been FAIRified and has not changed "
                "since artifacts were generated. Pass force=True to re-run."
            )

        qsv_bin = shutil.which("qsv")
        if not qsv_bin:
            raise RuntimeError("qsv command not found. Install qsv and try again.")

        if describe and not os.getenv("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY environment variable is required with describe=True.")

        base_name = source_path.stem
        source_filename = source_path.name
        freqs_file = source_path.with_name(f"{base_name}.freqs.csv")
        freqs_long_file = source_path.with_name(f"{base_name}.freqs.long.csv")
        describegpt_file = source_path.with_name(f"{base_name}.description.md")
        schema_file = source_path.with_name(f"{source_filename}.schema.json")
        stats_file = source_path.with_name(f"{source_filename}.stats.csv")
        stats_data_jsonl_file = source_path.with_name(f"{source_filename}.stats.csv.data.jsonl")
        stats_json_file = source_path.with_name(f"{source_filename}.stats.csv.json")

        commands: list[tuple[str, list[str]]] = [
            ("index", [qsv_bin, "index", str(source_path)]),
            ("stats", [qsv_bin, "stats", "-E", "--stats-jsonl", "--infer-dates", "--infer-boolean", str(source_path)]),
            ("moarstats", [qsv_bin, "moarstats", "--advanced", str(source_path)]),
            ("schema", [qsv_bin, "schema", str(source_path)]),
            (
                "frequency",
                [
                    qsv_bin,
                    "frequency",
                    "--limit",
                    "0",
                    "--unq-limit",
                    "1",
                    "--output",
                    str(freqs_file),
                    str(source_path),
                ],
            ),
            ("transpose", [qsv_bin, "transpose", "--long", "1", "--output", str(freqs_long_file), str(freqs_file)]),
        ]

        should_run_describe = False
        if describe:
            if not describegpt_file.exists():
                should_run_describe = True
            else:
                try:
                    should_run_describe = source_path.stat().st_mtime > describegpt_file.stat().st_mtime
                except OSError:
                    should_run_describe = True

        if should_run_describe:
            commands.append(
                (
                    "describegpt",
                    [
                        qsv_bin,
                        "describegpt",
                        str(source_path),
                        "-u",
                        "https://generativelanguage.googleapis.com/v1beta/openai",
                        "-m",
                        "gemini-3-flash-preview",
                        "-k",
                        os.getenv("GEMINI_API_KEY", ""),
                        "--quiet",
                        "--all",
                        "--fresh",
                        "--output",
                        str(describegpt_file),
                    ],
                )
            )

        total_steps = len(commands)
        for idx, (step_name, cmd) in enumerate(commands, start=1):
            if cancel_check and cancel_check():
                raise InterruptedError("Fairify task cancelled.")

            pct = round(10.0 + (idx - 1) * (80.0 / total_steps), 1)
            _emit(
                on_event,
                task_id=task_id,
                workspace_id=workspace_id,
                task_type=TaskType.FAIRIFY,
                status=TaskStatus.RUNNING,
                progress_pct=pct,
                current_step=f"Running qsv {step_name}",
                log_line=f"Executing: qsv {step_name} ({idx}/{total_steps})",
            )

            proc = subprocess.run(cmd, cwd=source_path.parent, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                err_detail = (proc.stderr or proc.stdout or "").strip()
                raise RuntimeError(f"qsv {step_name} failed with status {proc.returncode}: {err_detail}")

        generated_files = [
            source_path.with_name(f"{source_path.name}.idx"),
            schema_file,
            stats_file,
            stats_data_jsonl_file,
            stats_json_file,
            freqs_file,
            freqs_long_file,
        ]
        if describe:
            generated_files.append(describegpt_file)

        indexed_rel_paths: list[str] = []
        for file_path in generated_files:
            if not file_path.exists() or not file_path.is_file():
                continue
            if ws.is_initialized() and file_path.is_relative_to(ws.path):
                ws.scanner.scan_path(file_path, is_generated=True, generated_by="qsv")
            if file_path.is_relative_to(ws.path):
                indexed_rel_paths.append(file_path.relative_to(ws.path).as_posix())

        return _emit(
            on_event,
            task_id=task_id,
            workspace_id=workspace_id,
            task_type=TaskType.FAIRIFY,
            status=TaskStatus.COMPLETED,
            progress_pct=100.0,
            current_step="Fairify complete",
            log_line=f"Generated and indexed {len(indexed_rel_paths)} artifacts.",
            result={
                "source": source_path.relative_to(ws.path).as_posix(),
                "generated_files": indexed_rel_paths,
            },
        )
    except InterruptedError as exc:
        return _emit(
            on_event,
            task_id=task_id,
            workspace_id=workspace_id,
            task_type=TaskType.FAIRIFY,
            status=TaskStatus.CANCELLED,
            progress_pct=100.0,
            current_step="Cancelled",
            log_line=str(exc),
            error=str(exc),
        )
    except Exception as exc:
        return _emit(
            on_event,
            task_id=task_id,
            workspace_id=workspace_id,
            task_type=TaskType.FAIRIFY,
            status=TaskStatus.FAILED,
            progress_pct=100.0,
            current_step="Fairify failed",
            log_line=f"Error: {exc}",
            error=str(exc),
        )


def run_readstat_task(
    ws: Workspace,
    task_id: str,
    workspace_id: str,
    *,
    source_rel_path: str,
    output_rel_path: str | None = None,
    extract_metadata: bool = False,
    force: bool = False,
    on_event: EventCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> TaskEvent:
    """Execute readstat conversion or extract_metadata emitting structured TaskEvents."""
    _emit(
        on_event,
        task_id=task_id,
        workspace_id=workspace_id,
        task_type=TaskType.READSTAT,
        status=TaskStatus.RUNNING,
        progress_pct=10.0,
        current_step="Validating readstat inputs",
        log_line=f"Preparing readstat on '{source_rel_path}' (extract_metadata={extract_metadata})",
    )

    try:
        if cancel_check and cancel_check():
            raise InterruptedError("ReadStat task cancelled.")

        source_path = ws.resolve_safe_path(source_rel_path)
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"Source file not found: {source_rel_path}")
        if source_path.suffix.lower() not in SUPPORTED_READSTAT_INPUT_SUFFIXES:
            allowed = "|".join(ext.lstrip(".") for ext in sorted(SUPPORTED_READSTAT_INPUT_SUFFIXES))
            raise ValueError(f"Unsupported source type '{source_path.suffix}'. Expected one of: {allowed}")

        if extract_metadata:
            bin_path = shutil.which("extract_metadata")
            if not bin_path:
                raise RuntimeError("extract_metadata command not found. Install readstat and try again.")
            target_rel = output_rel_path or f"{source_rel_path}.readstat.json"
        else:
            bin_path = shutil.which("readstat")
            if not bin_path:
                raise RuntimeError("readstat command not found. Install readstat and try again.")
            target_rel = output_rel_path

        out_path: Path | None = ws.resolve_safe_path(target_rel) if target_rel else None
        if out_path is not None and out_path.exists():
            if out_path.is_dir():
                raise IsADirectoryError(f"Target path is a directory: {target_rel}")
            if not force:
                raise FileExistsError(f"Output file already exists: {target_rel}. Use force=True to overwrite.")
            out_path.unlink()

        cmd = [bin_path, str(source_path)]
        if out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            cmd.append(str(out_path))

        _emit(
            on_event,
            task_id=task_id,
            workspace_id=workspace_id,
            task_type=TaskType.READSTAT,
            status=TaskStatus.RUNNING,
            progress_pct=50.0,
            current_step="Running readstat subprocess",
            log_line=f"Executing: {' '.join(cmd)}",
        )

        proc = subprocess.run(cmd, cwd=source_path.parent, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            err_detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"readstat exited with status {proc.returncode}: {err_detail}")

        indexed_output: str | None = None
        if out_path is not None and out_path.exists() and out_path.is_file():
            if ws.is_initialized() and out_path.is_relative_to(ws.path):
                gen_flag = True if extract_metadata else False
                ws.scanner.scan_path(out_path, is_generated=gen_flag, generated_by="readstat")
            if out_path.is_relative_to(ws.path):
                indexed_output = out_path.relative_to(ws.path).as_posix()

        stdout_text = (proc.stdout or "").strip()
        return _emit(
            on_event,
            task_id=task_id,
            workspace_id=workspace_id,
            task_type=TaskType.READSTAT,
            status=TaskStatus.COMPLETED,
            progress_pct=100.0,
            current_step="ReadStat complete",
            log_line=f"ReadStat completed successfully{f' -> {indexed_output}' if indexed_output else ''}.",
            result={
                "source": source_path.relative_to(ws.path).as_posix(),
                "output": indexed_output,
                "stdout": stdout_text[:4000] if stdout_text else None,
            },
        )
    except InterruptedError as exc:
        return _emit(
            on_event,
            task_id=task_id,
            workspace_id=workspace_id,
            task_type=TaskType.READSTAT,
            status=TaskStatus.CANCELLED,
            progress_pct=100.0,
            current_step="Cancelled",
            log_line=str(exc),
            error=str(exc),
        )
    except Exception as exc:
        return _emit(
            on_event,
            task_id=task_id,
            workspace_id=workspace_id,
            task_type=TaskType.READSTAT,
            status=TaskStatus.FAILED,
            progress_pct=100.0,
            current_step="ReadStat failed",
            log_line=f"Error: {exc}",
            error=str(exc),
        )


def run_tocsv_task(
    ws: Workspace,
    task_id: str,
    workspace_id: str,
    *,
    source_rel_path: str,
    force: bool = False,
    on_event: EventCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> TaskEvent:
    """Convert a supported statistical file to CSV via readstat emitting TaskEvents."""
    try:
        source_path = ws.resolve_safe_path(source_rel_path)
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"Source file not found: {source_rel_path}")
        if source_path.suffix.lower() not in SUPPORTED_READSTAT_INPUT_SUFFIXES:
            allowed = "|".join(ext.lstrip(".") for ext in sorted(SUPPORTED_READSTAT_INPUT_SUFFIXES))
            raise ValueError(f"Unsupported source type '{source_path.suffix}'. Expected one of: {allowed}")

        target_rel = source_path.with_suffix(".csv").relative_to(ws.path).as_posix()

        def _forward_event(ev: TaskEvent) -> None:
            if on_event is not None:
                on_event(ev.model_copy(update={"task_type": TaskType.TOCSV}))

        final_ev = run_readstat_task(
            ws,
            task_id=task_id,
            workspace_id=workspace_id,
            source_rel_path=source_rel_path,
            output_rel_path=target_rel,
            extract_metadata=False,
            force=force,
            on_event=_forward_event,
            cancel_check=cancel_check,
        )
        return final_ev.model_copy(update={"task_type": TaskType.TOCSV})
    except Exception as exc:
        return _emit(
            on_event,
            task_id=task_id,
            workspace_id=workspace_id,
            task_type=TaskType.TOCSV,
            status=TaskStatus.FAILED,
            progress_pct=100.0,
            current_step="ToCSV failed",
            log_line=f"Error: {exc}",
            error=str(exc),
        )


async def stream_task(fn: Callable[..., TaskEvent], *args: Any, **kwargs: Any) -> AsyncIterator[TaskEvent]:
    """Run any synchronous task runner in a worker thread and asynchronously stream its TaskEvents."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[TaskEvent | None] = asyncio.Queue()
    user_callback = kwargs.pop("on_event", None)

    def _on_event(event: TaskEvent) -> None:
        if user_callback is not None:
            user_callback(event)
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def _runner() -> None:
        try:
            fn(*args, on_event=_on_event, **kwargs)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    task = asyncio.create_task(asyncio.to_thread(_runner))
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
    finally:
        await task
