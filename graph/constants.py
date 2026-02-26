"""
Shared constants for the agent graph.
Used across builder, validation, and other nodes to ensure consistency.
"""

# Default max validation loop iterations (configurable via MAX_VALIDATION_ITERATIONS env)
DEFAULT_MAX_VALIDATION_ITERATIONS = 3

# User-facing message when validation fails or answer cannot be confirmed from sources.
# Used in both validation node and finalize_response to prevent stale draft leakage.
SAFE_CLARIFICATION_MSG = (
    "I can't confirm that answer from the retrieved documents. "
    "Please specify which regulator/meeting series you mean "
    "(e.g., FOMC, Basel, CFTC, SEC), or add a keyword like 'FOMC minutes'."
)

# Shorter variant when query mentions "meeting"
SAFE_MEETING_MSG = (
    "Which meeting series do you mean (e.g., FOMC, Basel Committee, CFTC, SEC)? "
    "I can then pull the most recent related documents."
)
