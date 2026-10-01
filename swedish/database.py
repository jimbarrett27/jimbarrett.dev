"""
Database operations for the Swedish flashcards system.

Uses SQLAlchemy ORM for database access. The public API uses the FlashCard
dataclass from flash_card.py, with conversion to/from ORM models handled internally.
"""

import time
from typing import List, Optional

from sqlalchemy import select

from swedish.db_engine import get_engine, get_session
from swedish.flash_card import DailyWord, FlashCard, WordType
from swedish.orm_models import (
    Base,
    DailyWordORM,
    FlashCardORM,
    flashcard_orm_to_dataclass,
    flashcard_dataclass_to_orm,
)


def init_db():
    """Initialize the database schema."""
    engine = get_engine()
    Base.metadata.create_all(engine)


def add_card(word: str, word_type: WordType = WordType.UNKNOWN):
    """Add a new flashcard to the database.

    If the card already exists, this is a no-op.
    """
    with get_session() as session:
        # Check if card already exists
        existing = session.get(FlashCardORM, word)
        if existing is not None:
            return

        orm = FlashCardORM(
            word_to_learn=word,
            word_type=word_type.name,
            n_times_seen=0,
            difficulty=0.0,
            stability=0.0,
            last_review_epoch=0,
            next_review_min_epoch=0,
        )
        session.add(orm)


def get_card(word: str) -> Optional[FlashCard]:
    """Get a flashcard by word."""
    with get_session() as session:
        orm = session.get(FlashCardORM, word)
        if orm is None:
            return None
        return flashcard_orm_to_dataclass(orm)


def update_card(card: FlashCard):
    """Update an existing flashcard."""
    with get_session() as session:
        orm = session.get(FlashCardORM, card.word_to_learn)
        if orm is not None:
            orm.n_times_seen = card.n_times_seen
            orm.difficulty = card.difficulty
            orm.stability = card.stability
            orm.last_review_epoch = card.last_review_epoch
            orm.next_review_min_epoch = card.next_review_min_epoch
            orm.word_type = card.word_type.name


def get_due_cards() -> List[FlashCard]:
    """Get all cards that are due for review."""
    current_epoch = int(time.time())
    with get_session() as session:
        stmt = select(FlashCardORM).where(
            FlashCardORM.next_review_min_epoch <= current_epoch
        )
        orms = session.execute(stmt).scalars().all()
        return [flashcard_orm_to_dataclass(orm) for orm in orms]


def get_next_due_card() -> Optional[FlashCard]:
    """Get the next card due for review (earliest due date)."""
    with get_session() as session:
        stmt = (
            select(FlashCardORM)
            .order_by(FlashCardORM.next_review_min_epoch.asc())
            .limit(1)
        )
        orm = session.execute(stmt).scalar_one_or_none()
        if orm is None:
            return None
        return flashcard_orm_to_dataclass(orm)


def get_all_words() -> List[str]:
    """Get all words in the database."""
    with get_session() as session:
        stmt = select(FlashCardORM.word_to_learn)
        rows = session.execute(stmt).scalars().all()
        return list(rows)


def populate_db():
    """Populate the database from word files."""
    from util.constants import REPO_ROOT

    data_dir = REPO_ROOT / "swedish/data"

    files_map = {
        "verbs.txt": WordType.VERB,
        "nouns.txt": WordType.NOUN,
        "adjectives.txt": WordType.ADJECTIVE,
    }

    print(f"Populating database from {data_dir}...")

    existing_words = set(get_all_words())
    print(f"Found {len(existing_words)} existing words in DB.")

    for filename, word_type in files_map.items():
        filepath = data_dir / filename
        if not filepath.exists():
            print(f"Warning: {filename} not found at {filepath}")
            continue

        with open(filepath, "r") as f:
            count = 0
            skipped = 0
            for line in f:
                word = line.strip()
                if word:
                    if word in existing_words:
                        skipped += 1
                        continue

                    add_card(word, word_type)
                    count += 1
            print(
                f"Added {count} {word_type.name.lower()}s from {filename} "
                f"(skipped {skipped} existing)"
            )


def count_cards() -> int:
    """Count total number of flashcards."""
    with get_session() as session:
        stmt = select(FlashCardORM)
        return len(session.execute(stmt).scalars().all())


def get_all_cards() -> List[FlashCard]:
    """Get every flashcard."""
    with get_session() as session:
        orms = session.execute(select(FlashCardORM)).scalars().all()
        return [flashcard_orm_to_dataclass(orm) for orm in orms]


def get_daily_words(date: str) -> List[DailyWord]:
    """The panel words stored for an ISO date, in slot order (empty if none yet)."""
    with get_session() as session:
        stmt = (
            select(DailyWordORM)
            .where(DailyWordORM.date == date)
            .order_by(DailyWordORM.slot.asc())
        )
        return [
            DailyWord(
                word_to_learn=orm.word_to_learn,
                word_class=orm.word_class,
                translation=orm.translation,
                example_sv=orm.example_sv,
                example_en=orm.example_en,
            )
            for orm in session.execute(stmt).scalars().all()
        ]


def save_daily_words(date: str, words: List[DailyWord]):
    """Store a day's panel words, replacing anything already stored for that date."""
    with get_session() as session:
        session.query(DailyWordORM).filter(DailyWordORM.date == date).delete()
        for slot, word in enumerate(words):
            session.add(DailyWordORM(
                date=date,
                slot=slot,
                word_to_learn=word.word_to_learn,
                word_class=word.word_class,
                translation=word.translation,
                example_sv=word.example_sv,
                example_en=word.example_en,
            ))


def get_recent_daily_words(since_date: str) -> set[str]:
    """Words shown on the panel on or after an ISO date."""
    with get_session() as session:
        stmt = select(DailyWordORM.word_to_learn).where(DailyWordORM.date >= since_date)
        return set(session.execute(stmt).scalars().all())
