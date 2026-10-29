"""The oracle: a trusted model's commentary on how the series is going.

``python -m gb_agent.oracle`` runs twice a day (the ``gb-agent-oracle`` timer, at
06:00 and 18:00 Stockholm time). It reads every run of the autoplay series, boils the
game down to a timeline (where it went, who it fought, levels, badges, blackouts),
and asks DeepSeek for a few paragraphs on the series so far, mostly the last 12 hours.

Entries are kept in ``$GB_AGENT_DIR/oracle.json`` (the newest ``KEEP``) and uploaded
whole to the bucket root as ``oracle.json``, which the page shows under its title.
The digest is built from the runs alone; the agent never sees any of this.
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from gb_agent.autoplay import config_path, load_config, series
from gb_agent.paths import gb_agent_path
from gb_agent.replay import FPS
from util.timezone import STOCKHOLM

logger = logging.getLogger(__name__)

MODEL = "deepseek/deepseek-v4-pro"
PROMPT = str(Path(__file__).parent / "prompts" / "oracle.jinja2")
HOURS = 12
KEEP = 14  # entries in oracle.json
RECENT_EVENTS = 60  # timeline lines for the window; older ones are milestones only
SAID = 8  # of the agent's own lines from the window
SAID_CAP = 240  # characters each


def _jsonl(path: Path) -> list[dict]:
    out = []
    for line in path.read_text().splitlines() if path.exists() else []:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:  # a half-written last line
            continue
    return out


def when(t: float) -> str:
    return datetime.fromtimestamp(t, STOCKHOLM).strftime("%a %d %b %H:%M")


def _blacked_out(obs: dict) -> bool:
    return any("whited" in line or "blacked" in line
               for box in obs.get("text") or [] for line in box)


def events(before: dict | None, after: dict) -> list[tuple[str, bool]]:
    """What changed between two observations, as (text, milestone)."""
    out = []
    if before is None:
        return [(f"in {after['map']['name']}", True)]
    if after["map"]["name"] != before["map"]["name"]:
        out.append((f"went to {after['map']['name']}", False))
    battle, was = after.get("battle"), before.get("battle")
    if battle and not was:
        enemy = battle["enemy"]
        out.append((f"{battle['kind']} battle: {enemy['species']} Lv {enemy['level']}", False))
    if _blacked_out(after) and not _blacked_out(before):
        out.append(("blacked out (sent back to the last Pokemon Center or home, lost money)", True))
    old = {i: m for i, m in enumerate(before.get("party") or [])}
    for i, mon in enumerate(after.get("party") or []):
        prev = old.get(i)
        if prev is None or prev["species"] != mon["species"]:
            if mon["species"] not in {m["species"] for m in old.values()}:
                out.append((f"{mon['species']} joined the party (Lv {mon['level']})", True))
        elif mon["level"] > prev["level"]:
            out.append((f"{mon['species']} grew to Lv {mon['level']}", True))
    if (after.get("badges") or 0) > (before.get("badges") or 0):
        out.append((f"won a badge ({after['badges']} now)", True))
    dex, old_dex = after.get("dex"), before.get("dex")  # missing from older observations
    if dex and old_dex and dex.get("caught", 0) > old_dex.get("caught", 0):
        out.append((f"caught a Pokemon ({dex['caught']} caught)", True))
    return out


def digest(runs: list[Path], now: float, hours: float = HOURS,
           previous: list[dict] = ()) -> dict:
    """Everything the oracle is told, from a series' runs (oldest first)."""
    since = now - hours * 3600
    earlier, recent, seen_maps = [], [], set()
    before, first_time, last = None, None, None
    said = []
    totals = {"steps": 0, "kept_steps": 0, "llm_calls": 0, "minutes": 0.0}
    status, notes = "no runs yet", ""
    for run in runs:
        manifest = json.loads((run / "manifest.json").read_text()) \
            if (run / "manifest.json").exists() else {}
        for key in totals:
            totals[key] += manifest.get(key) or 0
        for step in _jsonl(run / "steps.jsonl"):
            obs = step.get("observation")
            if not step.get("kept") or not obs:
                continue
            t = step.get("time") or 0
            first_time = first_time or t
            for text, milestone in events(before, obs):
                if t >= since:
                    recent.append(f"{when(t)}  {text}")
                elif milestone or (text.startswith("went to ")
                                   and obs["map"]["name"] not in seen_maps):
                    earlier.append(f"{when(t)}  {text}"
                                   + (" (first time)" if text.startswith("went to ") else ""))
            seen_maps.add(obs["map"]["name"])
            before, last = obs, (t, step["step"], obs)
        for record in _jsonl(run / "agents.jsonl"):
            text = (record.get("text") or "").strip()
            if record.get("kind") == "llm" and text and (record.get("time") or 0) >= since:
                said.append(f"{when(record['time'])}  {text[:SAID_CAP]}")
        if (run / "notes.md").exists():
            notes = (run / "notes.md").read_text().strip()
        ended = manifest.get("stop_reason")
        status = f"stopped ({ended})" if ended else "playing"
    if len(recent) > RECENT_EVENTS:  # keep the start and the end of a busy window
        half = RECENT_EVENTS // 2
        recent = recent[:half] + [f"... {len(recent) - RECENT_EVENTS} more ..."] + recent[-half:]
    if len(said) > SAID:
        said = [said[round(i * (len(said) - 1) / (SAID - 1))] for i in range(SAID)]
    now_state = None
    if last is not None:
        t, step, obs = last
        party = ", ".join(f"{_mon_name(m)} Lv {m['level']} HP {m['hp']}/{m['max_hp']}"
                          for m in obs.get("party") or []) or "none"
        now_state = {"time": when(t), "step": step, "map": obs["map"]["name"], "party": party,
                     "badges": obs.get("badges", 0), "money": obs.get("money", 0),
                     "dex": obs.get("dex") or {}}
    return {
        "now": when(now), "hours": hours, "status": status,
        "started": when(first_time) if first_time else None,
        "hours_played": round(totals["minutes"] / 60, 1), "totals": totals,
        "game_time_min": round(_frame(runs) / FPS / 60),
        "state": now_state, "earlier": earlier, "recent": recent, "said": said, "notes": notes,
        "previous": [{"time": e.get("time"), "text": e.get("text")} for e in previous[-2:]],
        "run": runs[-1].name if runs else None, "step": last[1] if last else None,
    }


