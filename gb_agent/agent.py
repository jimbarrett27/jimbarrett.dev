"""The agent loop: an LLM calling tools until a limit runs out.

Written directly on LangChain's chat-model interface rather than with
``agents.Agent``, because a small local model needs control over its context:

- **Append-only.** llama-server reuses work for an unchanged prompt prefix, so
  appending a turn costs only the new tokens, while dropping old messages from
  the front forces the whole prompt to be re-read (minutes at 16k on this CPU).
- **Compaction.** Near the context limit the model writes notes for itself, and
  the context restarts from the system prompt, the goal, those notes and the
  current screen. Its scripts survive regardless; they're in the library.
- **Screenshots** come after the tool results as a user message (tool messages
  can't carry images everywhere), and only for the latest step.
"""

import base64
import logging
import time

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage

from agents.utils import content_to_str
from gb_agent.emulator import BUTTONS
from gb_agent.models import ModelProfile
from gb_agent.run import Run
from gb_agent.notes import SECTIONS, clean_notes, fit
from gb_agent.tools import Tools

logger = logging.getLogger(__name__)

MAX_IDLE_TURNS = 3  # replies without a tool call, in a row, before the run ends
LLM_RETRIES = 3

MAIN_INTRO = """\
You are playing a Game Boy game through tools. Nobody is watching live; keep going \
on your own until the run's budget runs out.

The idea is to build up a library of scripts: Python functions that do multi-step \
things for you (walk somewhere, get through a menu, mash through text), so you can \
decide *what* to do while your scripts handle *how*. Writing scripts is the main way \
you're expected to play:
- Write your first script early, even a small one, and run it.
- If you've done the same thing by hand twice, turn it into a script.
- If a script doesn't do what you expected, read its report, fix it with \
write_script, and run it again. Every run counts: there's no undo.
Pressing buttons directly is fine for a quick look, but don't play that way for long."""

SUB_INTRO = """\
You are a helper working for another agent that plays a Game Boy game. You have one \
job, given below. Work on it with your tools. When it's done, or you're sure you can't \
do it, call finish with a short summary: what you did, what happened, and anything \
the other agent should know. Only that summary goes back to it."""

GAME_API = """\
Scripts and snippets run in a sandbox with `game`, which has:
  game.press(button) / game.release(button)   buttons: {buttons}
  game.tick(frames=1)      advance time; 60 frames is about one second
  game.tap(button, hold=2, after=6)   press, hold, release, wait
  game.frame               frames since the run started
  game.memory[addr]        read a byte (memory[a:b] for a list); memory is read-only
  game.screenshot()        the screen as a PIL image (160x144)
  game.note(label, value)  record an observation; it shows up in your report
A script is one file defining one function with the same name, taking `game` first, \
with a docstring, for example:
  def walk_left(game, tiles: int = 1) -> int:
      \"\"\"Walk left `tiles` tiles.\"\"\"
      ...
Scripts can use each other: `from library.walk_left import walk_left`.

After each step you get a report (what happened, inputs used, how much of the screen \
changed, notes, errors) and a screenshot. Every step that touches the game is kept and \
spends frames."""

MAIN_CONTEXT = """\
Your context is limited. When it fills up it's cleared: you'll be asked for a quick \
summary, and everything else you've seen is forgotten, except your scripts and your \
notes. Keep your notes up to date with update_notes as you learn things, so you never \
lose track. Write them in four sections:
{sections} \
If something seems impossible with the tools you have, use report_blocker."""

SUBAGENTS = """\
You can also make sub-agents: helpers you design with define_subagent (instructions, \
some of your tools, which scripts they may run) and give one job at a time with \
run_subagent. A sub-agent starts with a fresh context and only its summary comes \
back, so long or fiddly jobs (getting through a conversation, reaching a place, \
getting a script to work) don't fill up your own context. Write clear \
instructions: it knows nothing except what you tell it."""

EVERY_REPLY = """\
Every reply should call a tool. If you want to think, write it briefly in the same \
reply as the tool call."""


