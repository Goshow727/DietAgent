import asyncio
import asyncpg

async def main():
    try:
        conn = await asyncpg.connect('postgresql://goshow:123456@localhost:5432/Diet_Db_demo1')
        rows = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position")
        print("Connected! Columns in users table:")
        for r in rows:
            print(" -", r['column_name'])
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
