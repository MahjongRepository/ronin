import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = structlog.get_logger()


async def cancel_and_wait(
    tasks: Iterable[asyncio.Task[Any]],
    *,
    finalizing: Iterable[asyncio.Task[Any]] = (),
) -> None:
    """
    Cancel background tasks and wait until they and the finalizing ones are done.

    A finalizing task (a callback already past its sleep, finishing a game) is awaited, never cancelled, so its
    persistence and socket closes complete; cancelling the waiter does not cancel it either. The current task is skipped
    in both groups: a task never cancels or awaits itself. A task that died with an exception has it logged here instead
    of re-raised, so one dead task cannot make a shutdown skip the steps after it.
    """
    current = asyncio.current_task()
    to_cancel = {task for task in tasks if task is not current}
    to_finish = {task for task in finalizing if task is not current} - to_cancel
    for task in to_cancel:
        task.cancel()

    awaited = to_cancel | to_finish
    if awaited:
        await asyncio.wait(awaited)

    for task in awaited:
        if not task.cancelled() and task.exception() is not None:
            logger.error("background task failed", task=task.get_name(), exc_info=task.exception())
