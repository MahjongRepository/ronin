import asyncio
import logging
from typing import TYPE_CHECKING

from shared.tasks import cancel_and_wait

if TYPE_CHECKING:
    import pytest


async def _sleep_forever() -> None:
    await asyncio.Event().wait()


class TestCancelAndWait:
    async def test_cancel_and_wait__when_tasks_sleep_or_finalize__should_cancel_sleepers_and_finish_finalizers(self):
        finalizer_may_finish = asyncio.Event()
        finalized: list[str] = []

        async def finalize() -> None:
            await finalizer_may_finish.wait()
            finalized.append("replay saved")

        sleeping = asyncio.create_task(_sleep_forever())
        finalizing = asyncio.create_task(finalize())
        await asyncio.sleep(0)
        asyncio.get_running_loop().call_soon(finalizer_may_finish.set)

        await cancel_and_wait([sleeping], finalizing=[finalizing])
        assert sleeping.cancelled()
        assert not finalizing.cancelled()
        assert finalized == ["replay saved"]

    async def test_cancel_and_wait__when_task_died_with_error__should_log_it_instead_of_raising(
        self, caplog: pytest.LogCaptureFixture
    ):
        async def crash() -> None:
            raise RuntimeError("loop crashed")

        dead = asyncio.create_task(crash())
        await asyncio.wait([dead])

        with caplog.at_level(logging.ERROR):
            await cancel_and_wait([dead])

        assert [r.msg["event"] for r in caplog.records if r.levelno == logging.ERROR] == ["background task failed"]

    async def test_cancel_and_wait__when_current_task_listed__should_neither_cancel_nor_await_it(self):
        other = asyncio.create_task(_sleep_forever())
        current = asyncio.current_task()
        assert current is not None

        await cancel_and_wait([current, other], finalizing=[current])
        assert other.cancelled()
        assert not current.cancelled()
