"""AI meme generator — picks the best template and writes the text."""

import logging

from langchain_core.messages import HumanMessage

from agents import Agent
from agents.config import get_llm
from memes import tools as meme_tools

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a meme generator. Given a topic or prompt, pick the single best \
meme template and fill in the text to make it funny.

Rules:
- Keep text SHORT — memes work best with punchy, concise text.
- Match the joke structure to the template (read the tool descriptions carefully).
- Use exactly one tool call. Do not explain yourself, just make the meme.
"""

DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"


def generate_meme(
    prompt: str,
    model: str = DEFAULT_MODEL,
    exclude_templates: list[str] | None = None,
) -> tuple[bytes, str, str]:
    """Generate a meme from a text prompt.

    Returns:
        (png_bytes, template_name, agent_text) tuple.
    """
    meme_tools.last_render = None

    tools = meme_tools.ALL_TOOLS
    if exclude_templates:
        tools = [t for t in tools if t.name not in exclude_templates]

    llm = get_llm(model=model, temperature=1.0)
    agent = Agent(
        name="meme_generator",
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        llm=llm,
    )

    result = agent.invoke([HumanMessage(content=prompt)])

    if meme_tools.last_render is None:
        raise RuntimeError("Agent did not produce a meme — no tool was called")

    # Extract final text response from the agent
    agent_text = ""
    for msg in reversed(result["messages"]):
        if msg.type == "ai" and msg.content:
            from agents.utils import content_to_str
            agent_text = content_to_str(msg.content)
            break

    return (*meme_tools.last_render, agent_text)
