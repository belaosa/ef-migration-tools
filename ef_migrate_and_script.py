#!/usr/bin/env python3
"""
Enhanced EF Core Migration Script
---------------------------------
- Dynamically choose between multiple environment files (e.g., wms.env, uc.env)
- Remembers last choice via .last_env
- Same functionality as before (migration creation and SQL generation)
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

# Regex definitions
OS_TICKET_RE = re.compile(r"\bOS[-_](\d+)\b", re.IGNORECASE)
MIGRATION_FILE_RE = re.compile(r"^(?P<ts>\d{14})_(?P<name>.+)\.cs$", re.IGNORECASE)

# ---------- Utility Functions ----------

def color(text, color_code): return f"\033[{color_code}m{text}\033[0m"
def green(text): return color(text, "92")
def yellow(text): return color(text, "93")
def red(text): return color(text, "91")
def cyan(text): return color(text, "96")

def load_env(env_path: Path) -> dict:
    if not env_path.exists():
        raise FileNotFoundError(f".env file not found at {env_path}")
    env_vars = {}
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    return env_vars


def choose_env_file(script_dir: Path) -> Path:
    """Prompt user to select which env file to use (e.g., wms.env, uc.env)."""
    env_files = list(script_dir.glob("*.env"))
    if not env_files:
        raise RuntimeError("No .env files found in the current directory!")

    last_env_file = script_dir / ".last_env"
    last_used = last_env_file.read_text().strip() if last_env_file.exists() else None

    print(cyan("\n🔧 Available environment files:"))
    for idx, f in enumerate(env_files, start=1):
        print(f"  {idx}. {f.name}" + ("  ✅ (last used)" if f.name == last_used else ""))

    choice = input(yellow(f"\nSelect environment [1-{len(env_files)}] or press Enter for last ({last_used}): ")).strip()

    if choice == "" and last_used:
        chosen = script_dir / last_used
    else:
        try:
            chosen = env_files[int(choice) - 1]
        except Exception:
            raise RuntimeError("Invalid selection.")

    # Save for next run
    last_env_file.write_text(chosen.name)
    print(green(f"\n✅ Using environment file: {chosen.name}"))
    return chosen


def run_stream(cmd: List[str], cwd: Path) -> str:
    print(cyan(f"\n> {' '.join(cmd)}\n   (cwd: {cwd})"))
    proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = []
    for line in proc.stdout:
        print(line.rstrip())
        out.append(line)
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(red(f"Command failed (exit {ret}): {' '.join(cmd)}"))
    return "".join(out)


def try_output(cmd: List[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(cmd, cwd=str(cwd), text=True).strip()
    except Exception:
        return ""


def resolve_ef_mode(repo: Path) -> str:
    if try_output(["dotnet", "ef", "--version"], repo):
        return "global"
    if try_output(["dotnet", "tool", "run", "dotnet-ef", "--version"], repo):
        return "local"
    raise RuntimeError(red("dotnet-ef not found. Install it globally or locally."))


def ef_cmd(mode: str, args: List[str]) -> List[str]:
    return (["dotnet", "ef"] if mode == "global" else ["dotnet", "tool", "run", "dotnet-ef"]) + args


def list_migration_files(migrations_dir: Path) -> List[Tuple[str, str]]:
    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migrations dir not found: {migrations_dir}")
    items = []
    for p in migrations_dir.glob("*.cs"):
        n = p.name
        if n.endswith("Snapshot.cs") or n.endswith(".Designer.cs"):
            continue
        m = MIGRATION_FILE_RE.match(n)
        if m:
            items.append((m.group("ts"), m.group("name")))
    items.sort(key=lambda x: x[0])
    return items


def git_branch(repo: Path) -> str:
    return try_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)


def extract_ticket(branch: str, latest_name: str, latest_ts: str) -> str:
    m = OS_TICKET_RE.search(branch)
    if m:
        return m.group(1)
    m2 = OS_TICKET_RE.search(latest_name)
    if m2:
        return m2.group(1)
    return latest_ts

# ---------- Main ----------

def main():
    script_dir = Path(__file__).parent

    # Ask user which env file to load
    chosen_env = choose_env_file(script_dir)
    env_vars = load_env(chosen_env)

    # CLI args
    ap = argparse.ArgumentParser(description="EF Core Migration Script Generator (multi-env)")
    ap.add_argument("--create", metavar="NAME", help="Create new migration")
    ap.add_argument("--no-script", action="store_true", help="Skip SQL generation")
    ap.add_argument("--from", dest="from_mig", help="Override 'from' migration")
    ap.add_argument("--to", dest="to_mig", help="Override 'to' migration")
    ap.add_argument("--ticket", help="Override ticket number")
    ap.add_argument("--context", help="Specify DbContext")
    ap.add_argument("--idempotent", action="store_true", help="Generate idempotent script")
    ap.add_argument("--skip-build", action="store_true", help="Skip build step")
    args = ap.parse_args()

    # Resolve paths
    repo = Path(env_vars["REPO_PATH"]).resolve()
    project_path = repo / env_vars["PROJECT_NAME"]
    startup_path = repo / env_vars["STARTUP_PROJECT"]
    migrations_dir = repo / env_vars["MIGRATIONS_DIR"]
    scripts_dir = repo / env_vars["SCRIPTS_DIR"]
    context = args.context or env_vars.get("DBCONTEXT_NAME")

    ef_mode = resolve_ef_mode(repo)

    # Create migration if requested
    if args.create:
        migration_name = args.create
        print(yellow("\n=== Creating New Migration ==="))
        print(f"Repo: {repo}\nProject: {project_path}\nStartup: {startup_path}\nMigration: {migration_name}")
        if context: print(f"Context: {context}")
        print("=" * 40)

        cmd = ["migrations", "add", migration_name, "--project", str(project_path), "--startup-project", str(startup_path)]
        if context: cmd += ["--context", context]
        run_stream(ef_cmd(ef_mode, cmd), repo)
        print(green(f"\n✅ Migration created: {migration_name}"))
        if args.no_script:
            print(yellow("Skipping SQL generation (--no-script)"))
            return

    # Generate SQL script
    files = list_migration_files(migrations_dir)
    if len(files) < 2 and not (args.from_mig and args.to_mig):
        raise RuntimeError("Need at least two migrations to generate script")

    ts_prev, name_prev = files[-2]
    ts_last, name_last = files[-1]
    from_id = args.from_mig or f"{ts_prev}_{name_prev}"
    to_id = args.to_mig or f"{ts_last}_{name_last}"

    ticket = args.ticket or extract_ticket(git_branch(repo), name_last, ts_last)
    output_sql = scripts_dir / f"{ticket}.sql"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    print(yellow("\n=== Generating SQL Script ==="))
    print(f"From: {from_id}\nTo: {to_id}\nTicket: {ticket}\nOutput: {output_sql}")
    print("=" * 40)

    if not args.skip_build:
        run_stream(["dotnet", "build", str(startup_path)], repo)

    cmd = ["migrations", "script", from_id, to_id, "--project", str(project_path), "--startup-project", str(startup_path), "--output", str(output_sql)]
    if context: cmd += ["--context", context]
    if args.idempotent: cmd += ["--idempotent"]

    try:
        run_stream(ef_cmd(ef_mode, cmd), repo)
    except Exception:
        cmd.append("--no-build")
        run_stream(ef_cmd(ef_mode, cmd), repo)

    print(green(f"\n✅ SQL script generated: {output_sql}"))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(red(f"\n❌ ERROR: {e}"))
        sys.exit(1)