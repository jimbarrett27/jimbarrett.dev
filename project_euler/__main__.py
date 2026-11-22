"""Run one problem: ``uv run python -m project_euler 1``."""

import argparse
import importlib
from time import perf_counter


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Project Euler solution")
    parser.add_argument("problem", type=int)
    args = parser.parse_args()

    module = importlib.import_module(f"project_euler.problem_{args.problem:03d}")

    start = perf_counter()
    answer = module.solve()
    print(f"Answer: {answer} time: {perf_counter() - start:.3g}s")


if __name__ == "__main__":
    main()