def system_prompt(notes: str, *, instructions: str | None = None,
                  subagents: bool = False, state_help: str = "") -> str:
    """The main agent's system prompt, or a sub-agent's when given its instructions.

    ``state_help`` explains the game-state description at the top of each report,
    if the run has one.
    """
    parts = [SUB_INTRO if instructions else MAIN_INTRO, GAME_API.format(buttons=", ".join(BUTTONS))]
    if state_help:
        parts.append(state_help)
    if not instructions:
        parts.append(MAIN_CONTEXT.format(sections=SECTIONS))
        if subagents:
            parts.append(SUBAGENTS)
    parts.append(EVERY_REPLY)
    if instructions:
        parts.append(f"Your instructions, from the agent that made you:\n{instructions}")
    parts.append(f"The game: {notes or '(no notes)'}")
    return "\n\n".join(parts)


COMPACT_PROMPT = f"""\
Your context is nearly full and is about to be cleared. Rewrite your notes: they're \
all you'll have afterwards, besides your scripts. Keep what's still true, fix anything \
that's wrong, and add what you've learned. Use these sections, in this order:
{SECTIONS}
Don't copy the game state (where you are, people, exits, the map grid, party, bag): \
you'll be shown it fresh, along with the places you've been and what you've been \
told, which the game keeps track of. Where those and your notes disagree, the game \
is right: fix your notes. At most 2000 characters. Reply with the notes only, as \
plain text: no tool call.

Your current notes:
{{notes}}"""

NOTES_CHECK = """\
Notes check: before carrying on, call update_notes with your notes brought up to \
date, in the sections GOAL, STORY, MAP, LESSONS. Your current notes:
{notes}"""

NOTES_EVERY = 15  # the main agent's own calls between notes checks


