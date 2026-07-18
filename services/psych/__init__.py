"""Psychology-informed conversation enhancement.

Subtle techniques from counseling psychology (OARS framework) integrated
into the existing prompt system — not a therapy module, but a way to make
the AI a more attentive, empathetic conversationalist.
"""

from services.psych.life_domains import (
    get_life_domain_context,
    update_life_domains,
)
from services.psych.entry_point import (
    get_curiosity_hint,
    update_curiosity_queue,
)

__all__ = [
    "get_life_domain_context",
    "update_life_domains",
    "get_curiosity_hint",
    "update_curiosity_queue",
]
