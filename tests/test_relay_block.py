"""Prueba integral de extremo a extremo con el bloque de driver de relé (N=4) y validación ERC."""

import os
import tempfile
import unittest

from core.block_detector import BlockDetector
from core.block_duplicator import BlockDuplicator, DuplicationConfig
from core.project_backup import SafetyManager
from core.reference_annotator import ReferenceAnnotationMode
from core.sexpr import SExprParser, SExprSerializer


RELAY_DRIVER_FULL_SCHEMATIC = """(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "7f8a9b0c-1234-4567-89ab-cdef01234567")
	(paper "A3")
	(lib_symbols
		(symbol "Device:R"
			(property "Reference" "R" (at 0 0 0) (effects (font (size 1.27 1.27))))
			(property "Value" "R" (at 0 0 0) (effects (font (size 1.27 1.27))))
		)
		(symbol "Device:D"
			(property "Reference" "D" (at 0 0 0) (effects (font (size 1.27 1.27))))
			(property "Value" "D" (at 0 0 0) (effects (font (size 1.27 1.27))))
		)
		(symbol "Isolator:PC817"
			(property "Reference" "U" (at 0 0 0) (effects (font (size 1.27 1.27))))
			(property "Value" "PC817" (at 0 0 0) (effects (font (size 1.27 1.27))))
		)
		(symbol "Transistor_BJT:2N3904"
			(property "Reference" "Q" (at 0 0 0) (effects (font (size 1.27 1.27))))
			(property "Value" "2N3904" (at 0 0 0) (effects (font (size 1.27 1.27))))
		)
		(symbol "Relay:Relay_SPDT"
			(property "Reference" "K" (at 0 0 0) (effects (font (size 1.27 1.27))))
			(property "Value" "Relay_SPDT" (at 0 0 0) (effects (font (size 1.27 1.27))))
		)
		(symbol "Connector:Conn_01x03_Pin"
			(property "Reference" "J" (at 0 0 0) (effects (font (size 1.27 1.27))))
			(property "Value" "Conn_01x03_Pin" (at 0 0 0) (effects (font (size 1.27 1.27))))
		)
	)
	(hierarchical_label "OUT_1" (shape output) (at 50.8 50.8 0)
		(effects (font (size 1.27 1.27)) (justify right))
		(uuid "10000000-0000-0000-0000-000000000001")
	)
	(global_label "+5V" (shape input) (at 76.2 38.1 0)
		(effects (font (size 1.27 1.27)))
		(uuid "10000000-0000-0000-0000-000000000002")
	)
	(global_label "GND" (shape input) (at 76.2 63.5 0)
		(effects (font (size 1.27 1.27)))
		(uuid "10000000-0000-0000-0000-000000000003")
	)
	(global_label "NC" (shape bidirectional) (at 152.4 45.72 0)
		(effects (font (size 1.27 1.27)))
		(uuid "10000000-0000-0000-0000-000000000004")
	)
	(global_label "COM" (shape bidirectional) (at 152.4 50.8 0)
		(effects (font (size 1.27 1.27)))
		(uuid "10000000-0000-0000-0000-000000000005")
	)
	(global_label "NA" (shape bidirectional) (at 152.4 55.88 0)
		(effects (font (size 1.27 1.27)))
		(uuid "10000000-0000-0000-0000-000000000006")
	)
	(symbol (lib_id "Device:R") (at 63.5 50.8 0) (unit 1)
		(uuid "20000000-0000-0000-0000-000000000001")
		(property "Reference" "R5" (at 63.5 48.26 0) (effects (font (size 1.27 1.27))))
		(property "Value" "1k" (at 63.5 53.34 0) (effects (font (size 1.27 1.27))))
	)
	(symbol (lib_id "Isolator:PC817") (at 76.2 50.8 0) (unit 1)
		(uuid "20000000-0000-0000-0000-000000000002")
		(property "Reference" "U4" (at 76.2 45.72 0) (effects (font (size 1.27 1.27))))
		(property "Value" "PC817" (at 76.2 55.88 0) (effects (font (size 1.27 1.27))))
	)
	(symbol (lib_id "Device:R") (at 88.9 50.8 0) (unit 1)
		(uuid "20000000-0000-0000-0000-000000000003")
		(property "Reference" "R6" (at 88.9 48.26 0) (effects (font (size 1.27 1.27))))
		(property "Value" "10k" (at 88.9 53.34 0) (effects (font (size 1.27 1.27))))
	)
	(symbol (lib_id "Transistor_BJT:2N3904") (at 101.6 50.8 0) (unit 1)
		(uuid "20000000-0000-0000-0000-000000000004")
		(property "Reference" "Q1" (at 101.6 45.72 0) (effects (font (size 1.27 1.27))))
		(property "Value" "2N3904" (at 101.6 55.88 0) (effects (font (size 1.27 1.27))))
	)
	(symbol (lib_id "Relay:Relay_SPDT") (at 114.3 50.8 0) (unit 1)
		(uuid "20000000-0000-0000-0000-000000000005")
		(property "Reference" "K1" (at 114.3 45.72 0) (effects (font (size 1.27 1.27))))
		(property "Value" "SRD-05VDC" (at 114.3 55.88 0) (effects (font (size 1.27 1.27))))
	)
	(symbol (lib_id "Device:D") (at 114.3 38.1 0) (unit 1)
		(uuid "20000000-0000-0000-0000-000000000006")
		(property "Reference" "D6" (at 114.3 35.56 0) (effects (font (size 1.27 1.27))))
		(property "Value" "1N4007" (at 114.3 40.64 0) (effects (font (size 1.27 1.27))))
	)
	(symbol (lib_id "Connector:Conn_01x03_Pin") (at 139.7 50.8 0) (unit 1)
		(uuid "20000000-0000-0000-0000-000000000007")
		(property "Reference" "J2" (at 139.7 45.72 0) (effects (font (size 1.27 1.27))))
		(property "Value" "Screw_Terminal" (at 139.7 55.88 0) (effects (font (size 1.27 1.27))))
	)
	(wire (pts (xy 50.8 50.8) (xy 63.5 50.8))
		(stroke (width 0) (type default))
		(uuid "30000000-0000-0000-0000-000000000001")
	)
)"""


