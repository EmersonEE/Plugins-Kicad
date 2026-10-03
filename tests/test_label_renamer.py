"""Pruebas unitarias para core/label_renamer.py."""

import unittest
from core.label_renamer import LabelRenamer, RenamingRule


class TestLabelRenamer(unittest.TestCase):

    def setUp(self):
        self.renamer = LabelRenamer()

    def test_hierarchical_numbered_label(self):
        # OUT_1 -> OUT_2, OUT_3, OUT_4
        self.assertEqual(self.renamer.rename_label("OUT_1", 1), "OUT_1")
        self.assertEqual(self.renamer.rename_label("OUT_1", 2), "OUT_2")
        self.assertEqual(self.renamer.rename_label("OUT_1", 3), "OUT_3")
        self.assertEqual(self.renamer.rename_label("OUT_1", 4), "OUT_4")

    def test_global_un_numbered_label(self):
        # NC -> NC_2, NC_3
        # COM -> COM_2, COM_3
        # NA -> NA_2, NA_3
        self.assertEqual(self.renamer.rename_label("NC", 1), "NC")
        self.assertEqual(self.renamer.rename_label("NC", 2), "NC_2")
        self.assertEqual(self.renamer.rename_label("NC", 3), "NC_3")

        self.assertEqual(self.renamer.rename_label("COM", 2), "COM_2")
        self.assertEqual(self.renamer.rename_label("NA", 2), "NA_2")

    def test_power_exceptions(self):
        # +5V y GND no deben cambiar en ninguna copia
        for copy_idx in range(1, 10):
            self.assertEqual(self.renamer.rename_label("+5V", copy_idx), "+5V")
            self.assertEqual(self.renamer.rename_label("GND", copy_idx), "GND")
            self.assertEqual(self.renamer.rename_label("gnd", copy_idx), "gnd")
            self.assertEqual(self.renamer.rename_label("+3V3", copy_idx), "+3V3")

    def test_zero_padding_preservation(self):
        # OUT_01 -> OUT_02, OUT_03
        self.assertEqual(self.renamer.rename_label("OUT_01", 1), "OUT_01")
        self.assertEqual(self.renamer.rename_label("OUT_01", 2), "OUT_02")
        self.assertEqual(self.renamer.rename_label("OUT_01", 10), "OUT_10")

    def test_multiple_numbers_in_label(self):
        # CH1_DATA_1 -> CH1_DATA_2, CH1_DATA_3
        self.assertEqual(self.renamer.rename_label("CH1_DATA_1", 2), "CH1_DATA_2")
        self.assertEqual(self.renamer.rename_label("CH1_DATA_1", 3), "CH1_DATA_3")

    def test_unseparated_numbers(self):
        # SIG1 -> SIG2, SIG3
        self.assertEqual(self.renamer.rename_label("SIG1", 2), "SIG2")
        self.assertEqual(self.renamer.rename_label("SIG1", 5), "SIG5")

    def test_custom_exceptions(self):
        rule = RenamingRule(exceptions={"+5V", "GND", "SYNC_BUS"})
        renamer = LabelRenamer(rule)
        self.assertEqual(renamer.rename_label("SYNC_BUS", 2), "SYNC_BUS")
        self.assertEqual(renamer.rename_label("OTHER_BUS", 2), "OTHER_BUS_2")


if __name__ == "__main__":
    unittest.main()
