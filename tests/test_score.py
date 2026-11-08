import unittest

from tools.score import parse_prediction, score


GOLD = [{
    "id": "T1",
    "intent": "alarm_set",
    "date": "tomorrow",
    "time": "seven am",
    "place": None,
}]


class ScoringTests(unittest.TestCase):
    def test_parse_prediction_accepts_exact_schema(self):
        prediction = {
            "intent": "alarm_set",
            "date": "tomorrow",
            "time": "seven am",
            "place": None,
        }
        self.assertEqual(parse_prediction(prediction), prediction)

    def test_parse_prediction_rejects_invalid_json_and_extra_keys(self):
        self.assertIsNone(parse_prediction("not json"))
        self.assertIsNone(parse_prediction({
            "intent": "alarm_set",
            "date": None,
            "time": None,
            "place": None,
            "extra": True,
        }))

    def test_perfect_prediction_scores_one_hundred_percent(self):
        report = score([{
            "id": "T1",
            "prediction": (
                '{"intent":"alarm_set","date":"tomorrow",'
                '"time":"seven am","place":null}'
            ),
        }], GOLD)

        self.assertEqual(report["json_validity"], 100.0)
        self.assertEqual(report["full_frame"], 100.0)
        self.assertEqual(report["missing_predictions"], 0)

    def test_missing_prediction_counts_as_incorrect(self):
        report = score([], GOLD)

        self.assertEqual(report["json_validity"], 0.0)
        self.assertEqual(report["full_frame"], 0.0)
        self.assertEqual(report["missing_predictions"], 1)


if __name__ == "__main__":
    unittest.main()
