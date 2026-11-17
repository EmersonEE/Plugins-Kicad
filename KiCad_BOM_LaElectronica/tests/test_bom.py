"""Unit tests for BOM extraction and query generation."""

import os
import tempfile
import unittest

from core.bom_extractor import BOMExtractor, BOMItem, ProductMatch
from core.exporter import BOMExporter


SAMPLE_SCHEMATIC = """(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "bfe657c0-e4c3-4a68-802c-828858edf143")
	(paper "A3")
	(symbol
		(lib_id "Device:R")
		(at 100 100 0)
		(unit 1)
		(in_bom yes)
		(on_board yes)
		(uuid "11111111-1111-1111-1111-111111111111")
		(property "Reference" "R1" (at 100 98 0))
		(property "Value" "10k" (at 100 102 0))
		(property "Footprint" "Resistor_SMD:R_0805_2012Metric" (at 100 100 0))
	)
	(symbol
		(lib_id "Device:R")
		(at 120 100 0)
		(unit 1)
		(in_bom yes)
		(on_board yes)
		(uuid "22222222-2222-2222-2222-222222222222")
		(property "Reference" "R2" (at 120 98 0))
		(property "Value" "10k" (at 120 102 0))
		(property "Footprint" "Resistor_SMD:R_0805_2012Metric" (at 120 100 0))
	)
	(symbol
		(lib_id "RF_Module:ESP32-WROOM-32")
		(at 150 100 0)
		(unit 1)
		(in_bom yes)
		(on_board yes)
		(uuid "33333333-3333-3333-3333-333333333333")
		(property "Reference" "U1" (at 150 98 0))
		(property "Value" "ESP32" (at 150 102 0))
		(property "Footprint" "RF_Module:ESP32-WROOM-32" (at 150 100 0))
	)
)
"""


class TestBOMExtractor(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".kicad_sch", delete=False, mode="w", encoding="utf-8")
        self.tmp.write(SAMPLE_SCHEMATIC)
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.remove(self.tmp.name)

    def test_bom_grouping(self):
        items = BOMExtractor.extract_from_schematic(self.tmp.name)
        self.assertEqual(len(items), 2)  # 1 group for R1,R2 and 1 group for U1

        r_group = next(i for i in items if i.prefix == "R")
        self.assertEqual(r_group.quantity, 2)
        self.assertEqual(r_group.references_str, "R1, R2")
        self.assertEqual(r_group.value, "10k")

        u_group = next(i for i in items if i.prefix == "U")
        self.assertEqual(u_group.quantity, 1)
        self.assertEqual(u_group.references_str, "U1")

    def test_query_generation(self):
        r_item = BOMItem(value="10k", footprint="Resistor_SMD:R_0805", lib_id="Device:R", references=["R1"])
        queries = r_item.generate_search_queries()
        self.assertTrue(any("Resistencia" in q for q in queries))

        c_item = BOMItem(value="100nF", footprint="Capacitor_SMD:C_0805", lib_id="Device:C", references=["C1"])
        c_queries = c_item.generate_search_queries()
        self.assertTrue(any("Capacitor" in q for q in c_queries))

    def test_exporter(self):
        items = [
            BOMItem(
                value="10k",
                footprint="Resistor_SMD:R_0805",
                lib_id="Device:R",
                references=["R1", "R2"],
                matched_product=ProductMatch(
                    title="Resistencia 10K Ohm a 1/4 W",
                    price=0.75,
                    price_str="Q0.75",
                    available=True,
                    url="/products/resistencia-10k",
                ),
            )
        ]

        csv_path = self.tmp.name + ".csv"
        self.assertTrue(BOMExporter.export_csv(csv_path, items))
        self.assertTrue(os.path.isfile(csv_path))
        os.remove(csv_path)

        html_path = self.tmp.name + ".html"
        self.assertTrue(BOMExporter.export_html(html_path, "Test Project", items))
        self.assertTrue(os.path.isfile(html_path))
        os.remove(html_path)


if __name__ == "__main__":
    unittest.main()
