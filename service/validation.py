"""Lightweight validation for command-parser JSON predictions."""

import json


def validate_prediction(raw, expected_keys, allowed_intents):
    """Return a valid four-key object, otherwise return None."""
    try:
        result = raw if isinstance(raw, dict) else json.loads(raw.strip())
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None

    if not isinstance(result, dict):
        return None

    if set(result.keys()) != set(expected_keys):
        return None

    intent = result.get("intent")
    if not isinstance(intent, str) or intent not in allowed_intents:
        return None

    for slot in ("date", "time", "place"):
        value = result.get(slot)
        if value is not None and not isinstance(value, str):
            return None

    return result
