"""Tests for saved schematic connectivity checks."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schematic  # noqa: E402
from tests._fakes import FakeFootprint, FakePad  # noqa: E402


class TestParseNetlist(unittest.TestCase):
    def test_extracts_reference_pin_nets(self):
        text = '''(export
\t(nets
\t\t(net
\t\t\t(code "1")
\t\t\t(name "Net-(C4-Pad1)")
\t\t\t(node
\t\t\t\t(ref "C4")
\t\t\t\t(pin "1")
\t\t\t)
\t\t\t(node
\t\t\t\t(ref "R11")
\t\t\t\t(pin "1")
\t\t\t)
\t\t)
\t)
)'''
        self.assertEqual(
            schematic.parse_netlist_pin_nets(text),
            {
                ("C4", "1"): "Net-(C4-Pad1)",
                ("R11", "1"): "Net-(C4-Pad1)",
            },
        )


class TestCompareFootprintNets(unittest.TestCase):
    def test_reports_stale_and_accepts_matching_pad(self):
        footprint = FakeFootprint(
            "C4",
            pads=[FakePad("1", 0, ""), FakePad("2", 7, "Net-(J4-Pin_2)")],
        )
        expected = {
            ("C4", "1"): "Net-(C4-Pad1)",
            ("C4", "2"): "Net-(J4-Pin_2)",
        }
        mismatches = schematic.compare_footprint_nets([footprint], expected)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]["reference"], "C4")
        self.assertEqual(mismatches[0]["pin"], "1")


if __name__ == "__main__":
    unittest.main()
