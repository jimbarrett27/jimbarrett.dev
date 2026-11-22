"""Run both parts of one day: ``uv run python -m advent_of_code 2025 7``."""

import argparse
import importlib
import math
from time import perf_counter


def round_sig(x: float, sig: int = 3) -> float:
    if x == 0:
        return 0.0
    return round(x, sig - int(math.floor(math.log10(abs(x)))) - 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an Advent of Code solution")
    parser.add_argument("year", type=int)
    parser.add_argument("day", type=int)
    args = parser.parse_args()

    module = importlib.import_module(f"advent_of_code.y{args.year}.day_{args.day:02d}")

    for part in (1, 2):
        start = perf_counter()
        answer = getattr(module, f"part_{part}")()
        elapsed = round_sig(perf_counter() - start)
        print(f"Part {part} answer: {answer} time: {elapsed}s")


if __name__ == "__main__":
    main()
