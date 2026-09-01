"""Unit tests for LaElectronica API client."""

import unittest
from core.laelectronica_api import LaElectronicaClient


class TestLaElectronicaAPI(unittest.TestCase):

    def test_live_search(self):
        client = LaElectronicaClient()
        results = client.search_products("ESP32")
        self.assertGreater(len(results), 0)

        p = results[0]
        self.assertTrue(bool(p.title))
        self.assertGreater(p.price, 0)
        self.assertTrue(p.full_url.startswith("https://laelectronica.com.gt"))

    def test_best_match_fallback(self):
        client = LaElectronicaClient()
        best, candidates = client.find_best_match(["LM358N", "LM358", "Amplificador"])
        self.assertIsNotNone(best)
        self.assertGreater(len(candidates), 0)


if __name__ == "__main__":
    unittest.main()
