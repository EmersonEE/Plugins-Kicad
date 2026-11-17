"""Unit tests for SchematicParser and FootprintLibraryManager."""

import os
import shutil
import tempfile
import unittest

from core.parser import SchematicFile, SchematicProject, SchematicSymbol
from core.footprint_library import FootprintLibraryManager


SAMPLE_SCHEMATIC = """(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "bfe657c0-e4c3-4a68-802c-828858edf143")
	(paper "A3")
	(lib_symbols
		(symbol "Device:R"
			(property "Reference" "R" (at 0 0 0) (effects (font (size 1.27 1.27))))
			(property "Value" "R" (at 0 0 0) (effects (font (size 1.27 1.27))))
			(property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27))))
		)
	)
	(symbol
		(lib_id "Device:R")
		(at 100 100 0)
		(unit 1)
		(in_bom yes)
		(on_board yes)
		(uuid "11111111-1111-1111-1111-111111111111")
		(property "Reference" "R1"
			(at 100 98 0)
			(effects (font (size 1.27 1.27)))
		)
		(property "Value" "10k"
			(at 100 102 0)
			(effects (font (size 1.27 1.27)))
		)
		(property "Footprint" "Resistor_SMD:R_0603_1608Metric"
			(at 100 100 0)
			(hide yes)
			(effects (font (size 1.27 1.27)))
		)
	)
	(symbol
		(lib_id "Device:R")
		(at 120 100 0)
		(unit 1)
		(in_bom yes)
		(on_board yes)
		(uuid "22222222-2222-2222-2222-222222222222")
		(property "Reference" "R2"
			(at 120 98 0)
			(effects (font (size 1.27 1.27)))
		)
		(property "Value" "10k"
			(at 120 102 0)
			(effects (font (size 1.27 1.27)))
		)
		(property "Footprint" "Resistor_SMD:R_0603_1608Metric"
			(at 120 100 0)
			(hide yes)
			(effects (font (size 1.27 1.27)))
		)
	)
	(symbol
		(lib_id "power:+3.3V")
		(at 50 50 0)
		(unit 1)
		(in_bom no)
		(on_board yes)
		(uuid "33333333-3333-3333-3333-333333333333")
		(property "Reference" "#PWR01"
			(at 50 48 0)
			(effects (font (size 1.27 1.27)))
		)
		(property "Value" "+3.3V"
			(at 50 52 0)
			(effects (font (size 1.27 1.27)))
		)
		(property "Footprint" ""
			(at 50 50 0)
			(hide yes)
			(effects (font (size 1.27 1.27)))
		)
	)
)
"""


class TestSchematicParser(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.sch_path = os.path.join(self.test_dir, "test.kicad_sch")
        with open(self.sch_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_SCHEMATIC)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_parse_symbols(self):
        sch = SchematicFile(self.sch_path)
        self.assertTrue(sch.load())
        self.assertEqual(len(sch.symbols), 3)

        # Verify R1
        r1 = next((s for s in sch.symbols if s.reference == "R1"), None)
        self.assertIsNotNone(r1)
        self.assertEqual(r1.value, "10k")
        self.assertEqual(r1.footprint, "Resistor_SMD:R_0603_1608Metric")
        self.assertFalse(r1.is_power)
        self.assertEqual(r1.prefix, "R")

        # Verify #PWR01
        pwr = next((s for s in sch.symbols if s.reference == "#PWR01"), None)
        self.assertIsNotNone(pwr)
        self.assertTrue(pwr.is_power)

    def test_update_footprints(self):
        sch = SchematicFile(self.sch_path)
        self.assertTrue(sch.load())

        new_fp = "Resistor_SMD:R_0805_2012Metric"
        ok, count, err = sch.update_footprints({"R1": new_fp, "R2": new_fp}, make_backup=True)

        self.assertTrue(ok)
        self.assertEqual(count, 2)
        self.assertTrue(os.path.isfile(self.sch_path + ".bak"))

        # Re-parse to verify persistence
        sch2 = SchematicFile(self.sch_path)
        self.assertTrue(sch2.load())

        r1 = next((s for s in sch2.symbols if s.reference == "R1"), None)
        r2 = next((s for s in sch2.symbols if s.reference == "R2"), None)
        self.assertEqual(r1.footprint, new_fp)
        self.assertEqual(r2.footprint, new_fp)

        # Values and other properties should remain untouched
        self.assertEqual(r1.value, "10k")
        self.assertEqual(r2.value, "10k")

    def test_project_integration(self):
        proj = SchematicProject(self.sch_path)
        self.assertTrue(proj.load())

        symbols = proj.get_all_symbols(include_power=False)
        self.assertEqual(len(symbols), 2)  # R1 and R2

        updates = {
            (self.sch_path, "R1"): "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
        }
        ok, count, errors = proj.apply_footprint_updates(updates, make_backup=False)
        self.assertTrue(ok)
        self.assertEqual(count, 1)

        proj2 = SchematicProject(self.sch_path)
        proj2.load()
        r1 = next((s for s in proj2.get_all_symbols() if s.reference == "R1"), None)
        self.assertEqual(
            r1.footprint,
            "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
        )


class TestFootprintLibrary(unittest.TestCase):

    def test_library_indexing_and_search(self):
        mgr = FootprintLibraryManager()
        mgr.discover_and_index()
        self.assertGreater(len(mgr.footprints), 0)

        results = mgr.search("0805", limit=10)
        self.assertGreater(len(results), 0)
        self.assertTrue(any("0805" in r.full_id for r in results))


if __name__ == "__main__":
    unittest.main()
