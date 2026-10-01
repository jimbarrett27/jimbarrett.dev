from enum import Enum, auto
from dataclasses import dataclass

class WordType(Enum):
    VERB = auto()
    ADJECTIVE = auto()
    NOUN = auto()
    UNKNOWN = auto()

@dataclass
class FlashCard:

    difficulty: float
    stability: float
    last_review_epoch: int
    next_review_min_epoch: int
    word_to_learn: str
    word_type: WordType = WordType.UNKNOWN
    n_times_seen: int = 0
    

@dataclass
class DailyWord:
    """One word on the TRMNL word-of-the-day panel, with its generated gloss."""

    word_to_learn: str
    word_class: str
    translation: str
    example_sv: str
    example_en: str
