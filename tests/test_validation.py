import unittest

from service.validation import validate_prediction


KEYS = {"intent", "date", "time", "place"}
INTENTS = {"alarm_set", "alarm_query", "weather_query"}

VALID = {
    "intent": "alarm_set",
    "date": "tomorrow",
    "time": "seven am",
    "place": None,
}


class PredictionValidationTests(unittest.TestCase):
    def test_valid_json_object_is_accepted(self):
        self.assertEqual(validate_prediction(VALID, KEYS, INTENTS), VALID)

    def test_valid_json_string_is_accepted(self):
        import json
        self.assertEqual(
            validate_prediction(json.dumps(VALID), KEYS, INTENTS),
            VALID
        )

    def test_invalid_json_is_rejected(self):
        self.assertIsNone(validate_prediction("not json", KEYS, INTENTS))

    def test_missing_or_extra_keys_are_rejected(self):
        missing = dict(VALID)
        missing.pop("place")
        extra = dict(VALID, confidence=0.9)

        self.assertIsNone(validate_prediction(missing, KEYS, INTENTS))
        self.assertIsNone(validate_prediction(extra, KEYS, INTENTS))

    def test_invalid_intent_and_slot_types_are_rejected(self):
        invalid_intent = dict(VALID, intent="unknown")
        non_string_intent = dict(VALID, intent=123)
        invalid_slot = dict(VALID, date=123)

        self.assertIsNone(
            validate_prediction(invalid_intent, KEYS, INTENTS)
        )
        self.assertIsNone(
            validate_prediction(non_string_intent, KEYS, INTENTS)
        )
        self.assertIsNone(validate_prediction(invalid_slot, KEYS, INTENTS))


if __name__ == "__main__":
    unittest.main()
