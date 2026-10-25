"""Run one experiment: ``python -m gb_agent.play --model qwen3-vl-2b-local``.

Prints the run directory at the start and a summary at the end. Paid models
refuse to start without --allow-paid.
"""

import argparse
import logging
import subprocess
import sys
from dataclasses import replace

from gb_agent.agent import GameAgent
from gb_agent.models import PROFILES, build_chat_model, get_profile
from gb_agent.run import STEP_FRAMES, ExperimentConfig, Run
from gb_agent.steps import StepLimits
from gb_agent.subagents import SubAgentHost

DEFAULT_GOAL = "Make as much progress in the game as you can."


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m gb_agent.play", description=__doc__)
    p.add_argument("--game", default="silver")
    p.add_argument("--model", default="qwen3-vl-8b-local", choices=sorted(PROFILES))
    p.add_argument("--goal", default=DEFAULT_GOAL)
    p.add_argument("--frames", type=int, default=10_000, help="frame budget (kept steps only)")
    p.add_argument("--max-calls", type=int, default=300, help="LLM calls")
    p.add_argument("--max-tokens", type=int, default=5_000_000)
    p.add_argument("--max-minutes", type=float, default=240)
    # A backstop for code that spins without ticking; the frame cap stops the rest.
    p.add_argument("--step-timeout", type=float, default=300, help="seconds per sandbox step")
    p.add_argument("--step-frames", type=int, default=STEP_FRAMES,
                   help="most frames one step may use")
    p.add_argument("--video", action="store_true", help="render run.mp4 at the end")
    p.add_argument("--publish", action="store_true",
                   help="publish the run live for the website as it goes (gb_agent.publish)")
    p.add_argument("--no-notify", action="store_true", help="don't send blockers to Telegram")
    p.add_argument("--allow-paid", action="store_true",
                   help="allow a paid (OpenRouter) model, for the agent or its sub-agents")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    profile = get_profile(args.model)
    if profile.paid and not args.allow_paid:
        print(f"{args.model} is a paid model ({profile.provider}); pass --allow-paid to use it.",
              file=sys.stderr)
        return 2

    steps = StepLimits(max_frames=args.step_frames)
    config = ExperimentConfig(
        game=args.game, model=args.model, goal=args.goal, frame_budget=args.frames,
        max_llm_calls=args.max_calls, max_tokens=args.max_tokens, max_minutes=args.max_minutes,
        step=replace(steps, sandbox=replace(steps.sandbox, timeout_s=args.step_timeout)),
        notify=not args.no_notify,
        allow_paid=args.allow_paid,
    )
    run = Run(config)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(run.dir / "run.log")],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(f"run {run.id}\n  {run.dir}", flush=True)
    publisher = None
    if args.publish:  # its own process, so a publishing failure can't stop the run
        with (run.dir / "publish.log").open("a") as log:
            publisher = subprocess.Popen(
                [sys.executable, "-m", "gb_agent.publish", "--run", run.id],
                stdout=log, stderr=subprocess.STDOUT)

    describer = None
    if not profile.vision and profile.describer:
        describer = build_chat_model(get_profile(profile.describer))
    host = SubAgentHost(run, profile, build_chat_model, allow_paid=args.allow_paid,
                        describer=describer)
    agent = GameAgent(run, build_chat_model(profile), profile, describer=describer, host=host)
    try:
        reason = agent.play()
    except KeyboardInterrupt:
        reason = "interrupted"
    run.finish(reason, video=args.video)
    if publisher is not None:
        try:  # it stops by itself once it has published the ended run
            publisher.wait(timeout=120)
        except subprocess.TimeoutExpired:
            publisher.terminate()
    print(f"ended: {reason}; frame {run.frame}/{config.frame_budget}, {run.step} steps "
          f"({run.kept_steps} kept), {run.llm_calls} LLM calls, {run.tokens} tokens, "
          f"{run.minutes:.1f} min, {agent.compactions} compactions\n  {run.dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
