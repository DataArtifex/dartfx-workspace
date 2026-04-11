"""
Interactive bash-like shell for dartfx-workspace.
"""

import fnmatch
import os
import shlex
import shutil
import stat
from datetime import datetime
from pathlib import Path

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.tree import Tree

from dartfx.workspace.core import Workspace

console = Console()

app = typer.Typer(help="Dartfx Workspace Management Tools")

COMMANDS = [
    "init",
    "scan",
    "stats",
    "cd",
    "ls",
    "tree",
    "head",
    "tail",
    "pwd",
    "mkdir",
    "mv",
    "cp",
    "rm",
    "exit",
    "quit",
    "clear",
    "help",
    "?",
]
IGNORE_DIRS = {".dartfx", ".git", "__pycache__", "venv", ".venv"}


class ShellContext:
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.cwd = workspace.path

    def relativize(self, p: Path) -> str:
        try:
            val = str(p.relative_to(self.workspace.path))
            return "/" if val == "." else f"/{val}"
        except ValueError:
            return str(p)

    def resolve(self, p_str: str) -> Path:
        if p_str == "/":
            return self.workspace.path
        if p_str.startswith("/"):
            # treat as relative to workspace root
            return self.workspace.path / p_str[1:]
        p = Path(p_str)
        if p.is_absolute():
            return p
        return (self.cwd / p).resolve()


def handle_init(ctx: ShellContext, args: list[str]):
    create_dirs = "--dirs" in args
    Workspace.init(ctx.workspace.path, create_dirs=create_dirs)
    typer.echo(f"Initialized workspace at {ctx.workspace.path}")
    if create_dirs:
        typer.echo("Created standard directories.")


def handle_scan(ctx: ShellContext, _args: list[str]):
    if not ctx.workspace.is_initialized():
        console.print("[red]Workspace not initialized.[/red]")
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task("Scanning workspace...", total=None)

        def update_progress(path: str):
            progress.update(task, description=f"Scanning [cyan]{path}[/cyan]")

        ctx.workspace.scanner.scan(status_callback=update_progress)

    console.print("[green]Scan complete.[/green]")


def handle_stats(ctx: ShellContext, _args: list[str]):
    if not ctx.workspace.is_initialized():
        console.print("[red]Workspace not initialized.[/red]")
        return
    stats = ctx.workspace.stats()

    # Per-Type Table
    table = Table(title="File Type Breakdown", box=None, show_header=True, header_style="bold magenta")
    table.add_column("Type", style="cyan")
    table.add_column("Count", justify="right", style="green")
    table.add_column("Size", justify="right", style="blue")

    for file_type, info in stats.types_info.items():
        if info.count > 0:
            table.add_row(file_type.value, str(info.count), format_size(info.size_bytes))

    # Summary Table
    summary = Table(title="Registration Summary", box=None, show_header=True, header_style="bold yellow")
    summary.add_column("Status", style="bold")
    summary.add_column("Count", justify="right")
    summary.add_column("Size", justify="right")

    summary.add_row("Registered", str(stats.registered_count), format_size(stats.registered_size_bytes))
    summary.add_row("Unregistered", str(stats.unregistered_count), format_size(stats.unregistered_size_bytes))
    summary.add_section()
    summary.add_row("Total", str(stats.total_files), format_size(stats.total_size_bytes), style="bold white")

    console.print(Panel(table, expand=False, border_style="green"))
    console.print(Panel(summary, expand=False, border_style="yellow"))


def handle_cd(ctx: ShellContext, args: list[str]):
    if not args:
        ctx.cwd = ctx.workspace.path
        return

    target = args[0]
    p = ctx.resolve(target)
    if p.is_dir():
        ctx.cwd = p
    else:
        typer.secho(f"cd: no such file or directory: {target}", fg=typer.colors.RED)


