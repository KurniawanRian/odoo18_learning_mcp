import asyncio
from fastmcp import Client

async def main():

    user_input = input("Tanya ERP: ")

    # URL harus mengarah ke /mcp karena FastMCP streamable-http
    # serve endpoint di path /mcp, bukan di root /
    async with Client("http://localhost:8000/mcp") as client:

        try:
            response = await client.call_tool(
                "query_erp",
                {
                    "natural_language": user_input
                }
            )

            print("HASIL:", response)

        except Exception as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    asyncio.run(main())