def _mon_name(m: dict) -> str:
    nick = (m.get("nickname") or "").strip()
    return m["species"] if not nick or nick.upper() == m["species"].upper() \
        else f"{nick} (a {m['species']})"


def _frame(runs: list[Path]) -> int:
    for run in reversed(runs):
        manifest = run / "manifest.json"
        if manifest.exists() and (frame := json.loads(manifest.read_text()).get("frame")):
            return frame
    return 0


def oracle_path() -> Path:
    return gb_agent_path("oracle.json")


def load_entries(path: Path) -> list[dict]:
    return json.loads(path.read_text()).get("entries", []) if path.exists() else []


def comment(facts: dict, model: str = MODEL) -> str:
    from llm.llm_util import get_llm_response

    return get_llm_response(PROMPT, facts, model_name=model).strip()


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m gb_agent.oracle", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dest", default="gs://personal-website-318015-gb-agent",
                   help="gs://<bucket>, or a local folder laid out like the bucket")
    p.add_argument("--dry-run", action="store_true",
                   help="print what the model would be told, and don't call it")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config(config_path())
    if not config or not config.get("start"):
        logger.info("no autoplay series: nothing to comment on")
        return 0
    path = oracle_path()
    entries = load_entries(path)
    facts = digest(series(gb_agent_path("runs"), config["start"]), time.time(), previous=entries)
    if args.dry_run:
        print(json.dumps(facts, indent=2, ensure_ascii=False))
        return 0
    text = comment(facts)
    if not text:
        logger.error("the oracle said nothing")
        return 1
    entries.append({"time": datetime.now(timezone.utc).isoformat(), "text": text, "model": MODEL,
                    "run": facts["run"], "step": facts["step"], "hours": HOURS})
    data = {"entries": entries[-KEEP:]}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    from gb_agent.publish import NO_CACHE, GCSDestination, LocalDestination, _json

    dest = (GCSDestination(args.dest.removeprefix("gs://")) if args.dest.startswith("gs://")
            else LocalDestination(Path(args.dest)))
    dest.put("oracle.json", _json(data), "application/json", NO_CACHE)
    logger.info("published the oracle's %d words", len(text.split()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
