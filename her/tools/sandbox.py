from __future__ import annotations

import asyncio
from typing import Sequence


async def run_sandboxed_command(command: Sequence[str], timeout_seconds: int = 10) -> str:
    """Execute a command without shell expansion and return output."""

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise TimeoutError("Sandboxed command timed out")

    return stdout.decode("utf-8", errors="replace")
