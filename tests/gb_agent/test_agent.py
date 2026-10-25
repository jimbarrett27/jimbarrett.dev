"""The agent loop and its tools, driven by a scripted fake model, in the real sandbox."""

import json
from dataclasses import replace
from itertools import count

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from gb_agent.agent import GameAgent
from gb_agent.games import GameProfile, MemRef
from gb_agent.models import get_profile
from gb_agent.run import ExperimentConfig, Run
from gb_agent.sandbox import SandboxLimits
from gb_agent.steps import StepLimits
from tests.gb_agent.conftest import TEST_ROM, needs_docker

pytestmark = needs_docker

_ids = count()

WALK = '''def walk(game, frames: int = 20) -> int:
    """Hold right for a while."""
    game.press("right")
    game.tick(frames)
    game.release("right")
    return game.frame
'''


def call(tool, /, **args):
    return {"name": tool, "args": args, "id": f"call{next(_ids)}"}


def say(*calls, text="", input_tokens=100):
    return AIMessage(text, tool_calls=list(calls),
                     usage_metadata={"input_tokens": input_tokens, "output_tokens": 10,
                                     "total_tokens": input_tokens + 10})


class ScriptedModel(BaseChatModel):
    """Replies with the given messages in order, then stops calling tools."""

    replies: list = Field(default_factory=list)
    seen: list = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        reply = self.replies.pop(0) if self.replies else say(text="nothing more to do")
        if callable(reply):
            reply = reply(messages)
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted"


@pytest.fixture
def game(tmp_path, test_rom):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "walk.py").write_text(WALK)
    return GameProfile(
        name="test", rom=TEST_ROM,
        power_on_state=tmp_path / "states" / "power_on.state",
        start_state=tmp_path / "states" / "start.state",
        setup=("t:30",),
        progress_values={"wram0": MemRef(0xC000)},
        seed_library=seed,
        notes="A test ROM.",
    )


@pytest.fixture
def make_run(tmp_path, game, image):
    sent = []

    def make(**overrides):
        config = ExperimentConfig(**{
            "game": "test", "model": "qwen3-vl-2b-local", "goal": "test the harness",
            "frame_budget": 300, "max_llm_calls": 50,
            "step": StepLimits(sandbox=SandboxLimits(timeout_s=20)),
            **overrides})
        run = Run(config, root=tmp_path / "runs", game=game, image=image, notify=sent.append)
        run.sent = sent
        return run
    return make


def play(run, replies, profile=None):
    model = ScriptedModel(replies=list(replies))
    agent = GameAgent(run, model, profile or get_profile("qwen3-vl-2b-local"))
    reason = agent.play()
    run.finish(reason)
    return reason, model, agent


def tool_texts(model):
    return [m.content for m in model.seen[-1] if isinstance(m, ToolMessage)]


def jsonl(run, name):
    path = run.dir / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_a_whole_run(make_run):
    run = make_run()
    reason, model, _ = play(run, [
        say(call("list_scripts")),
        say(call("write_script", name="tap_a", reason="tap A once",
                 code='def tap_a(game):\n    """Tap A."""\n    game.tap("a")\n')),
        say(call("run_script", name="walk", args={"frames": 100})),
        say(call("watch_memory", label="wram0", addr="0xC000")),
        say(call("run_script", name="tap_a")),
        say(call("read_memory", addr="0xC000", length=4), call("screenshot")),
        say(call("report_blocker", problem="Can't find the exit", tried="walking",
                 would_help="a map")),
        say(call("press", button="b"), call("wait", frames=60)),
        say(call("wait", frames=600)),  # more than is left: stops at the budget
    ])
    assert reason == "frame_budget"
    assert run.frame == 300

    steps = jsonl(run, "steps.jsonl")
    assert [(s["script"], s["kept"]) for s in steps[:2]] == [("walk", True), ("tap_a", True)]
    assert steps[-1]["frames"] == 107 and steps[-1]["kept"]  # shortened to what was left

    events = jsonl(run, "events.jsonl")
    assert {e["script"] for e in events} >= {"walk", "tap_a"}
    assert all(e["version"] for e in events if e["script"])
    assert run.final_state_replays()

    progress = jsonl(run, "progress.jsonl")
    assert progress[0]["frame"] == 0 and progress[-1]["frame"] == 300
    assert len(run.sent) == 1 and "Can't find the exit" in run.sent[0]

    manifest = json.loads((run.dir / "manifest.json").read_text())
    assert manifest["stop_reason"] == "frame_budget" and manifest["frame"] == 300
    assert manifest["llm_calls"] == 9
    assert (run.dir / "library" / "library" / "tap_a.py").exists()


