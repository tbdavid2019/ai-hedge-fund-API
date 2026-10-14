import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure src is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from tools.jev_client import (
    build_jev_request,
    normalize_jev_response,
    extract_system_and_user_prompts,
    call_systemone_with_failover,
    PRIMARY_URL,
    FALLBACK2_URL,
    FALLBACK3_URL,
)


class TestJevClient(unittest.TestCase):
    def test_build_jev_request(self):
        req = build_jev_request("System text", "User text", model="clef-flash")
        self.assertEqual(req["model"], "clef-flash")
        self.assertEqual(req["state"]["investor_prompt"], "System text")
        self.assertEqual(req["state"]["financial_snapshot"], "User text")
        self.assertIn("direction", req["questions"])
        self.assertIn("bullish_strength", req["questions"])
        self.assertIn("bearish_strength", req["questions"])

    def test_extract_prompts(self):
        sys_p, usr_p = extract_system_and_user_prompts("Just user prompt string")
        self.assertEqual(usr_p, "Just user prompt string")
        self.assertTrue(len(sys_p) > 0)

    def test_normalize_jev_response_bullish(self):
        mock_raw = {
            "model": "clef-flash",
            "answers": {
                "direction": {
                    "type": "choice",
                    "choice": "bullish",
                    "probabilities": {"bullish": 0.85, "bearish": 0.05, "neutral": 0.10},
                    "confidence": 0.85
                },
                "bullish_strength": {
                    "type": "score",
                    "score": 3.0,
                    "probabilities": {"0": 0.0, "1": 0.05, "2": 0.15, "3": 0.60, "4": 0.20}
                }
            }
        }
        res = normalize_jev_response(mock_raw, include_bilingual=True)
        self.assertEqual(res["signal"], "bullish")
        self.assertEqual(res["confidence"], 75.0)
        self.assertIn("看多", res["reasoning"])
        self.assertIn("Bullish", res["reasoning"])

    def test_normalize_jev_response_neutral(self):
        mock_raw = {
            "model": "clef-flash",
            "answers": {
                "direction": {
                    "type": "choice",
                    "choice": "neutral",
                    "probabilities": {"bullish": 0.33, "bearish": 0.33, "neutral": 0.34},
                    "confidence": 0.34
                }
            }
        }
        res = normalize_jev_response(mock_raw)
        self.assertEqual(res["signal"], "neutral")
        self.assertEqual(res["confidence"], 50.0)

    @patch("tools.jev_client.requests.post")
    def test_call_failover_to_fallback2(self, mock_post):
        # First call fails, second call succeeds
        mock_resp_fail = MagicMock()
        mock_resp_fail.status_code = 500
        mock_resp_fail.text = "Internal error"

        mock_resp_success = MagicMock()
        mock_resp_success.status_code = 200
        mock_resp_success.json.return_value = {
            "model": "clef-flash",
            "answers": {
                "direction": {
                    "type": "choice",
                    "choice": "bearish",
                    "probabilities": {"bullish": 0.1, "bearish": 0.8, "neutral": 0.1},
                    "confidence": 0.8
                },
                "bearish_strength": {
                    "type": "score",
                    "score": 3.5
                }
            }
        }

        mock_post.side_effect = [mock_resp_fail, mock_resp_success]

        res = call_systemone_with_failover("System", "User")
        self.assertEqual(res["signal"], "bearish")
        self.assertEqual(res["confidence"], 87.5)
        self.assertEqual(res["provider_tier"], "Tier-2 Fallback (Clef-Flash-Q4)")
        self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
