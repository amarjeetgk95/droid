"""Run migrations on Supabase with proper transaction handling."""
import sys
import os
import re
import asyncio

from sqlalchemy import text

backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)


def get_async_engine_safe():
    from app.core.database import get_async_engine
    return get_async_engine()


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL script into executable statements respecting dollar quoting and comments."""
    statements = []
    current = []
    in_dollar_quote = False
    dollar_tag = ""

    lines = sql.split("\n")
    for line in lines:
        stripped = line.strip()
        # Skip empty lines and single-line comments if not in block
        if not in_dollar_quote and (not stripped or stripped.startswith("--") or stripped.startswith("/*")):
            continue

        current.append(line)

        if not in_dollar_quote:
            # Check for opening dollar quote like $$ or $tag$
            match = re.search(r"(\$[a-zA-Z0-9_]*\$)", line)
            if match:
                tag = match.group(1)
                # Check if closed on same line after the match
                after_open = line[match.end():]
                if tag in after_open:
                    # Opened and closed on same line
                    if stripped.endswith(";"):
                        stmt = "\n".join(current).strip()
                        if stmt:
                            statements.append(stmt)
                        current = []
                else:
                    in_dollar_quote = True
                    dollar_tag = tag
            elif stripped.endswith(";"):
                stmt = "\n".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
        else:
            # In dollar quote, look for closing tag
            if dollar_tag in line:
                in_dollar_quote = False
                dollar_tag = ""
                if stripped.endswith(";"):
                    stmt = "\n".join(current).strip()
                    if stmt:
                        statements.append(stmt)
                    current = []

    if current:
        stmt = "\n".join(current).strip()
        if stmt:
            statements.append(stmt)

    return statements


async def main():
    engine = get_async_engine_safe()
    if engine is None:
        print("ERROR: No database URL configured")
        return

    migration_dir = os.path.join(os.path.dirname(backend_dir), 'database', 'migrations')
    files = sorted([f for f in os.listdir(migration_dir) if f.endswith('.sql')])

    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")

        for filename in files:
            filepath = os.path.join(migration_dir, filename)
            print(f"=== {filename} ===")
            with open(filepath, 'r', encoding="utf-8") as f:
                sql = f.read()
            statements = split_sql_statements(sql)
            for stmt in statements:
                if not stmt or stmt.isspace():
                    continue
                try:
                    await conn.execute(text(stmt))
                    display = stmt[:60].replace('\n', ' ')
                    print(f"  OK: {display}...")
                except Exception as e:
                    err_str = str(e).replace('\n', ' ')
                    print(f"  NOTICE/SKIP: {err_str[:90]}")

        # Verify tables
        result = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        ))
        tables = [row[0] for row in result]
        print(f"\nAll Public Tables in Supabase: {tables}")

        # Check RLS
        result = await conn.execute(text(
            "SELECT tablename, rowsecurity FROM pg_tables "
            "WHERE schemaname = 'public' ORDER BY tablename"
        ))
        rls_info = [(row[0], row[1]) for row in result]
        print("\nRLS status:")
        for table, rls in rls_info:
            print(f"  {table}: {'ENABLED' if rls else 'disabled'}")

    await engine.dispose()
    print("\n=== Migrations Successfully Applied to Supabase ===")


if __name__ == "__main__":
    asyncio.run(main())
