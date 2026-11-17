"""Pruebas unitarias para core/block_duplicator.py."""

import unittest
from core.block_detector import BlockDetector
from core.block_duplicator import BlockDuplicator, DuplicationConfig, snap_to_grid
from core.reference_annotator import ReferenceAnnotationMode
from core.sexpr import SExprParser


# Bloque de ejemplo: Driver de relé
# OUT_1 -> R5 -> U4 (PC817) -> R6 -> Q1 (2N3904) -> K1 (con D6) -> J2
# +5V, GND, y globales NC, COM, NA
SAMPLE_RELAY_BLOCK = """(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "00000000-0000-0000-0000-000000000000")
	(paper "A4")
	(hierarchical_label "OUT_1" (shape output) (at 50.8 50.8 0)
		(effects (font (size 1.27 1.27)) (justify right))
		(uuid "11111111-0000-0000-0000-000000000001")
	)
	(global_label "+5V" (shape input) (at 76.2 38.1 0)
		(effects (font (size 1.27 1.27)))
		(uuid "11111111-0000-0000-0000-000000000002")
	)
	(global_label "GND" (shape input) (at 76.2 63.5 0)
		(effects (font (size 1.27 1.27)))
		(uuid "11111111-0000-0000-0000-000000000003")
	)
	(global_label "NC" (shape bidirectional) (at 127.0 45.72 0)
		(effects (font (size 1.27 1.27)))
		(uuid "11111111-0000-0000-0000-000000000004")
	)
	(global_label "COM" (shape bidirectional) (at 127.0 50.8 0)
		(effects (font (size 1.27 1.27)))
		(uuid "11111111-0000-0000-0000-000000000005")
	)
	(global_label "NA" (shape bidirectional) (at 127.0 55.88 0)
		(effects (font (size 1.27 1.27)))
		(uuid "11111111-0000-0000-0000-000000000006")
	)
	(symbol (lib_id "Device:R") (at 60.96 50.8 0) (unit 1)
		(uuid "22222222-0000-0000-0000-000000000001")
		(property "Reference" "R5" (at 60.96 48.26 0) (effects (font (size 1.27 1.27))))
		(property "Value" "1k" (at 60.96 53.34 0) (effects (font (size 1.27 1.27))))
		(pin "1" (uuid "33333333-0000-0000-0000-000000000001"))
		(pin "2" (uuid "33333333-0000-0000-0000-000000000002"))
	)
	(symbol (lib_id "Isolator:PC817") (at 76.2 50.8 0) (unit 1)
		(uuid "22222222-0000-0000-0000-000000000002")
		(property "Reference" "U4" (at 76.2 45.72 0) (effects (font (size 1.27 1.27))))
		(property "Value" "PC817" (at 76.2 55.88 0) (effects (font (size 1.27 1.27))))
		(pin "1" (uuid "33333333-0000-0000-0000-000000000003"))
		(pin "2" (uuid "33333333-0000-0000-0000-000000000004"))
	)
	(symbol (lib_id "Device:R") (at 88.9 50.8 0) (unit 1)
		(uuid "22222222-0000-0000-0000-000000000003")
		(property "Reference" "R6" (at 88.9 48.26 0) (effects (font (size 1.27 1.27))))
		(property "Value" "10k" (at 88.9 53.34 0) (effects (font (size 1.27 1.27))))
	)
	(symbol (lib_id "Transistor_BJT:2N3904") (at 101.6 50.8 0) (unit 1)
		(uuid "22222222-0000-0000-0000-000000000004")
		(property "Reference" "Q1" (at 101.6 45.72 0) (effects (font (size 1.27 1.27))))
		(property "Value" "2N3904" (at 101.6 55.88 0) (effects (font (size 1.27 1.27))))
	)
	(symbol (lib_id "Relay:Relay_SPDT") (at 114.3 50.8 0) (unit 1)
		(uuid "22222222-0000-0000-0000-000000000005")
		(property "Reference" "K1" (at 114.3 45.72 0) (effects (font (size 1.27 1.27))))
		(property "Value" "SRD-05VDC" (at 114.3 55.88 0) (effects (font (size 1.27 1.27))))
	)
	(symbol (lib_id "Device:D") (at 114.3 40.64 0) (unit 1)
		(uuid "22222222-0000-0000-0000-000000000006")
		(property "Reference" "D6" (at 114.3 35.56 0) (effects (font (size 1.27 1.27))))
		(property "Value" "1N4007" (at 114.3 45.72 0) (effects (font (size 1.27 1.27))))
	)
	(symbol (lib_id "Connector:Conn_01x03_Pin") (at 139.7 50.8 0) (unit 1)
		(uuid "22222222-0000-0000-0000-000000000007")
		(property "Reference" "J2" (at 139.7 45.72 0) (effects (font (size 1.27 1.27))))
		(property "Value" "Screw_Terminal" (at 139.7 55.88 0) (effects (font (size 1.27 1.27))))
	)
	(wire (pts (xy 50.8 50.8) (xy 58.42 50.8))
		(stroke (width 0) (type default))
		(uuid "44444444-0000-0000-0000-000000000001")
	)
)"""


