#!/usr/bin/env python3
r"""
EF Core Migration Script Generator

Modes:
1. Default: Generate SQL script from last two migrations
   - Automatically detects from/to migrations
   - Output filename: OS-#### from branch/migration name, or timestamp

2. Create mode (--create): Add a new migration and generate SQL script
   - Usage: --create MigrationName
   - Use --no-script to skip SQL generation after creating migration

Requirements:
- Python 3.10+
- dotnet-ef (global or local tool)
- .env file with project configuration
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

OS_TICKET_RE = re.compile(r"\bOS[-_](\d+)\b", re.IGNORECASE)
MIGRATION_FILE_RE = re.compile(r"^(?P<ts>\d{14})_(?P<name>.+)\.cs$", re.IGNORECASE)


def load_env(env_path: Path) -> dict:
    """Load environment variables from .env file."""
    if not env_path.exists():
        raise FileNotFoundError(
            f".env file not found at {env_path}\n"
            f"Copy .env.example to .env and configure your project paths."
        )

    env_vars = {}
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    return env_vars


def run_stream(cmd: List[str], cwd: Path) -> str:
    """Execute command and stream output to console."""
    print(f"\n> {' '.join(cmd)}\n   (cwd: {cwd})")
    proc = subprocess.Popen(
        cmd, cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    out = []
    for line in proc.stdout:
        print(line.rstrip())
        out.append(line)
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"Command failed (exit {ret}): {' '.join(cmd)}")
    return "".join(out)


def try_output(cmd: List[str], cwd: Path) -> str:
    """Execute command and return output, empty string on error."""
    try:
        return subprocess.check_output(cmd, cwd=str(cwd), text=True).strip()
    except Exception:
        return ""

def resolve_path(base: Path, raw: str) -> Path:
    """
    Resolve a path from .env:
    - If raw is an absolute path → return it as Path.
    - If raw is relative → resolve it against the base path.
    """
    p = Path(raw)

    # Case 1: absolute path (C:\..., D:\..., /home/..., etc.)
    if p.is_absolute():
        return p.resolve()

    # Case 2: relative path → attach to repo base
    return (base / p).resolve()

def resolve_ef_mode(repo: Path) -> str:
    """Detect if dotnet-ef is installed globally or locally."""
    if try_output(["dotnet", "ef", "--version"], repo):
        return "global"
    if try_output(["dotnet", "tool", "run", "dotnet-ef", "--version"], repo):
        return "local"
    raise RuntimeError(
        "dotnet-ef not found.\n"
        "Install globally:  dotnet tool install -g dotnet-ef\n"
        "or as local tool:  dotnet new tool-manifest && dotnet tool install dotnet-ef"
    )


def ef_cmd(mode: str, args: List[str]) -> List[str]:
    """Build dotnet-ef command based on installation mode."""
    return (["dotnet", "ef"] if mode == "global" else ["dotnet", "tool", "run", "dotnet-ef"]) + args


def list_migration_files(migrations_dir: Path) -> List[Tuple[str, str]]:
    """Scan migrations directory and return sorted list of (timestamp, name) tuples."""
    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migrations dir not found: {migrations_dir}")

    items: List[Tuple[str, str]] = []
    for p in migrations_dir.glob("*.cs"):
        n = p.name
        if n.endswith("Snapshot.cs") or n.endswith(".Designer.cs"):
            continue
        m = MIGRATION_FILE_RE.match(n)
        if m:
            items.append((m.group("ts"), m.group("name")))
    items.sort(key=lambda x: x[0])
    return items

def add_context_arg(cmd: List[str], context: str | None):
    """Append DbContext argument if provided."""
    if context:
        cmd += ["--context", context]


def git_branch(repo: Path) -> str:
    """Get current git branch name."""
    out = try_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
    return out or ""


def extract_ticket(branch: str, latest_name: str, latest_ts: str) -> str:
    """
    Extract OS ticket number for output filename.
    Priority: branch name > migration name > timestamp
    """
    m = OS_TICKET_RE.search(branch)
    if m:
        return m.group(1)

    m2 = OS_TICKET_RE.search(latest_name)
    if m2:
        return m2.group(1)

    return latest_ts


def main():
    script_dir = Path(__file__).parent
    env_file = script_dir / ".env"

    ap = argparse.ArgumentParser(
        description="EF Core migration script generator. Reads config from .env file.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--create", metavar="NAME", help="Create a new migration (also generates SQL by default)")
    ap.add_argument("--no-script", action="store_true", help="Skip SQL script generation after creating migration")
    ap.add_argument("--revert", action="store_true", help="Generate SQL script to revert (rollback) the last migration")
    ap.add_argument("--from", dest="from_mig", help="Override 'from' migration id")
    ap.add_argument("--to", dest="to_mig", help="Override 'to' migration id")
    ap.add_argument("--ticket", help="Override ticket number for output filename")
    ap.add_argument("--context", help="DbContext name (if multiple contexts exist)")
    ap.add_argument("--idempotent", action="store_true", help="Generate idempotent script")
    ap.add_argument("--skip-build", action="store_true", help="Skip dotnet build step")
    ap.add_argument("--env", default=str(env_file), help="Path to .env file")
    args = ap.parse_args()

    env_vars = load_env(Path(args.env))

    repo = Path(env_vars["REPO_PATH"]).resolve()
    project_path = resolve_path(repo, env_vars["PROJECT_NAME"])
    startup_path = resolve_path(repo, env_vars["STARTUP_PROJECT"])
    migrations_dir = resolve_path(repo, env_vars["MIGRATIONS_DIR"])
    scripts_dir = resolve_path(repo, env_vars["SCRIPTS_DIR"])
    context = args.context or env_vars.get("DBCONTEXT_NAME")

    ef_mode = resolve_ef_mode(repo)

    if args.create:
        migration_name = args.create
        print("\n=== Creating New Migration ===")
        print(f"Repo:            {repo}")
        print(f"Project:         {project_path}")
        print(f"Startup:         {startup_path}")
        print(f"Migration name:  {migration_name}")
        if context:
            print(f"Context:         {context}")
        print("==============================")

        cmd = [
            "migrations", "add", migration_name,
            "--project", str(project_path),
            "--startup-project", str(startup_path)
        ]
        add_context_arg(cmd, context)

        run_stream(ef_cmd(ef_mode, cmd), repo)
        print(f"\n✅ Migration created: {migration_name}")

        if args.no_script:
            print("Skipping SQL script generation (--no-script flag)")
            return

        print("\n=== Generating SQL Script for New Migration ===")

    files = list_migration_files(migrations_dir)
    if len(files) < 2 and not (args.from_mig and args.to_mig):
        if args.create:
            print("⚠️  Only one migration exists. Cannot generate SQL script.")
            return
        raise RuntimeError(f"Need at least two migrations in {migrations_dir}")

    if args.from_mig and args.to_mig:
        from_id = args.from_mig
        to_id = args.to_mig
        latest_ts, latest_name = files[-1] if files else ("latest", "latest")
    else:
        ts_prev, name_prev = files[-2]
        ts_last, name_last = files[-1]
        from_id = f"{ts_prev}_{name_prev}"
        to_id = f"{ts_last}_{name_last}"
        latest_ts, latest_name = ts_last, name_last

    if args.revert:
        print("\n=== REVERT MODE ===")
        print("Generating reverse SQL (rollback) script")
        print(f"Swapping FROM ({from_id}) and TO ({to_id})\n")
        from_id, to_id = to_id, from_id

    ticket = args.ticket or extract_ticket(git_branch(repo), latest_name, latest_ts)
    suffix = "_revert" if args.revert else ""
    output_sql = scripts_dir / f"{ticket}{suffix}.sql"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    print("\n=== Generating SQL Script ===")
    print(f"Repo:            {repo}")
    print(f"Project:         {project_path}")
    print(f"Startup:         {startup_path}")
    print(f"Migrations dir:  {migrations_dir}")
    print(f"Scripts dir:     {scripts_dir}")
    print(f"From migration:  {from_id}")
    print(f"To migration:    {to_id}")
    print(f"Ticket:          {ticket}")
    print(f"Output SQL:      {output_sql}")
    if context:
        print(f"Context:         {context}")
    print("=============================")

    if not args.skip_build:
        run_stream(["dotnet", "build", str(startup_path)], repo)

    cmd = [
        "migrations", "script", from_id, to_id,
        "--project", str(project_path),
        "--startup-project", str(startup_path),
        "--output", str(output_sql)
    ]
    add_context_arg(cmd, context)

    if args.idempotent:
        cmd += ["--idempotent"]

    try:
        run_stream(ef_cmd(ef_mode, cmd), repo)
    except Exception:
        cmd.append("--no-build")
        run_stream(ef_cmd(ef_mode, cmd), repo)

    print(f"\n✅ SQL script generated: {output_sql}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)
