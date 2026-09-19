#!/usr/bin/env python
"""Run a full AI-vs-AI game for system testing.

Usage:
    uv run python -m dnd.run_test_game [--rounds N] [--players N]

Plays through N rounds with AI-controlled players against the real narrator,
logging everything so you can read through the story and debug the flow.
"""

import argparse
import asyncio
import logging
import sys

from sqlalchemy import create_engine

from dnd import database as db
from dnd import db_engine
from dnd.ai_player import generate_action
from dnd.game_manager import GameManager, ActionResult, _player_context
from dnd.models import Base
from dnd.narrator import (
    Narrator,
    NarratorContext,
    PlayerContext,
    ResolvedAction,
    EncounterContext,
    NpcContext,
)

# ── Logging ──────────────────────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s %(levelname)-5s %(message)s"
DATE_FORMAT = "%H:%M:%S"


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logging.root.handlers = [handler]
    logging.root.setLevel(level)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    # llm_util logs every request/response — useful in verbose, noisy otherwise
    logging.getLogger("llm.llm_util").setLevel(logging.DEBUG if verbose else logging.WARNING)


logger = logging.getLogger("dnd.test_game")


def log_divider(title: str = ""):
    logger.info("")
    logger.info("=" * 60)
    if title:
        logger.info(f"  {title}")
        logger.info("=" * 60)


def log_narrative(text: str):
    for line in text.strip().split("\n"):
        logger.info(f"  📖 {line}")


def log_action_result(player_name: str, action_text: str, result: ActionResult):
    logger.info(f"  ⚔️  {player_name}: \"{action_text}\"")
    if result.roll:
        r = result.roll
        logger.info(f"     🎲 {r.description}")
    elif result.outcome:
        logger.info(f"     🎲 (narrative, no check)")
    if result.outcome:
        for line in result.outcome.strip().split("\n"):
            logger.info(f"     → {line}")


# ── Test characters ──────────────────────────────────────────────────────────

TEST_PLAYERS = [
    {
        "user_id": 9001,
        "display_name": "Thornwick",
        "character_class": "Wizard",
        "character_description": "An elderly wizard with a long grey beard and a habit of talking to his staff. "
        "Cautious and analytical, he prefers to understand a situation before acting.",
    },
    {
        "user_id": 9002,
        "display_name": "Brynn",
        "character_class": "Ranger",
        "character_description": "A young ranger with sharp eyes and a quiet demeanour. "
        "She trusts her instincts and prefers action to deliberation.",
    },
    {
        "user_id": 9003,
        "display_name": "Galdric",
        "character_class": "Paladin",
        "character_description": "A boisterous paladin who charges headfirst into danger. "
        "Fiercely loyal to his companions, occasionally reckless.",
    },
]

TEST_CONTEXT = NarratorContext(
    narrator_context=(
        "You are narrating a dark fantasy adventure. The world is dangerous and mysterious. "
        "Magic is real but unpredictable. NPCs have their own agendas. "
        "Reward creative player actions and let the consequences of failures be interesting."
    ),
    adventure_name="The Cursed Castle",
    adventure_description=(
        "A group of adventurers has been hired to investigate strange occurrences "
        "at Castle Dreadmere, abandoned for decades but recently the source of unearthly lights and sounds."
    ),
    scene_name="The Castle Gates",
    scene_description=(
        "The party stands before the rusted iron gates of Castle Dreadmere. "
        "The castle looms against a bruised sky, its towers crumbling. "
        "Thick fog clings to the ground. Through the gates, a courtyard of cracked stone "
        "leads to the main doors, which hang ajar. Faint green light pulses from within."
    ),
    encounters=[
        EncounterContext(
            name="The Rusted Gate",
            description="The iron gate is chained shut with a heavy rusted lock.",
            skill="Athletics",
            dc=12,
        ),
        EncounterContext(
            name="The Whispering Fog",
            description="The fog seems to murmur. Listening carefully might reveal something.",
            skill="Perception",
            dc=14,
        ),
        EncounterContext(
            name="The Warding Glyphs",
            description="Faint symbols are etched into the gateposts, barely visible.",
            skill="Arcana",
            dc=15,
        ),
    ],
    npcs=[
        NpcContext(
            name="Old Maren",
            description="A hunched villager who followed the party, clutching a lantern. Claims to know the castle's history.",
            motivation="Wants the party to retrieve a family heirloom from inside.",
        ),
    ],
)


