import asyncio
from pathlib import Path
from typing import Optional

from dnd.narrator import PlayerContext, ResolvedAction
from llm.llm_util import get_llm_response

_PROMPTS_DIR = Path(__file__).parent / "prompts"

DEFAULT_AI_MODEL = "deepseek/deepseek-v4.1-flash"


async def generate_action(
    player: PlayerContext,
    scene_narrative: str,
    recent_actions: Optional[list[ResolvedAction]] = None,
    story_so_far: Optional[str] = None,
    model: str = DEFAULT_AI_MODEL,
) -> str:
    """Generate an in-character action for an AI player."""
    params = {
        "player_name": player.name,
        "player_class": player.character_class,
        "player_description": player.character_description,
        "scene_narrative": scene_narrative,
        "recent_actions": [
            {"player_name": a.player_name, "text": a.text, "outcome": a.outcome}
            for a in (recent_actions or [])
        ],
        "story_so_far": story_so_far or "",
    }
    text = await asyncio.to_thread(
        get_llm_response,
        str(_PROMPTS_DIR / "ai_player_action.jinja2"),
        params,
        model_name=model,
    )
    return text.strip().strip('"')
