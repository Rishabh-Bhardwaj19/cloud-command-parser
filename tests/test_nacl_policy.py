import json
import unittest
from pathlib import Path

from tools.nacl_sim import decide, load_rules


ROOT = Path(__file__).resolve().parents[1]


class PublicSubnetPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_rules(ROOT / "network" / "nacl.json")
        cls.packet_files = [
            ROOT / "network" / "packets_sample.jsonl",
            ROOT / "network" / "packets_reply_examples.jsonl",
            ROOT / "network" / "packets_assignment_examples.jsonl",
        ]
        cls.packets = []
        for path in cls.packet_files:
            with path.open(encoding="utf-8") as file:
                cls.packets.extend(json.loads(line) for line in file if line.strip())

    def test_all_supplied_and_requirement_packets_match_expected(self):
        for packet in self.packets:
            with self.subTest(packet=packet["id"]):
                action, _ = decide(self.rules, packet)
                self.assertEqual(action, packet["expected"])

    def test_abusive_cidr_is_denied_before_web_allow(self):
        for port in (80, 443, 22, 8080):
            packet = {
                "direction": "inbound",
                "protocol": "tcp",
                "port": port,
                "address": "198.51.100.22",
            }
            with self.subTest(port=port):
                self.assertEqual(decide(self.rules, packet)[0], "deny")

    def test_http_and_https_are_open_for_other_sources(self):
        for port in (80, 443):
            packet = {
                "direction": "inbound",
                "protocol": "tcp",
                "port": port,
                "address": "203.0.113.25",
            }
            with self.subTest(port=port):
                self.assertEqual(decide(self.rules, packet)[0], "allow")

    def test_ssh_is_allowed_only_from_management_subnet(self):
        allowed = {
            "direction": "inbound",
            "protocol": "tcp",
            "port": 22,
            "address": "10.20.5.130",
        }
        denied = {**allowed, "address": "10.20.5.160"}
        self.assertEqual(decide(self.rules, allowed)[0], "allow")
        self.assertEqual(decide(self.rules, denied)[0], "deny")

    def test_app_replies_and_outbound_client_replies_are_allowed(self):
        inbound_reply = {
            "direction": "inbound",
            "protocol": "tcp",
            "port": 60000,
            "address": "10.20.1.20",
        }
        outbound_reply = {
            "direction": "outbound",
            "protocol": "tcp",
            "port": 60000,
            "address": "203.0.113.25",
        }
        self.assertEqual(decide(self.rules, inbound_reply)[0], "allow")
        self.assertEqual(decide(self.rules, outbound_reply)[0], "allow")

    def test_only_tcp_8000_is_allowed_to_app_subnet(self):
        allowed = {
            "direction": "outbound",
            "protocol": "tcp",
            "port": 8000,
            "address": "10.20.1.20",
        }
        denied = {**allowed, "port": 1000}
        self.assertEqual(decide(self.rules, allowed)[0], "allow")
        self.assertEqual(decide(self.rules, denied)[0], "deny")


if __name__ == "__main__":
    unittest.main()
