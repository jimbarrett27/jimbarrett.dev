"""Unit tests for the pure parts of the tapestry storage layout (no GCS access)."""

from tapestry.storage import model_variant, panel_variant


def test_model_variant_slugifies_a_model_id():
    assert model_variant("anthropic/claude-opus-4.7") == "anthropic-claude-opus-4.7"
    assert model_variant("deepseek/deepseek-v4-pro") == "deepseek-deepseek-v4-pro"


def test_model_variant_is_a_safe_object_name():
    # No slashes (which would nest the alternate under a bogus path) and no
    # spaces/uppercase, so the manifest value and the blob name always agree.
    variant = model_variant("MoonshotAI/Kimi K2.7 (code)")
    assert variant == "moonshotai-kimi-k2.7-code"
    assert "/" not in variant and variant == variant.lower()


def test_model_variant_is_stable_for_the_same_model():
    # Re-archiving the same day+model must rewrite one object, not accumulate.
    assert model_variant("openai/gpt-5.4") == model_variant("openai/gpt-5.4")


def test_panel_variant_separates_renderings_that_share_a_model():
    """The case backfill hits: same model, changed prompt.

    Keyed on the model alone these collide, so archiving a redraw would either
    overwrite the artwork it was meant to preserve or be skipped as a no-op.
    """
    old = panel_variant("deepseek/deepseek-v4-pro", "old prompt")
    new = panel_variant("deepseek/deepseek-v4-pro", "new prompt")

    assert old != new
    assert old.startswith("deepseek-deepseek-v4-pro-")


def test_panel_variant_is_stable_for_the_same_rendering():
    # What makes re-running a backfill idempotent rather than piling up copies.
    assert panel_variant("openai/gpt-5.4", "a prompt") == panel_variant(
        "openai/gpt-5.4", "a prompt"
    )


def test_panel_variant_tolerates_a_panel_missing_its_provenance():
    assert panel_variant(None, None).startswith("unknown-")
