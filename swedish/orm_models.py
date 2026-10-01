"""
SQLAlchemy ORM models for the Swedish flashcards system.

These models are internal to the database layer. The public interface
uses the FlashCard dataclass from flash_card.py.
"""

from sqlalchemy import Integer, Float, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from swedish.flash_card import FlashCard, WordType


class Base(DeclarativeBase):
    pass


class FlashCardORM(Base):
    """SQLAlchemy model for flashcards table."""

    __tablename__ = "flashcards"

    word_to_learn: Mapped[str] = mapped_column(Text, primary_key=True)
    word_type: Mapped[str] = mapped_column(Text, nullable=True)
    n_times_seen: Mapped[int] = mapped_column(Integer, default=0)
    difficulty: Mapped[float] = mapped_column(Float, default=0.0)
    stability: Mapped[float] = mapped_column(Float, default=0.0)
    last_review_epoch: Mapped[int] = mapped_column(Integer, default=0)
    next_review_min_epoch: Mapped[int] = mapped_column(Integer, default=0)


def flashcard_orm_to_dataclass(orm: FlashCardORM) -> FlashCard:
    """Convert a FlashCardORM instance to a FlashCard dataclass."""
    word_type = WordType[orm.word_type] if orm.word_type else WordType.UNKNOWN
    return FlashCard(
        word_to_learn=orm.word_to_learn,
        word_type=word_type,
        n_times_seen=orm.n_times_seen or 0,
        difficulty=orm.difficulty or 0.0,
        stability=orm.stability or 0.0,
        last_review_epoch=orm.last_review_epoch or 0,
        next_review_min_epoch=orm.next_review_min_epoch or 0,
    )


def flashcard_dataclass_to_orm(card: FlashCard) -> FlashCardORM:
    """Convert a FlashCard dataclass to a FlashCardORM instance."""
    return FlashCardORM(
        word_to_learn=card.word_to_learn,
        word_type=card.word_type.name,
        n_times_seen=card.n_times_seen,
        difficulty=card.difficulty,
        stability=card.stability,
        last_review_epoch=card.last_review_epoch,
        next_review_min_epoch=card.next_review_min_epoch,
    )


class DailyWordORM(Base):
    """One of the day's words on the TRMNL panel, generated once and then re-read.

    Keyed by (date, slot) so the hourly rotation is a lookup, never a regeneration.
    """

    __tablename__ = "daily_words"

    date: Mapped[str] = mapped_column(String, primary_key=True)  # ISO, Stockholm
    slot: Mapped[int] = mapped_column(Integer, primary_key=True)
    word_to_learn: Mapped[str] = mapped_column(Text, nullable=False)
    word_class: Mapped[str] = mapped_column(Text, nullable=False, default="")
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    example_sv: Mapped[str] = mapped_column(Text, nullable=False)
    example_en: Mapped[str] = mapped_column(Text, nullable=False)