def _image_part(png: bytes) -> dict:
    return {"type": "image_url",
            "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}


def _upscale(png: bytes, factor: int = 2) -> bytes:
    """Game Boy screens are tiny; doubling them helps vision models read text."""
    import io

    from PIL import Image

    image = Image.open(io.BytesIO(png))
    image = image.resize((image.width * factor, image.height * factor), Image.NEAREST)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _estimate_tokens(messages: list[AnyMessage]) -> int:
    total = 0
    for message in messages:
        content = message.content
        if isinstance(content, str):
            total += len(content) // 3
        else:
            for part in content:
                total += 300 if part.get("type") == "image_url" else len(part.get("text", "")) // 3
        total += sum(len(str(call)) // 3 for call in getattr(message, "tool_calls", []) or [])
    return total


class GameAgent:
    """The main agent, or (given ``instructions`` and a ``task``) a sub-agent.

    A sub-agent's ``tools`` are restricted by its spec; it ends when it calls
    finish, uses ``max_calls`` LLM calls, or the run hits a limit.
    """

    def __init__(self, run: Run, llm: BaseChatModel, profile: ModelProfile, *,
                 name: str = "main", describer: BaseChatModel | None = None,
                 tools: Tools | None = None, host=None, instructions: str | None = None,
                 task: str | None = None, max_calls: int | None = None):
        self.run = run
        self.profile = profile
        self.name = name
        self.base_llm = llm
        self.tools = tools or Tools(run, agent=name, host=host)
        schemas = self.tools.schemas()
        self.llm = llm.bind_tools(schemas)
        # Same tools in the prompt, so the server can reuse the cached prefix (the
        # tool definitions are part of it), but the model must answer in text.
        self.notes_llm = llm.bind_tools(schemas, tool_choice="none")
        self.describer = describer
        self.task = task
        self.max_calls = max_calls
        self.calls = 0  # this agent's own LLM calls
        self.system = SystemMessage(system_prompt(
            run.game.notes, instructions=instructions,
            subagents="run_subagent" in self.tools.allowed,
            state_help=run.game.state_help if run.reports_state else ""))
        self.messages: list[AnyMessage] = []
        self.context_tokens = 0  # as of the last call
        self.compactions = 0

    # -- messages -----------------------------------------------------------

    def _opening(self, notes: str | None = None) -> list[AnyMessage]:
        if self.task is not None:
            text = (f"Your job: {self.task}\n\nYou can use {self.max_calls} LLM calls and "
                    f"{self.tools.frames_left()} frames. {self.tools._budget()}\n\n"
                    "Call finish when you're done.")
            if notes:
                text += f"\n\nYour notes from earlier in this job:\n{notes}"
            text += self._state_now()
            return [self.system, self._with_screens(text, [
                (f"the screen now (frame {self.run.frame})", self.run.screenshot_png())])]
        c = self.run.config
        text = (f"Your goal: {c.goal}\n\nBudget: {c.frame_budget} frames "
                f"(about {c.frame_budget // 60} seconds of game time), {c.max_llm_calls} LLM "
                f"calls. {self.run.budget_line()}\n\nYour library has: "
                + (", ".join(i.name for i in self.run.library.scripts()) or "nothing yet")
                + ". Use list_scripts and read_script to look at them."
                + ("\n\nStart by writing a script of your own for something you expect to "
                   "do often, and run it." if not self.run.notes else "")
                + ("\n\nOnce you have a script or two, consider a sub-agent for a job that "
                   "takes many steps, such as exploring a room or getting through a "
                   "conversation. It keeps that work out of your own context."
                   if not self.run.notes and "run_subagent" in self.tools.allowed else ""))
        if (resumed := self.run.resumed_from) is not None:
            text += (f"\n\nThis picks up a game already in progress, where an earlier run "
                     f"stopped (its step {resumed.step}). Your notes and scripts are from then; "
                     "check them against the game now.")
        if self.run.notes:
            text += f"\n\nYour notes (kept across context clears):\n{self.run.notes}"
        if journal := self.run.journal_text():
            text += f"\n\n{journal}"
        text += self._state_now()
        return [self.system, self._with_screens(text, [
            (f"the screen now (frame {self.run.frame})", self.run.screenshot_png())])]

    def _state_now(self) -> str:
        state = self.run.state_text()
        return f"\n\nThe game now:\n{state}" if state else ""

    def _with_screens(self, text: str, images: list[tuple[str, bytes]]) -> HumanMessage:
        images = images[-self.profile.images_per_step:] if self.profile.images_per_step else []
        if not images:
            return HumanMessage(text)
        if not self.profile.vision:
            return HumanMessage(text + "\n\n" + "\n".join(
                f"[{caption}] {self._describe(png)}" for caption, png in images))
        parts: list[dict] = [{"type": "text", "text": text + "\n\nScreenshots: "
                              + ", ".join(caption for caption, _ in images)}]
        parts += [_image_part(_upscale(png)) for _, png in images]
        return HumanMessage(parts)

    def _describe(self, png: bytes) -> str:
        if self.describer is None:
            return "(no description available: this model can't see images)"
        reply = self._invoke(self.describer, [HumanMessage([
            {"type": "text", "text": "Describe this Game Boy screen in two or three "
             "sentences: what's shown, any text, and where the player is."},
            _image_part(_upscale(png))])], purpose="describe")
        return content_to_str(reply.content).strip()

    # -- the loop -----------------------------------------------------------

    def play(self) -> str:
        self.messages = self._opening()
        idle = 0
        while (reason := self._limit_reached()) is None:
            if self.context_tokens > self.profile.context_window * self.profile.compact_at:
                self._compact()
            try:
                response = self._invoke(self.llm, self.messages, purpose="act")
            except Exception as e:
                logger.exception("LLM call failed")
                return f"llm_error: {e}"
            self.messages.append(response)

            calls = list(response.tool_calls or [])
            bad = list(getattr(response, "invalid_tool_calls", None) or [])
            if not calls and not bad:
                idle += 1
                if idle >= MAX_IDLE_TURNS:
                    return "agent_stopped"
                self.messages.append(HumanMessage(
                    f"Keep going: call a tool. {self.tools._budget()}"))
                continue
            idle = 0

            images: list[tuple[str, bytes]] = []
            for call in calls:
                result = self.tools.call(call["name"], call.get("args"))
                self.messages.append(ToolMessage(result.text, tool_call_id=call["id"],
                                                 name=call["name"]))
                images += result.images
                self.run.log_agent({"agent": self.name, "kind": "tool", "tool": call["name"],
                                    "args": call.get("args"), "result": result.text,
                                    "step": self.run.step})
            for call in bad:
                text = (f"Error: couldn't read that tool call ({call.get('error') or 'bad JSON'}). "
                        "Arguments must be valid JSON.")
                self.messages.append(ToolMessage(text, tool_call_id=call.get("id") or "invalid",
                                                 name=call.get("name") or "unknown"))
            check = (self.task is None and "update_notes" in self.tools.allowed
                     and self.calls % NOTES_EVERY == 0)
            follow_up = (NOTES_CHECK.format(notes=self.run.notes or "(none yet)") if check
                         else "Call your next tool.")
            if images:
                self.messages.append(self._with_screens(
                    f"Screenshots from that step are below. {follow_up}", images))
            elif check:
                self.messages.append(HumanMessage(follow_up))
        return reason

    def _limit_reached(self) -> str | None:
        if self.tools.finished is not None:
            return "finished"
        if self.max_calls is not None and self.calls >= self.max_calls:
            return "max_calls"
        if self.task is not None and self.tools.frames_left() == 0 and self.run.frames_left:
            return "max_frames"
        return self.run.limit_reached()

    def _invoke(self, llm, messages: list[AnyMessage], *, purpose: str) -> AIMessage:
        for attempt in range(LLM_RETRIES):
            started = time.monotonic()
            try:
                response = llm.invoke(messages)
                break
            except Exception:
                if attempt == LLM_RETRIES - 1:
                    raise
                logger.warning("LLM call failed (attempt %d), retrying", attempt + 1,
                               exc_info=True)
                time.sleep(5 * 2 ** attempt)
        usage = response.usage_metadata or {}
        input_tokens = usage.get("input_tokens") or _estimate_tokens(messages)
        output_tokens = usage.get("output_tokens") or len(content_to_str(response.content)) // 3
        self.run.llm_calls += 1
        self.calls += 1
        self.run.tokens += input_tokens + output_tokens
        self.run.save_manifest()  # kept current, so a killed run still has one
        if purpose == "act":
            self.context_tokens = input_tokens + output_tokens
        logger.info("%s call %d (%s): %.1fs, %d in / %d out, tools: %s", self.name,
                    self.run.llm_calls, purpose, time.monotonic() - started, input_tokens,
                    output_tokens, ", ".join(c["name"] for c in response.tool_calls or []) or "-")
        self.run.log_agent({
            "agent": self.name, "kind": "llm", "purpose": purpose,
            "seconds": round(time.monotonic() - started, 1),
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "text": content_to_str(response.content),
            "reasoning": (response.additional_kwargs or {}).get("reasoning_content"),
            "tool_calls": [{"name": c["name"], "args": c.get("args")}
                           for c in response.tool_calls or []],
            "invalid_tool_calls": [dict(c) for c in getattr(response, "invalid_tool_calls", [])],
            "llm_calls": self.run.llm_calls, "step": self.run.step,
        })
        return response

    def _compact(self) -> None:
        """Clear the context; the model's rewritten notes are what carries over."""
        # Appended to the existing context, so only the request itself is new input.
        request = self.messages + [HumanMessage(COMPACT_PROMPT.format(
            notes=self.run.notes or "(none yet)"))]
        try:
            reply = content_to_str(self._invoke(self.notes_llm, request,
                                                purpose="compact").content)
        except Exception:
            logger.exception("compaction failed; keeping the old notes")
            reply = ""
        notes = fit(clean_notes(reply))
        if not notes:
            logger.warning("compaction gave no usable notes; keeping the old ones")
        if notes and self.task is None:
            self.run.set_notes(notes, agent=self.name)
        self.compactions += 1
        self.run.log_agent({"agent": self.name, "kind": "compaction", "notes": notes,
                            "compactions": self.compactions, "step": self.run.step})
        # A sub-agent has no persistent notes, so its rewrite is passed along directly.
        self.messages = self._opening(notes if self.task is not None else None)
        self.context_tokens = _estimate_tokens(self.messages)