def format_size(size_bytes: int) -> str:
    """Formats bytes into human-friendly units."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    size: float = float(size_bytes)
    for unit in ["K", "M", "G", "T", "P"]:
        size /= 1024
        if size < 1024:
            return f"{size:.1f}{unit}"
    return f"{size:.1f}E"


def handle_ls(ctx: ShellContext, args: list[str]):
    show_all = False
    show_uuid = False
    human_readable = False
    new_args = []
    for arg in args:
        if arg in ("-a", "--all"):
            show_all = True
        elif arg == "--uuid":
            show_uuid = True
        elif arg in ("-h", "--human-readable"):
            human_readable = True
        else:
            new_args.append(arg)

    target_str = new_args[0] if new_args else "."

    # Handle glob patterns
    is_glob = any(char in target_str for char in ["*", "?", "["])

    if is_glob:
        p = Path(target_str)
        # If no parent in path, use current working directory (ctx.cwd)
        if len(p.parts) == 1:
            search_dir = ctx.cwd
            pattern = target_str
        else:
            search_dir = ctx.resolve(str(p.parent))
            pattern = p.name

        if not search_dir.exists() or not search_dir.is_dir():
            console.print(f"[red]ls: cannot access '{target_str}': No such directory[/red]")
            return
        items = [item for item in search_dir.iterdir() if fnmatch.fnmatch(item.name, pattern)]
    else:
        target = ctx.resolve(target_str)
        if not target.exists():
            console.print(f"[red]ls: cannot access '{target_str}': No such file or directory[/red]")
            return
        items = [target] if not target.is_dir() else list(target.iterdir())

    # Prepare Knowledge Base data for cross-referencing
    kb_files = {}
    if ctx.workspace.is_initialized():
        try:
            kb_files = {f["path"]: f for f in ctx.workspace.kb.get_all_files()}
        except Exception:
            pass

    def _get_item_info(item: Path):
        is_dir = item.is_dir()
        rel_path = item.relative_to(ctx.workspace.path).as_posix() if ctx.workspace.is_initialized() else ""
        kb_info = kb_files.get(rel_path)

        st = item.stat()
        mode = stat.filemode(st.st_mode)
        size_val = st.st_size
        size_str = format_size(size_val) if human_readable else str(size_val)
        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")

        if is_dir:
            registered = "-"
            file_type = "-"
            file_uuid = "-"
        else:
            registered = "[green]✔[/green]" if kb_info else "[red]✘[/red]"
            ft = kb_info["type"] if kb_info else "-"
            ff = kb_info.get("file_format", "undetermined") if kb_info else ""
            file_type = f"{ft}/{ff}" if ff and ff != "undetermined" else ft
            file_uuid = kb_info["uuid"] if kb_info else "-"

        suffix = "/" if is_dir else ""
        return mode, size_str, mtime, registered, file_type, file_uuid, f"{item.name}{suffix}"

    table = Table(box=None, show_header=True, header_style="bold cyan")
    table.add_column("Mode", style="dim")
    table.add_column("Size", justify="right")
    table.add_column("Modified", style="dim")
    table.add_column("Reg", justify="center")
    table.add_column("Type", style="magenta")
    if show_uuid:
        table.add_column("UUID", style="dim")
    table.add_column("Name", style="bold white")

    for item in sorted(items):
        if not show_all and item.name.startswith("."):
            continue
        info = list(_get_item_info(item))
        if not show_uuid:
            info.pop(5)
        table.add_row(*info)

    console.print(table)


def handle_tree(ctx: ShellContext, args: list[str]):
    target_str = "."
    show_uuid = False
    max_level = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--uuid":
            show_uuid = True
        elif arg in ("-L", "--level") and i + 1 < len(args):
            try:
                max_level = int(args[i + 1])
                i += 1
            except ValueError:
                pass
        elif not arg.startswith("-"):
            target_str = arg
        i += 1

    target = ctx.resolve(target_str)

    if not target.exists() or not target.is_dir():
        console.print(f"[red]tree: '{target_str}' is not a directory or does not exist[/red]")
        return

    kb_files = {}
    if ctx.workspace.is_initialized():
        try:
            kb_files = {f["path"]: f for f in ctx.workspace.kb.get_all_files()}
        except Exception:
            pass

    tree = Tree(f"[bold blue]{target.name}/[/bold blue]")

    def add_to_tree(directory: Path, tree_node: Tree, current_level: int):
        if max_level is not None and current_level >= max_level:
            return

        for path in sorted(directory.iterdir()):
            if path.name.startswith("."):
                continue

            if path.is_dir():
                branch = tree_node.add(f"[bold blue]{path.name}/[/bold blue]")
                add_to_tree(path, branch, current_level + 1)
            else:
                rel_path = path.relative_to(ctx.workspace.path).as_posix() if ctx.workspace.is_initialized() else ""
                kb_info = kb_files.get(rel_path)

                if kb_info:
                    ft = kb_info["type"]
                    ff = kb_info.get("file_format", "undetermined")
                    type_label = f"{ft}/{ff}" if ff and ff != "undetermined" else ft
                    label = f"[green]✔[/green] {path.name} [dim]({type_label})[/dim]"
                    if show_uuid:
                        label += f" [dim blue]<{kb_info['uuid']}>[/dim blue]"
                else:
                    label = f"[red]✘[/red] {path.name}"

                tree_node.add(label)

    add_to_tree(target, tree, 0)
    console.print(tree)


def handle_head(ctx: ShellContext, args: list[str]):
    num_lines = 10
    target_str = None

    i = 0
    while i < len(args):
        if args[i] == "-n" and i + 1 < len(args):
            try:
                num_lines = int(args[i + 1])
                i += 1
            except ValueError:
                pass
        else:
            target_str = args[i]
        i += 1

    if not target_str:
        typer.secho("head: missing operand", fg=typer.colors.RED)
        return

    p = ctx.resolve(target_str)
    if not p.is_file():
        typer.secho(f"head: {target_str}: not a file", fg=typer.colors.RED)
        return

    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for _ in range(num_lines):
                line = f.readline()
                if not line:
                    break
                print(line, end="")
    except Exception as e:
        typer.secho(f"head error: {e}", fg=typer.colors.RED)


def handle_tail(ctx: ShellContext, args: list[str]):
    num_lines = 10
    target_str = None

    i = 0
    while i < len(args):
        if args[i] == "-n" and i + 1 < len(args):
            try:
                num_lines = int(args[i + 1])
                i += 1
            except ValueError:
                pass
        else:
            target_str = args[i]
        i += 1

    if not target_str:
        typer.secho("tail: missing operand", fg=typer.colors.RED)
        return

    p = ctx.resolve(target_str)
    if not p.is_file():
        typer.secho(f"tail: {target_str}: not a file", fg=typer.colors.RED)
        return

    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            for line in lines[-num_lines:]:
                print(line, end="")
    except Exception as e:
        typer.secho(f"tail error: {e}", fg=typer.colors.RED)


def handle_pwd(ctx: ShellContext, _args: list[str]):
    typer.echo(ctx.relativize(ctx.cwd))


def handle_mkdir(ctx: ShellContext, args: list[str]):
    for d in args:
        p = ctx.resolve(d)
        p.mkdir(parents=True, exist_ok=True)


def handle_mv(ctx: ShellContext, args: list[str]):
    if len(args) < 2:
        typer.secho("mv: missing operand", fg=typer.colors.RED)
        return
    src = ctx.resolve(args[0])
    dst = ctx.resolve(args[1])

    if dst.is_dir():
        actual_dst = dst / src.name
    else:
        actual_dst = dst

    try:
        shutil.move(str(src), str(dst))
        # If workspace is initialized, track targeted move
        if ctx.workspace.is_initialized():
            ctx.workspace.scanner.handle_move(src, actual_dst)
    except Exception as e:
        typer.secho(f"mv error: {e}", fg=typer.colors.RED)


def handle_cp(ctx: ShellContext, args: list[str]):
    if len(args) < 2:
        typer.secho("cp: missing operand", fg=typer.colors.RED)
        return
    src = ctx.resolve(args[0])
    dst = ctx.resolve(args[1])

    if dst.is_dir():
        actual_dst = dst / src.name
    else:
        actual_dst = dst

    try:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        if ctx.workspace.is_initialized():
            ctx.workspace.scanner.scan_path(actual_dst)
    except Exception as e:
        typer.secho(f"cp error: {e}", fg=typer.colors.RED)


def handle_rm(ctx: ShellContext, args: list[str]):
    for a in args:
        if a in ["-r", "-rf"]:
            continue
        p = ctx.resolve(a)
        if not p.exists():
            continue
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            if ctx.workspace.is_initialized():
                ctx.workspace.scanner.handle_remove(p)
        except Exception as e:
            typer.secho(f"rm error: {e}", fg=typer.colors.RED)


def handle_clear(_ctx: ShellContext, _args: list[str]):
    os.system("cls" if os.name == "nt" else "clear")


def handle_help(_ctx: ShellContext, _args: list[str]):
    table = Table(title="Available Commands", show_header=True, header_style="bold magenta")
    table.add_column("Command", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")

    help_text = [
        ("init", "Initialize the workspace (use --dirs for standard structure)"),
        ("scan", "Scan workspace and sync to Knowledge Base"),
        ("stats", "Show workspace statistics"),
        ("cd", "Change directory"),
        ("ls", "List directory contents (-a, -h, --uuid, or glob)"),
        ("tree", "Display tree structure (-L level, --uuid)"),
        ("head", "Show first lines of a file (-n number)"),
        ("tail", "Show last lines of a file (-n number)"),
        ("pwd", "Print working directory"),
        ("mkdir", "Create a directory"),
        ("mv", "Move or rename files/directories"),
        ("cp", "Copy files/directories"),
        ("rm", "Remove files/directories"),
        ("clear", "Clear the terminal screen"),
        ("help, ?", "Show this help message"),
        ("exit, quit", "Exit the shell"),
    ]
    help_text.sort()
    for cmd, desc in help_text:
        table.add_row(cmd, desc)

    console.print(table)


COMMAND_HANDLERS = {
    "init": handle_init,
    "scan": handle_scan,
    "stats": handle_stats,
    "cd": handle_cd,
    "ls": handle_ls,
    "tree": handle_tree,
    "head": handle_head,
    "tail": handle_tail,
    "pwd": handle_pwd,
    "mkdir": handle_mkdir,
    "mv": handle_mv,
    "cp": handle_cp,
    "rm": handle_rm,
    "clear": handle_clear,
    "help": handle_help,
    "?": handle_help,
}


@app.command()
def interact(path: str = typer.Argument(".", help="Workspace root directory")):
    """Starts the interactive dartfx shell."""
    ws = Workspace(Path(path))
    ctx = ShellContext(ws)

    completer = WordCompleter(COMMANDS, ignore_case=True)
    session: PromptSession = PromptSession(history=InMemoryHistory())

    console.print(
        Panel("[bold green]Dartfx Workspace Shell[/bold green]", subtitle="Type 'exit' or press Ctrl-C to quit")
    )

    while True:
        try:
            # Format prompt: dartfx [rel_cwd] >
            rel_cwd = ctx.relativize(ctx.cwd)
            p = f"dartfx [{rel_cwd}]> "
            text = session.prompt(p, completer=completer)

            if not text.strip():
                continue

            parts = shlex.split(text)
            cmd = parts[0]
            args = parts[1:]

            if cmd in ["exit", "quit"]:
                if typer.confirm("Are you sure you want to exit?"):
                    break
                continue

            if cmd in COMMAND_HANDLERS:
                COMMAND_HANDLERS[cmd](ctx, args)
            else:
                typer.secho(f"Unknown command: {cmd}", fg=typer.colors.YELLOW)

        except (KeyboardInterrupt, EOFError):
            if typer.confirm("\nAre you sure you want to exit?"):
                break
            continue
        except Exception as e:
            typer.secho(f"Error: {e}", fg=typer.colors.RED)


if __name__ == "__main__":
    app()
