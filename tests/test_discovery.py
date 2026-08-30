"""Unit tests for block auto-discovery (discovery.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import discovery  # noqa: E402
from tests._fakes import FakeBoard, FakeFootprint, FakePad  # noqa: E402


class _Net:
    def __init__(self, class_name=""):
        self.class_name = class_name

    def GetNetClass(self):
        class_name = self.class_name

        class NC:
            def GetName(self):
                return class_name

        return NC()


def _resistor(ref, x=0, y=0, net_codes=()):
    pads = [FakePad(str(i + 1), net_codes[i] if i < len(net_codes) else 0)
            for i in range(2)]
    return FakeFootprint(ref, value="10k", fp_name="R_0805", pads=pads, x=x, y=y)


class TestIsGlobalNet(unittest.TestCase):
    def _call(self, net_id, reference_len=2, pad_counts=None, net_names=None,
              net_objects=None, cfg=None):
        pad_counts = pad_counts or {}
        net_names = net_names or {}
        net_objects = net_objects or {}
        cfg = cfg or config.default_config()
        return discovery._is_global_net(
            net_id, reference_len, pad_counts, net_names, net_objects, cfg
        )

    def test_unconnected(self):
        self.assertTrue(self._call(0))
        self.assertTrue(self._call(-1))
        self.assertTrue(self._call(None))

    def test_high_pad_count(self):
        self.assertTrue(self._call(7, reference_len=2, pad_counts={7: 10}))

    def test_power_name(self):
        self.assertTrue(self._call(7, net_names={7: "GND"}))
        self.assertTrue(self._call(7, net_names={7: "+5V"}))

    def test_net_class_power(self):
        self.assertTrue(
            self._call(7, net_names={7: "SIGNAL7"}, net_objects={7: _Net("PWR")})
        )

    def test_internal_signal(self):
        self.assertFalse(self._call(7, net_names={7: "RELAY_CTRL"}))


class TestAutoDiscoverSuffix(unittest.TestCase):
    def test_suffix_strategy(self):
        # Reference block: R1_A, R2_A. Repeated block: R1_B, R2_B.
        ref = [_resistor("R1_A", 0, 0, (100, 200)), _resistor("R2_A", 2000, 0, (200, 300))]
        target = [_resistor("R1_B", 100000, 100000, (400, 500)),
                  _resistor("R2_B", 102000, 100000, (500, 600))]
        board = FakeBoard(ref + target)
        discovered = discovery.auto_discover_blocks(board, ref, [])
        self.assertEqual(len(discovered), 1)
        self.assertEqual(
            sorted(fp.GetReference() for fp in discovered[0]),
            ["R1_B", "R2_B"],
        )

    def test_no_reference(self):
        self.assertEqual(discovery.auto_discover_blocks(FakeBoard([]), [], []), [])


if __name__ == "__main__":
    unittest.main()
