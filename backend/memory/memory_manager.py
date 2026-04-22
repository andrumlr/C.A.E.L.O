"""Long-term memory candidates (placeholder). Short-term continuity: `memory.short_term_buffer`."""


def extract_memory_candidate(user_input: str):
    # VERY BASIC placeholder logic
    if "i prefer" in user_input.lower():
        return {
            "category": "preference",
            "content": user_input,
            "state": "tentative"
        }
    return None