def test_one_off_code_is_kept_in_the_library(make_run):
    run = make_run()
    play(run, [say(call("run_code", code="game.tick(50)")),
               say(call("press", button="a"))])
    assert run.frame > 50
    snippet = run.dir / "library" / "snippets" / "step00001.py"
    assert snippet.read_text() == "game.tick(50)"
    assert not (run.dir / "library" / "snippets" / "step00002.py").exists()  # press is ours
    first, second = jsonl(run, "steps.jsonl")
    assert first["kept"] and first["version"] and second["version"] is None
    events = jsonl(run, "events.jsonl")
    assert {e["version"] for e in events if e["step"] == 1} == {first["version"]}
    assert "One-off code at step 1" in run.library._git("log", "--format=%s").stdout


def test_steps_that_go_behind_games_back_are_not_kept(make_run):
    run = make_run()
    _, model, _ = play(run, [
        say(call("run_code", code="game._pyboy.button_press('a')\ngame.tick(30)")),
        say(call("screenshot")),
    ])
    assert run.frame == 0
    assert jsonl(run, "steps.jsonl")[0]["kept"] is False
    assert "[not kept]" in model.seen[1][-2].content or any(
        "[not kept]" in m.content for m in model.seen[1] if isinstance(m, ToolMessage))


def test_bad_calls_get_errors_and_the_run_goes_on(make_run):
    run = make_run()
    bad_json = AIMessage("", invalid_tool_calls=[
        {"name": "press", "args": "{oops", "id": "bad1", "error": "bad JSON"}])
    reason, model, _ = play(run, [
        say(call("teleport", x=1), call("press", button="turbo"),
            call("read_memory", addr="banana"), call("run_script", name="../x"),
            call("wait", frames=-5), call("write_script", name="x", code="def y(): pass",
                                          reason="r")),
        bad_json,
        say(call("wait", frames=10)),
    ])
    texts = tool_texts(model)
    assert all(t.startswith("Error") for t in texts[:6])
    assert any("couldn't read that tool call" in t for t in texts)
    assert run.frame == 10
    assert reason == "agent_stopped"


def test_an_agent_that_stops_calling_tools_ends_the_run(make_run):
    run = make_run()
    reason, model, _ = play(run, [say(text="hmm"), say(text="thinking"), say(text="done")])
    assert reason == "agent_stopped"
    assert "Keep going" in model.seen[1][-1].content


def test_the_call_limit_ends_the_run(make_run):
    run = make_run(max_llm_calls=3)
    reason, _, _ = play(run, [say(call("wait", frames=1))] * 10)
    assert reason == "max_llm_calls" and run.llm_calls == 3


def test_screenshots_follow_game_steps(make_run):
    run = make_run()
    _, model, _ = play(run, [say(call("wait", frames=30)), say(text="ok")])
    last = model.seen[1][-1]
    assert isinstance(last, HumanMessage)
    images = [p for p in last.content if p.get("type") == "image_url"]
    assert len(images) == 1  # just "after": "before" is the previous step's "after"
    assert "after (frame 30)" in last.content[0]["text"]
    assert images[0]["image_url"]["url"].startswith("data:image/png;base64,")
    # the opening message shows the screen too
    assert any(p.get("type") == "image_url" for p in model.seen[0][1].content)


def test_a_model_without_vision_gets_descriptions(make_run):
    run = make_run()
    blind = replace(get_profile("qwen3-vl-2b-local"), vision=False)
    describer = ScriptedModel(replies=[say(text="A blank screen.")] * 5)
    model = ScriptedModel(replies=[say(call("wait", frames=30)), say(text="ok")])
    agent = GameAgent(run, model, blind, describer=describer)
    agent.play()
    assert "A blank screen." in model.seen[1][-1].content
    assert isinstance(model.seen[1][-1].content, str)


def test_compaction_restarts_from_notes(make_run):
    run = make_run()
    small = replace(get_profile("qwen3-vl-2b-local"), context_window=1_000)
    reason, model, agent = play(run, [
        say(call("wait", frames=10), input_tokens=900),  # past 75% of 1000
        say(text="Notes: waiting works. Next: press A."),  # the compaction reply
        say(call("wait", frames=10)),
    ], profile=small)
    assert agent.compactions == 1
    after = model.seen[2]
    assert len([m for m in after if isinstance(m, ToolMessage)]) == 0  # old turns gone
    opening = after[1].content[0]["text"]
    assert "Notes: waiting works" in opening
    assert [r["kind"] for r in jsonl(run, "agents.jsonl")].count("compaction") == 1
    assert run.frame == 20


