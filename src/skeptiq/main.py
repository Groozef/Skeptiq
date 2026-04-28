async def run() -> None:
    raise NotImplementedError


def cli() -> None:
    import asyncio

    asyncio.run(run())


if __name__ == "__main__":
    cli()