class TestRelayBlockIntegration(unittest.TestCase):

    def test_relay_driver_end_to_end_n4_and_erc(self):
        root = SExprParser.parse(RELAY_DRIVER_FULL_SCHEMATIC)
        self.assertIsNotNone(root)

        # Detectar el bloque por las referencias del caso de uso
        refs = ["R5", "U4", "R6", "Q1", "K1", "D6", "J2"]
        block = BlockDetector.from_schematic_by_references(root, refs, margin=25.4)

        self.assertEqual(len(block.symbols), 7)

        cfg = DuplicationConfig(
            num_copies=4,
            direction="vertical",
            pitch_y_mm=50.8,
            annotation_mode=ReferenceAnnotationMode.RESET_TO_QUESTION_MARK
        )
        duplicator = BlockDuplicator(cfg)
        report = duplicator.duplicate_block(block)

        # Agregar los nuevos elementos clonados a la raíz del esquemático
        for item in report.new_items:
            root.add_child(item)

        # Serializar el esquemático completo modificado
        serialized = SExprSerializer.serialize(root)

        # Guardar en archivo temporal y validar con kicad-cli sch erc
        with tempfile.NamedTemporaryFile(suffix=".kicad_sch", mode="w", delete=False) as f:
            f.write(serialized)
            tmp_sch_path = f.name

        try:
            success, output, errors = SafetyManager.validate_with_kicad_erc(tmp_sch_path)
            self.assertTrue(success, f"KiCad ERC falló en cargar el esquema: {output}")

            # Re-parsear el archivo guardado y comprobar la cantidad total de símbolos
            reparsed = SExprParser.parse(serialized)
            total_symbols = [it for it in reparsed.items if it.tag == "symbol"]
            self.assertEqual(len(total_symbols), 7 * 4)  # 28 símbolos en total

            # Comprobar etiquetas
            hier_labels = [str(it.get_atom(0)) for it in reparsed.items if it.tag == "hierarchical_label"]
            self.assertIn("OUT_1", hier_labels)
            self.assertIn("OUT_2", hier_labels)
            self.assertIn("OUT_3", hier_labels)
            self.assertIn("OUT_4", hier_labels)

            global_labels = [str(it.get_atom(0)) for it in reparsed.items if it.tag == "global_label"]
            self.assertIn("NC", global_labels)
            self.assertIn("NC_2", global_labels)
            self.assertIn("NC_3", global_labels)
            self.assertIn("NC_4", global_labels)

            self.assertIn("COM", global_labels)
            self.assertIn("COM_2", global_labels)
            self.assertIn("COM_3", global_labels)
            self.assertIn("COM_4", global_labels)

            self.assertIn("NA", global_labels)
            self.assertIn("NA_2", global_labels)
            self.assertIn("NA_3", global_labels)
            self.assertIn("NA_4", global_labels)

            # Verificar que +5V y GND siguen apareciendo en todas las copias sin sufijo
            pwr_5v_count = sum(1 for g in global_labels if g == "+5V")
            pwr_gnd_count = sum(1 for g in global_labels if g == "GND")
            self.assertEqual(pwr_5v_count, 4)
            self.assertEqual(pwr_gnd_count, 4)

        finally:
            if os.path.exists(tmp_sch_path):
                os.remove(tmp_sch_path)


if __name__ == "__main__":
    unittest.main()
