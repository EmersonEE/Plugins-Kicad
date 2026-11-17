"""Pruebas unitarias para core/hierarchical.py."""

import os
import tempfile
import unittest
from core.hierarchical import HierarchicalManager
from core.sexpr import SExprParser


PARENT_SCHEMATIC = """(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "00000000-0000-0000-0000-000000000000")
	(paper "A4")
	(sheet (at 50.8 50.8) (size 50.8 40.0)
		(fields_autoplaced yes)
		(uuid "6f3d1b70-c75c-449e-b9bb-2cfad335e263")
		(property "Sheetname" "RelayChannels" (at 50.8 49.53 0))
		(property "Sheetfile" "relay_driver.kicad_sch" (at 50.8 92.0 0))
		(pin "OUT_1" output (at 101.6 60.96 0)
			(effects (font (size 1.27 1.27)) (justify right))
			(uuid "561e1b21-4f88-4e3a-b8cb-4074211a2f1c")
		)
	)
)"""


class TestHierarchicalSync(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.parent_path = os.path.join(self.test_dir, "main.kicad_sch")
        self.child_path = os.path.join(self.test_dir, "relay_driver.kicad_sch")

        with open(self.parent_path, "w", encoding="utf-8") as f:
            f.write(PARENT_SCHEMATIC)
        with open(self.child_path, "w", encoding="utf-8") as f:
            f.write("(kicad_sch)")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sync_parent_sheet_pins(self):
        new_labels = [
            ("OUT_1", "OUT_2"),
            ("OUT_1", "OUT_3"),
            ("OUT_1", "OUT_4"),
        ]

        added = HierarchicalManager.sync_parent_sheet_pins(
            self.parent_path, self.child_path, new_labels
        )
        self.assertEqual(added, ["OUT_2", "OUT_3", "OUT_4"])

        # Verificar que el archivo padre contiene los nuevos pines
        with open(self.parent_path, "r", encoding="utf-8") as f:
            content = f.read()

        root = SExprParser.parse(content)
        sheet = root.get_child("sheet")
        pins = sheet.get_children("pin")
        pin_names = [str(p.get_atom(0)) for p in pins]

        self.assertIn("OUT_1", pin_names)
        self.assertIn("OUT_2", pin_names)
        self.assertIn("OUT_3", pin_names)
        self.assertIn("OUT_4", pin_names)


if __name__ == "__main__":
    unittest.main()
