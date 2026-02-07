import time
from collections.abc import Callable
from typing import Any, Iterable


class RetryError(RuntimeError):
    pass


def with_retry(
    func: Callable[[], Any],
    *,
    attempts: int = 3,
    delay_seconds: float = 0.5,
    retry_on: Iterable[type[BaseException]] = (Exception,),
) -> Any:
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except tuple(retry_on) as exc:  # type: ignore[arg-type]
            last_exc = exc
            if attempt == attempts:
                break
            time.sleep(delay_seconds)

    raise RetryError("Operation failed after retries") from last_exc
