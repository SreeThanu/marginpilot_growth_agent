"""Strip the semantic context from a merchant view, changing nothing else.

The context-sensitivity ablation. If an agent's decisions are identical with the
merchant's situation removed, then whatever its prose says, it is not reasoning
from the situation — it is doing arithmetic on the numbers and narrating the
result. That failure mode is invisible in the output text, which is exactly why
it needs a paired experiment rather than a reading.

Everything the numbers carry survives: population, conversion, AOV, margin,
budget, catalogue prices, intervention depths and costs. Only the *narrative*
is removed — trading notes, support themes, competitor activity, seasonal
events, inventory commentary, segment descriptions, and the merchant's own
description of itself.
"""

from __future__ import annotations

import dataclasses

from src.eval.contracts import MerchantView, SegmentView
from src.world.schema import Product, SemanticContext

#: What a stripped world says instead of nothing. An empty string would be a
#: visibly broken prompt and might itself change behaviour; a neutral
#: placeholder keeps the shape of the input while removing its content.
_WITHHELD = "No information available."


def _blank_semantic(semantic: SemanticContext) -> SemanticContext:
    return SemanticContext(
        merchant_name=semantic.merchant_name,  # identity is not situational
        vertical=semantic.vertical,
        merchant_description=_WITHHELD,
        seasonal_events=(_WITHHELD,),
        competitor_events=(_WITHHELD,),
        customer_service_themes=(_WITHHELD,),
        inventory_notes=(_WITHHELD,),
        trading_notes=(_WITHHELD,),
    )


def _blank_product(product: Product) -> Product:
    """Keep the economics, drop the story.

    Price, cost and stock level are numbers a merchant reads off a system.
    The description and the stock-status label are narrative, and inventory age
    is the field the agent is most likely to reason from qualitatively.
    """
    return dataclasses.replace(
        product,
        name=f"Product {product.product_id}",
        category="Uncategorised",
        description=_WITHHELD,
        stock_status="unknown",
        inventory_age_days=0,
    )


def strip_semantic_context(view: MerchantView) -> MerchantView:
    """Return the same merchant with its situation withheld."""
    return dataclasses.replace(
        view,
        semantic=_blank_semantic(view.semantic),
        products=tuple(_blank_product(p) for p in view.products),
        segments=tuple(
            SegmentView(
                segment_id=s.segment_id,
                name=f"Segment {s.segment_id}",
                share=s.share,
                notes=_WITHHELD,
                behaviour_tags=(),
            )
            for s in view.segments
        ),
    )
