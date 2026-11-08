import json
import tempfile
import unittest
from pathlib import Path

from tools.nacl_sim import decide, load_rules


class NaclSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.rules_path = Path(self.temp_dir.name) / "nacl.json"

        rules = {
            "inbound": [
                {
                    "rule": 100,
                    "protocol": "tcp",
                    "port_from": 22,
                    "port_to": 22,
                    "cidr": "0.0.0.0/0",
                    "action": "deny",
                },
                {
                    "rule": 110,
                    "protocol": "tcp",
                    "port_from": 443,
                    "port_to": 443,
                    "cidr": "192.0.2.0/24",
                    "action": "allow",
                },
            ],
            "outbound": [],
        }

        self.rules_path.write_text(json.dumps(rules), encoding="utf-8")
        self.rules = load_rules(self.rules_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_allowed_https_matches_first_allow_rule(self):
        packet = {
            "direction": "inbound",
            "protocol": "tcp",
            "port": 443,
            "address": "192.0.2.55",
        }
        self.assertEqual(decide(self.rules, packet), ("allow", 110))

    def test_ssh_is_denied_by_earlier_rule(self):
        packet = {
            "direction": "inbound",
            "protocol": "tcp",
            "port": 22,
            "address": "192.0.2.55",
        }
        self.assertEqual(decide(self.rules, packet), ("deny", 100))

    def test_unmatched_packet_uses_default_deny(self):
        packet = {
            "direction": "inbound",
            "protocol": "tcp",
            "port": 8080,
            "address": "192.0.2.55",
        }
        self.assertEqual(decide(self.rules, packet), ("deny", None))


if __name__ == "__main__":
    unittest.main()
