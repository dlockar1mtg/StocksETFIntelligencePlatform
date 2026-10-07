from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.market.priority_batch_route_discovery_pilot_execution import execute_pilot, validate_inputs


class Phase36B3ITests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(Path("config/market/priority_batch_route_discovery_pilot_execution_policy.json").read_text())
        self.pilot = {
            "records": [
                {
                    "security_id": f"US-ETF-T{i}",
                    "symbol": f"T{i}",
                    "sec_cik": "0001100663",
                    "sec_series_id": f"S00000000{i}",
                    "sec_class_contract_id": f"C00000000{i}",
                    "pilot_state": "DISCOVERY_PENDING",
                    "source_capture_authorized": False,
                    "taxonomy_dimensions_assigned": False,
                    "taxonomy_classification_authorized": False,
                    "production_taxonomy_authority": False,
                    "discovery_requests": [
                        {"route_type": "ISHARES_SYMBOL_PRODUCT_DISCOVERY", "discovery_state": "DISCOVERY_PENDING", "capture_authorized": False},
                        {"route_type": "SEC_SERIES_CLASS_FILING_DISCOVERY", "discovery_state": "DISCOVERY_PENDING", "capture_authorized": False},
                    ],
                }
                for i in range(5)
            ]
        }

    def test_valid_inputs_pass(self):
        validate_inputs(self.pilot, self.policy)

    def test_count_drift_fails_closed(self):
        with self.assertRaises(ValueError):
            validate_inputs({"records": self.pilot["records"][:4]}, self.policy)

    def test_duplicate_identity_fails_closed(self):
        self.pilot["records"][1]["security_id"] = self.pilot["records"][0]["security_id"]
        with self.assertRaises(ValueError):
            validate_inputs(self.pilot, self.policy)

    def test_nonpending_request_fails_closed(self):
        self.pilot["records"][0]["discovery_requests"][0]["discovery_state"] = "DISCOVERY_RESOLVED"
        with self.assertRaises(ValueError):
            validate_inputs(self.pilot, self.policy)

    def test_user_agent_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                execute_pilot(self.pilot, self.policy, Path(tmp)/"out.json", Path(tmp)/"raw", "invalid")

    def test_execution_preserves_raw_hashes_and_no_capture_authority(self):
        def fetcher(url, user_agent, timeout):
            payload = b"S000000000 C000000000 T0 product evidence"
            final = "https://www.ishares.com/us/products/test/T0" if "ishares" in url else url
            return {"payload": payload, "http_status": 200, "final_url": final, "redirect_chain": [url, final], "error": None}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"out.json"
            result = execute_pilot(self.pilot, self.policy, out, Path(tmp)/"raw", "Tester test@example.com", fetcher=fetcher, sleeper=lambda _: None)
            self.assertEqual(len(list((Path(tmp)/"raw").glob("*.bin"))), 10)
            for record in result["records"]:
                self.assertFalse(record["source_capture_authorized"])
                for request in record["discovery_requests"]:
                    self.assertRegex(request["payload_sha256"], r"^[a-f0-9]{64}$")
                    self.assertFalse(request["capture_authorized"])

    def test_generic_landing_page_not_resolved(self):
        def fetcher(url, user_agent, timeout):
            return {"payload": b"generic search", "http_status": 200, "final_url": url, "redirect_chain": [url], "error": None}
        with tempfile.TemporaryDirectory() as tmp:
            result = execute_pilot(self.pilot, self.policy, Path(tmp)/"out.json", Path(tmp)/"raw", "Tester test@example.com", fetcher=fetcher, sleeper=lambda _: None)
            states = {r["discovery_state"] for rec in result["records"] for r in rec["discovery_requests"]}
            self.assertIn("GENERIC_LANDING_PAGE", states)

    def test_official_domain_policy_exact(self):
        self.assertEqual(self.policy["official_domains"], ["sec.gov", "ishares.com", "blackrock.com"])

    def test_downstream_authorities_remain_false(self):
        blocked = [k for k, v in self.policy["authority"].items() if k not in {"route_discovery_pilot_execution", "route_discovery_pilot_result_analysis"}]
        self.assertTrue(all(self.policy["authority"][key] is False for key in blocked))

    def test_full_batch_capture_remains_false(self):
        self.assertFalse(self.policy["authority"]["priority_batch_source_capture"])


if __name__ == "__main__":
    unittest.main()
