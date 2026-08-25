"""Semantic context must be present, populated, and different between worlds.

Its purpose is to give the LLM a genuine reasoning problem over unstructured
merchant context. Empty strings or identical boilerplate across worlds would
turn that back into a menu of enumerable options, which is the failure mode this
field exists to prevent.
"""

from __future__ import annotations

from src.world.generator import generate_world


def test_semantic_fields_are_populated() -> None:
    world = generate_world(21)
    semantic = world.semantic

    assert semantic.merchant_name.strip()
    assert semantic.vertical.strip()
    assert len(semantic.merchant_description.split()) > 12

    for field in (
        semantic.seasonal_events,
        semantic.competitor_events,
        semantic.customer_service_themes,
        semantic.inventory_notes,
        semantic.trading_notes,
    ):
        assert field, "semantic tuple is empty"
        assert all(text.strip() for text in field)
        assert all(len(text.split()) >= 3 for text in field)


def test_products_carry_names_categories_descriptions_and_inventory_age() -> None:
    world = generate_world(22)
    for product in world.products:
        assert product.name.strip()
        assert product.category.strip()
        assert len(product.description.split()) > 5
        assert product.inventory_age_days >= 0
        assert product.stock_status in {"fresh", "steady", "aging", "overstocked", "clearance"}
        assert 0.0 < product.contribution_margin < 1.0


def test_segments_carry_qualitative_notes() -> None:
    world = generate_world(23)
    for segment in world.segments:
        assert len(segment.notes.split()) > 8, "segment note is too thin to reason from"
        assert segment.behaviour_tags


def test_semantic_context_varies_across_worlds() -> None:
    worlds = [generate_world(seed) for seed in range(30, 46)]

    assert len({w.semantic.merchant_name for w in worlds}) > 1
    assert len({w.semantic.merchant_description for w in worlds}) > 1
    assert len({w.semantic.vertical for w in worlds}) > 1
    assert len({w.semantic.seasonal_events for w in worlds}) > 1
    assert len({w.semantic.competitor_events for w in worlds}) > 1
    assert len({w.semantic.customer_service_themes for w in worlds}) > 1
    assert len({w.semantic.trading_notes for w in worlds}) > 1
    assert len({tuple(p.name for p in w.products) for w in worlds}) > 1


def test_seasonality_index_matches_the_stated_calendar() -> None:
    """A world that says "Diwali gifting season" should behave like one.

    Context that contradicted the simulator would make the reasoning task
    unlearnable rather than hard, so the index is derived from the events chosen
    rather than sampled independently.
    """
    peak = [w for w in (generate_world(s) for s in range(1, 60)) if "Diwali gifting" in " ".join(w.semantic.seasonal_events)]
    lull = [w for w in (generate_world(s) for s in range(1, 60)) if "Post-Diwali lull" in " ".join(w.semantic.seasonal_events)]

    assert peak, "no world in the sample mentions the Diwali peak"
    assert lull, "no world in the sample mentions the post-Diwali lull"
    assert max(w.params.seasonality_index for w in peak) > min(
        w.params.seasonality_index for w in lull
    )
