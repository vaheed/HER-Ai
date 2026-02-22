#!/usr/bin/env python3
import asyncio
import statistics
import time


async def _ticker(duration_seconds: float = 0.25) -> tuple[int, float]:
    ticks = 0
    started = time.perf_counter()
    first_tick_delay = 0.0
    first_tick_recorded = False
    end = time.perf_counter() + duration_seconds
    while time.perf_counter() < end:
        await asyncio.sleep(0.01)
        ticks += 1
        if not first_tick_recorded:
            first_tick_delay = time.perf_counter() - started
            first_tick_recorded = True
    return ticks, first_tick_delay


async def _baseline_blocking_run(task_delay_seconds: float) -> tuple[float, int, float]:
    def _run_task_job() -> None:
        time.sleep(task_delay_seconds)

    async def _legacy_run_task_now() -> None:
        _run_task_job()

    started = time.perf_counter()
    _, (ticks, first_tick_delay) = await asyncio.gather(_legacy_run_task_now(), _ticker())
    return (time.perf_counter() - started), ticks, first_tick_delay


async def _improved_nonblocking_run(task_delay_seconds: float) -> tuple[float, int, float]:
    def _run_task_job() -> None:
        time.sleep(task_delay_seconds)

    async def _run_now() -> None:
        await asyncio.to_thread(_run_task_job)

    started = time.perf_counter()
    _, (ticks, first_tick_delay) = await asyncio.gather(_run_now(), _ticker())
    return (time.perf_counter() - started), ticks, first_tick_delay


def main() -> None:
    rounds = 10
    baseline_latencies: list[float] = []
    baseline_ticks: list[int] = []
    baseline_first_ticks: list[float] = []
    improved_latencies: list[float] = []
    improved_ticks: list[int] = []
    improved_first_ticks: list[float] = []

    for _ in range(rounds):
        latency, ticks, first_tick = asyncio.run(_baseline_blocking_run(task_delay_seconds=0.2))
        baseline_latencies.append(latency)
        baseline_ticks.append(ticks)
        baseline_first_ticks.append(first_tick)

        latency, ticks, first_tick = asyncio.run(_improved_nonblocking_run(task_delay_seconds=0.2))
        improved_latencies.append(latency)
        improved_ticks.append(ticks)
        improved_first_ticks.append(first_tick)

    print("Benchmark: scheduler run-now event-loop responsiveness")
    print(f"Rounds: {rounds}")
    print(
        "Baseline (legacy direct call): "
        f"p50_latency={statistics.median(baseline_latencies):.4f}s "
        f"avg_ticks={statistics.mean(baseline_ticks):.1f} "
        f"p50_first_tick={statistics.median(baseline_first_ticks):.4f}s"
    )
    print(
        "Improved (asyncio.to_thread): "
        f"p50_latency={statistics.median(improved_latencies):.4f}s "
        f"avg_ticks={statistics.mean(improved_ticks):.1f} "
        f"p50_first_tick={statistics.median(improved_first_ticks):.4f}s"
    )
    print(
        "Delta: "
        f"latency_improvement={(statistics.median(baseline_latencies) - statistics.median(improved_latencies)):.4f}s "
        f"first_tick_improvement={(statistics.median(baseline_first_ticks) - statistics.median(improved_first_ticks)):.4f}s"
    )


if __name__ == "__main__":
    main()
