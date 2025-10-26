# EF Core Migration Script Generator

Automates EF Core migration workflows: generating SQL scripts and creating new migrations.

## Setup

1. **Copy the environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Configure `.env` with your project paths:**
   ```env
   REPO_PATH=C:\Users\username\source\repos\your-project
   PROJECT_NAME=YourProject.Data
   STARTUP_PROJECT=YourProject.Data
   MIGRATIONS_DIR=YourProject.Data\Migrations
   SCRIPTS_DIR=YourProject.Data\Scripts
   ```

3. **Ensure dotnet-ef is installed:**
   ```bash
   dotnet tool install -g dotnet-ef
   ```

## Usage

### Generate SQL Script (Default Mode)

Automatically generates a SQL script from the last two migrations:

```bash
python ef_migrate_and_script.py
```

**Output filename logic:**
1. Extracts `OS-####` from current git branch name
2. Falls back to `OS-####` or `OS_####` from latest migration name
3. Falls back to migration timestamp

**Options:**
- `--from <migration>` - Override source migration
- `--to <migration>` - Override target migration
- `--ticket <number>` - Override output filename (e.g., `--ticket 1234` → `1234.sql`)
- `--context <name>` - Specify DbContext (if multiple exist)
- `--idempotent` - Generate idempotent SQL script
- `--skip-build` - Skip build step

### Create New Migration

Creates a new migration **and automatically generates SQL script** from the last two migrations:

```bash
python ef_migrate_and_script.py --create MigrationName
```

To create a migration **without** generating the SQL script:

```bash
python ef_migrate_and_script.py --create MigrationName --no-script
```

Example:
```bash
python ef_migrate_and_script.py --create AddUserEmailColumn
```
This will:
1. Create the migration `AddUserEmailColumn`
2. Generate SQL script from second-to-last migration to the new one

## Examples

**Basic usage:**
```bash
python ef_migrate_and_script.py
```

**Create migration and generate SQL (default behavior):**
```bash
python ef_migrate_and_script.py --create AddUserEmailColumn
```
Output:
- Creates new migration `AddUserEmailColumn`
- Generates SQL file (e.g., `OS-1234.sql` if on branch `OS-1234-add-user-email`)

**Create migration without SQL generation:**
```bash
python ef_migrate_and_script.py --create AddUserEmailColumn --no-script
```
Output: Only creates the migration, no SQL file

**Generate SQL for specific migrations:**
```bash
python ef_migrate_and_script.py --from 20241001120000_Initial --to 20241002150000_AddUsers
```

**Generate idempotent script:**
```bash
python ef_migrate_and_script.py --idempotent
```

**Override ticket number:**
```bash
python ef_migrate_and_script.py --ticket 5678
```
Output: `5678.sql`

## Requirements

- Python 3.10+
- dotnet-ef (global or local tool)
- .NET project with EF Core migrations

## Troubleshooting

**`.env file not found`**
- Copy `.env.example` to `.env` and configure your paths

**`dotnet-ef not found`**
- Install globally: `dotnet tool install -g dotnet-ef`
- Or locally: `dotnet tool install dotnet-ef`

**`Need at least two migrations`**
- Create at least two migrations or use `--from` and `--to` flags

## Git Integration

Add to `.gitignore`:
```
.env
*.sql
```

Keep in repository:
```
.env.example
```
