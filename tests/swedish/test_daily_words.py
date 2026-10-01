"""Tests for swedish.daily_words -- choosing, storing and rotating the panel words."""

import json
import random
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine

from swedish import daily_words, db_engine
from swedish.database import add_card, get_daily_words
from swedish.flash_card import FlashCard, WordType
from swedish.orm_models import Base
from util import trmnl


@pytest.fixture
def temp_db():
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(test_engine)
    db_engine.set_engine(test_engine)
    yield test_engine
    db_engine.reset_engine()


def _card(word, difficulty=0.0, seen=0):
    return FlashCard(difficulty=difficulty, stability=1.0, last_review_epoch=0,
                     next_review_min_epoch=0, word_to_learn=word,
                     word_type=WordType.NOUN, n_times_seen=seen)


def _llm_answer(words):
    return "```json\n" + json.dumps([
        {"word": w, "word_class": "noun (en)", "translation": f"{w}-en",
         "example_sv": f"Jag ser {w}.", "example_en": f"I see {w}."}
        for w in words
    ]) + "\n```"


@pytest.fixture
def deck(temp_db):
    for i in range(20):
        add_card(f"en ord{i}", WordType.NOUN)
    return [f"en ord{i}" for i in range(20)]


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def respond(template_path, params, **_):
        calls.append(params)
        return _llm_answer(params["candidates"][:params["n_words"]])

    monkeypatch.setattr(daily_words, "get_llm_response", respond)
    return calls


def test_pick_candidates_excludes_recent_and_is_distinct():
    cards = [_card(f"w{i}") for i in range(30)]
    picked = daily_words.pick_candidates(cards, exclude={"w0", "w1"}, k=16,
                                         rng=random.Random(0))
    assert len(picked) == len(set(picked)) == 16
    assert not {"w0", "w1"} & set(picked)


def test_pick_candidates_favours_difficult_cards():
    cards = [_card(f"easy{i}", difficulty=2.0, seen=3) for i in range(50)]
    cards += [_card(f"hard{i}", difficulty=9.0, seen=3) for i in range(50)]
    rng = random.Random(1)
    hard = sum(w.startswith("hard")
               for _ in range(50)
               for w in daily_words.pick_candidates(cards, set(), k=10, rng=rng))
    assert hard > 0.75 * 500


def test_pick_candidates_falls_back_when_everything_is_recent():
    cards = [_card(f"w{i}") for i in range(5)]
    picked = daily_words.pick_candidates(cards, exclude={c.word_to_learn for c in cards})
    assert len(picked) == 5


def test_ensure_day_generates_once_then_reads(deck, fake_llm):
    day = date(2026, 10, 1)
    first = daily_words.ensure_day(day)
    second = daily_words.ensure_day(day)
    assert len(fake_llm) == 1
    assert len(first) == daily_words.WORDS_PER_DAY
    assert [w.word_to_learn for w in first] == [w.word_to_learn for w in second]
    assert get_daily_words(day.isoformat()) == first


def test_ensure_day_avoids_recent_words(deck, fake_llm):
    shown = {w.word_to_learn for w in daily_words.ensure_day(date(2026, 10, 1))}
    daily_words.ensure_day(date(2026, 10, 2))
    assert not shown & set(fake_llm[1]["candidates"])


def test_parse_drops_words_not_offered_and_malformed():
    response = json.dumps([
        {"word": "en ord1", "translation": "a", "example_sv": "b", "example_en": "c"},
        {"word": "hallucinated", "translation": "a", "example_sv": "b", "example_en": "c"},
        {"word": "en ord2", "translation": "", "example_sv": "b", "example_en": "c"},
        {"word": "en ord1", "translation": "a", "example_sv": "b", "example_en": "c"},
    ])
    parsed = daily_words._parse(response, ["en ord1", "en ord2"])
    assert [w.word_to_learn for w in parsed] == ["en ord1"]


def test_ensure_day_retries_once_on_bad_output(deck, monkeypatch):
    answers = iter(["not json", None])

    def respond(template_path, params, **_):
        answer = next(answers)
        return answer if answer else _llm_answer(params["candidates"][:4])

    monkeypatch.setattr(daily_words, "get_llm_response", respond)
    assert len(daily_words.ensure_day(date(2026, 10, 1))) == 4


def test_ensure_day_stores_nothing_when_llm_keeps_failing(deck, monkeypatch):
    monkeypatch.setattr(daily_words, "get_llm_response", lambda *a, **k: "[]")
    with pytest.raises(ValueError):
        daily_words.ensure_day(date(2026, 10, 1))
    assert get_daily_words("2026-10-01") == []


def test_slot_cycles_through_the_day():
    slots = [daily_words.current_slot(datetime(2026, 10, 1, h)) for h in range(8)]
    assert slots == [0, 1, 2, 3, 0, 1, 2, 3]


def test_merge_variables_fit_trmnl_payload(deck, fake_llm):
    now = datetime(2026, 10, 1, 14)
    variables = daily_words.current_merge_variables(now=now)
    assert variables["position"] == "3 / 4"
    assert variables["date"] == "1 OCT"
    trmnl.build_payload(variables)  # raises if over 2KB


def test_long_words_get_smaller_type():
    assert daily_words._font_size("att skrämma bort") < daily_words._font_size("en klippa")
