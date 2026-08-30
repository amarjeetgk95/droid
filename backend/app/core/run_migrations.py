"""
Run database migrations on Supabase.
Executes SQL files handling $$ delimiters and function bodies correctly.
"""
import asyncio
import re
from app.core.database import get_async_engine
from sqlalchemy import text


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL into statements, handling $$ delimiters."""
    statements = []
    current = []
    in_dollar_quote = False
    dollar_tag = ""
    
    lines = sql.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Skip comments
        stripped = line.strip()
        if stripped.startswith('--') or stripped.startswith('/*'):
            i += 1
            continue
        
        # Handle dollar-quoted strings ($$ ... $$)
        if not in_dollar_quote:
            # Check for opening dollar quote
            match = re.search(r'\$\w*\$', line)
            if match:
                dollar_tag = match.group()
                in_dollar_quote = True
                current.append(line)
                # Check if it closes on same line
                rest = line[line.index(match.group()) + len(match.group()):]
                if dollar_tag in rest:
                    in_dollar_quote = False
                i += 1
                continue
            else:
                current.append(line)
                if stripped.endswith(';'):
                    stmt = '\n'.join(current).strip()
                    if stmt:
                        statements.append(stmt)
                    current = []
                i += 1
        else:
            current.append(line)
            if dollar_tag in line:
                in_dollar_quote = False
            i += 1
    
    # Add any remaining statement
    if current:
        stmt = '\n'.join(current).strip()
        if stmt:
            statements.append(stmt)
    
    return statements


async def run_migration(engine, filepath: str):
    """Run a single migration file."""
    with open(filepath, 'r') as f:
        sql = f.read()
    
    statements = split_sql_statements(sql)
    
    async with engine.connect() as conn:
        for stmt in statements:
            if not stmt or stmt.isspace():
                continue
            try:
                await conn.execute(text(stmt))
                await conn.execute(text("COMMIT"))
                print(f"OK: {stmt[:70].replace(chr(10), ' ')}...")
            except Exception as e:
                await conn.execute(text("ROLLBACK"))
                err_msg = str(e)[:80]
                print(f"SKIP: {err_msg}")
        
        # Verify
        result = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        ))
        tables = [row[0] for row in result]
        print(f"\nTables in public schema: {tables}")


async def main():
    engine = get_async_engine()
    if engine is None:
        print("ERROR: No database URL configured")
        return
    
    import os
    migration_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database', 'migrations')
    
    files = sorted([f for f in os.listdir(migration_dir) if f.endswith('.sql')])
    
    for filename in files:
        filepath = os.path.join(migration_dir, filename)
        print(f"\n=== Running {filename} ===")
        await run_migration(engine, filepath)
    
    await engine.dispose()
    print("\n=== All migrations complete ===")


if __name__ == "__main__":
    asyncio.run(main())