# ── Game runner ──────────────────────────────────────────────────────────────

async def run_game(num_rounds: int, num_players: int, ai_model: str):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db_engine.set_engine(engine)

    narrator = Narrator(context=TEST_CONTEXT)
    manager = GameManager(narrator=narrator)
    chat_id = 1

    try:
        # Create game and add players
        log_divider("GAME SETUP")
        manager.create_game(chat_id)
        players_to_use = TEST_PLAYERS[:num_players]

        for p in players_to_use:
            manager.join_game(
                chat_id,
                user_id=p["user_id"],
                display_name=p["display_name"],
                character_class=p["character_class"],
                character_description=p["character_description"],
            )
            logger.info(f"  Joined: {p['display_name']} ({p['character_class']})")
            logger.info(f"          {p['character_description']}")

        # Start
        log_divider("GAME START")
        narrative, first_player = await manager.start_game(chat_id)
        log_narrative(narrative)

        # Play rounds
        for round_num in range(1, num_rounds + 1):
            log_divider(f"ROUND {round_num}")

            round_done = False
            while not round_done:
                current = manager.get_current_player(chat_id)
                if not current:
                    break

                player_ctx = _player_context(current)

                # Gather context for the AI player
                game = db.get_active_game(chat_id)
                round_ = db.get_current_round(game.id)
                actions = db.get_actions_for_round(round_.id)
                players = db.get_players(game.id)
                recent = []
                for a in actions:
                    if a.outcome is None:
                        continue
                    p = next((p for p in players if p.id == a.player_id), None)
                    name = p.display_name if p else "Unknown"
                    recent.append(ResolvedAction(player_name=name, text=a.text, outcome=a.outcome))

                story_so_far = manager.get_story(chat_id)

                logger.info(f"  🎭 {current.display_name}'s turn ({current.character_class or 'Adventurer'})")

                action_text = await generate_action(
                    player=player_ctx,
                    scene_narrative=round_.narrative or "",
                    recent_actions=recent,
                    story_so_far=story_so_far if round_num > 1 else None,
                    model=ai_model,
                )

                result = await manager.submit_action(chat_id, current.user_id, action_text)
                log_action_result(current.display_name, action_text, result)

                if result.round_complete:
                    round_done = True
                    log_divider(f"ROUND {round_num} COMPLETE")
                    if result.new_narrative:
                        log_narrative(result.new_narrative)

        # Final story
        log_divider("FULL STORY")
        story = manager.get_story(chat_id)
        for line in story.split("\n"):
            logger.info(f"  {line}")

        manager.finish_game(chat_id)
        logger.info("")
        logger.info("Game finished.")

    finally:
        db_engine.reset_engine()


def main():
    parser = argparse.ArgumentParser(description="Run an AI-vs-AI D&D test game")
    parser.add_argument("--rounds", type=int, default=3, help="Number of rounds to play (default: 3)")
    parser.add_argument("--players", type=int, default=3, help="Number of players (default: 3, max: 3)")
    parser.add_argument("--model", type=str, default="deepseek/deepseek-v4.1-flash",
                        help="AI player model (default: deepseek/deepseek-v4.1-flash)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logs including full LLM prompts")
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)
    asyncio.run(run_game(
        num_rounds=args.rounds,
        num_players=min(args.players, len(TEST_PLAYERS)),
        ai_model=args.model,
    ))


if __name__ == "__main__":
    main()