def test_rewriting_a_script_unchanged_says_so(make_run):
    from gb_agent.tools import Tools

    run = make_run()
    tools = Tools(run)
    code = run.library.read("walk")
    assert tools.call("write_script", {"name": "walk", "code": code, "reason": "again"}) \
        .text.startswith("Nothing saved")
    assert "Saved walk" in tools.call("write_script", {
        "name": "walk", "code": code.replace("20", "30"), "reason": "longer"}).text


def test_press_takes_the_same_names_as_game_tap(make_run):
    from gb_agent.tools import Tools

    run = make_run()
    tools = Tools(run)
    assert "frames 0→7" in tools.call("press", {"button": "a", "hold": 3, "after": 4}).text
    assert "frames 7→14" in tools.call("press", {"button": "a", "hold_frames": 3,
                                                  "wait_frames": 4}).text


def test_repeated_identical_calls_get_a_note(make_run):
    from gb_agent.tools import Tools

    tools = Tools(make_run())
    texts = [tools.call("read_memory", {"addr": "0xC000"}).text for _ in range(4)]
    assert "Note:" not in texts[0] + texts[1]
    assert "this exact call 3 times in a row" in texts[2]
    assert "4 times" in texts[3]
    assert "Note:" not in tools.call("read_memory", {"addr": "0xC001"}).text


def test_reports_say_how_much_of_the_screen_changed(make_run):
    from gb_agent.tools import Tools

    text = Tools(make_run()).call("wait", {"frames": 30}).text
    assert "screen: " in text


def test_compaction_rewrites_the_notes(make_run):
    run = make_run()
    small = replace(get_profile("qwen3-vl-2b-local"), context_window=1_000)
    reason, model, agent = play(run, [
        say(call("update_notes", notes="Stairs are top right. walk() works."), input_tokens=900),
        say(text="Stairs are top right. walk() works. Now downstairs, looking for the door."),
        say(call("wait", frames=10)),
    ], profile=small)
    request = model.seen[1][-1].content  # the compaction request shows the old notes
    assert "Rewrite your notes" in request and "Stairs are top right. walk() works." in request
    opening = model.seen[2][1].content[0]["text"]
    assert "Now downstairs, looking for the door." in opening
    assert "Start by writing a script" not in opening  # not a fresh start
    assert run.notes.endswith("looking for the door.")
    assert (run.dir / "notes.md").read_text().startswith("Stairs are top right.")


def test_the_agent_is_asked_to_update_its_notes_regularly(make_run):
    from gb_agent.agent import NOTES_EVERY

    run = make_run()
    _, model, _ = play(run, [say(call("wait", frames=1))] * (NOTES_EVERY + 1))
    followups = [m[-1].content for m in model.seen[1:]]
    texts = [f if isinstance(f, str) else f[0]["text"] for f in followups]
    assert sum("Notes check" in t for t in texts) == 1
    assert "Notes check" in texts[NOTES_EVERY - 1]


def test_notes_have_a_size_limit(make_run):
    from gb_agent.tools import Tools

    run = make_run()
    assert "limited to 2000" in Tools(run).call("update_notes", {"notes": "x" * 2_001}).text
    assert run.notes == ""


def test_kept_steps_are_capped_per_step(make_run):
    from gb_agent.run import STEP_FRAMES, ExperimentConfig
    from gb_agent.tools import Tools

    assert ExperimentConfig("g", "m", "goal").step.max_frames == STEP_FRAMES == 600
    run = make_run(step=StepLimits(max_frames=100, sandbox=SandboxLimits(timeout_s=20)))
    tools = Tools(run)
    assert tools.call("wait", {"frames": 500}).text.startswith("(Shortened to 100 frames")
    assert "FrameLimitExceeded" in tools.call("run_code", {"code": "game.tick(150)"}).text
    assert run.frame == 100  # the second step was refused at the limit, nothing advanced


def test_budget_used_up_refuses_steps(make_run):
    run = make_run(frame_budget=30)
    run.frame = 30  # as if spent
    from gb_agent.tools import Tools

    tools = Tools(run)
    assert tools.call("wait", {"frames": 5}).text.startswith("Error: the frame budget")
    assert tools.call("run_code", {"code": "game.tick(5)"}).text.startswith(
        "Error: the frame budget")