class TestBlockDuplicator(unittest.TestCase):

    def setUp(self):
        self.block = BlockDetector.from_clipboard_text(SAMPLE_RELAY_BLOCK)
        self.assertIsNotNone(self.block)

    def test_grid_snapping(self):
        self.assertEqual(snap_to_grid(50.8), 50.8)
        self.assertEqual(snap_to_grid(1.27), 1.27)
        self.assertAlmostEqual(snap_to_grid(1.3), 1.27, places=3)
        self.assertAlmostEqual(snap_to_grid(2.5), 2.54, places=3)

    def test_relay_block_duplication_n4_question_mark(self):
        cfg = DuplicationConfig(
            num_copies=4,
            direction="vertical",
            pitch_y_mm=50.8,
            annotation_mode=ReferenceAnnotationMode.RESET_TO_QUESTION_MARK
        )
        duplicator = BlockDuplicator(cfg)
        report = duplicator.duplicate_block(self.block)

        # Se crearon 3 copias adicionales (total N=4 bloques)
        self.assertEqual(report.total_copies_created, 3)

        # 7 símbolos x 3 copias = 21 símbolos nuevos
        self.assertEqual(report.symbols_created, 21)

        # Verificar etiquetas renombradas en el reporte
        # OUT_1 -> OUT_2, OUT_3, OUT_4
        hier_renames = [new for orig, new, idx in report.labels_renamed if orig == "OUT_1"]
        self.assertEqual(hier_renames, ["OUT_2", "OUT_3", "OUT_4"])

        # NC, COM, NA -> sufijo _2, _3, _4
        nc_renames = [new for orig, new, idx in report.labels_renamed if orig == "NC"]
        self.assertEqual(nc_renames, ["NC_2", "NC_3", "NC_4"])

        com_renames = [new for orig, new, idx in report.labels_renamed if orig == "COM"]
        self.assertEqual(com_renames, ["COM_2", "COM_3", "COM_4"])

        na_renames = [new for orig, new, idx in report.labels_renamed if orig == "NA"]
        self.assertEqual(na_renames, ["NA_2", "NA_3", "NA_4"])

        # +5V y GND NO deben cambiar
        pwr_renames = [new for orig, new, idx in report.labels_renamed if orig == "+5V"]
        self.assertEqual(pwr_renames, ["+5V", "+5V", "+5V"])

        gnd_renames = [new for orig, new, idx in report.labels_renamed if orig == "GND"]
        self.assertEqual(gnd_renames, ["GND", "GND", "GND"])

        # En modo question_mark, las referencias de las copias deben terminar en '?'
        for orig_ref, new_ref, idx in report.references_assigned:
            self.assertTrue(new_ref.endswith("?"), f"Expected question mark ref, got {new_ref}")

    def test_clipboard_payload_is_bare_selection(self):
        """KiCad pega desde un bloque SIN envoltorio (kicad_sch ...).

        Si el payload lleva el envoltorio, LoadContent lanza IO_ERROR y KiCad pega
        el contenido como un simple objeto de texto. Este test lo previene.
        """
        from core.block_duplicator import build_kicad_clipboard_payload

        cfg = DuplicationConfig(
            num_copies=4,
            direction="vertical",
            pitch_y_mm=50.8,
            annotation_mode=ReferenceAnnotationMode.RESET_TO_QUESTION_MARK
        )
        duplicator = BlockDuplicator(cfg)
        report = duplicator.duplicate_block(self.block)

        payload = build_kicad_clipboard_payload(SAMPLE_RELAY_BLOCK, self.block, report.new_items)
        nodes = SExprParser.parse_many(payload)

        self.assertTrue(nodes)
        self.assertTrue(all(n.tag != "kicad_sch" for n in nodes))

        tags = [n.tag for n in nodes]
        # 7 símbolos originales + 7 * 3 copias
        self.assertEqual(tags.count("symbol"), 28)

        # Si hay caché de símbolos, debe ir primero (como hace KiCad).
        if "lib_symbols" in tags:
            self.assertEqual(tags[0], "lib_symbols")

    def test_copied_symbol_instance_reference_is_quoted(self):
        """Las referencias dentro de (instances ...) deben ir entrecomilladas.

        KiCad no puede abrir el esquemático si se escriben como átomos sueltos
        (p. ej. ``R?`` sin comillas).
        """
        from core.block_duplicator import build_kicad_clipboard_payload

        schematic = """(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "00000000-0000-0000-0000-000000000000")
	(paper "A4")
	(lib_symbols
		(symbol "Device:R"
			(property "Reference" "R" (at 0 0 0) (effects (font (size 1.27 1.27))))
			(property "Value" "R" (at 0 0 0) (effects (font (size 1.27 1.27))))
		)
	)
	(symbol (lib_id "Device:R") (at 50.8 50.8 0) (unit 1)
		(uuid "20000000-0000-0000-0000-000000000001")
		(property "Reference" "R5" (at 50.8 48.26 0) (effects (font (size 1.27 1.27))))
		(property "Value" "1k" (at 50.8 53.34 0) (effects (font (size 1.27 1.27))))
		(instances
			(project "demo"
				(path "/00000000-0000-0000-0000-000000000000"
					(reference "R5") (unit 1)
				)
			)
		)
	)
)"""
        block = BlockDetector.from_clipboard_text(schematic)
        self.assertIsNotNone(block)

        duplicator = BlockDuplicator(DuplicationConfig(num_copies=2))
        report = duplicator.duplicate_block(block)
        payload = build_kicad_clipboard_payload(schematic, block, report.new_items)

        self.assertIn('"R?"', payload)
        # No debe quedar ninguna referencia sin comillas dentro de (reference ...).
        self.assertNotRegex(payload, r'\(reference\s+[A-Za-z#]+\?')

    def test_relay_block_duplication_sequential(self):
        cfg = DuplicationConfig(
            num_copies=4,
            direction="vertical",
            pitch_y_mm=50.8,
            annotation_mode=ReferenceAnnotationMode.AUTO_SEQUENTIAL
        )
        duplicator = BlockDuplicator(cfg)
        report = duplicator.duplicate_block(self.block)

        # Verificar que no hay signos de interrogación y que no colisionan con R5, R6
        assigned_refs = [new_ref for orig, new_ref, idx in report.references_assigned]
        for ref in assigned_refs:
            self.assertFalse(ref.endswith("?"))

        # Las nuevas resistencias deben ser superiores a R6 (ej. R7, R8...)
        new_resistors = [r for r in assigned_refs if r.startswith("R")]
        self.assertNotIn("R5", new_resistors)
        self.assertNotIn("R6", new_resistors)


if __name__ == "__main__":
    unittest.main()
