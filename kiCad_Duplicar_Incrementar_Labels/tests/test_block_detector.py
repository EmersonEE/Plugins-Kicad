"""Pruebas para la detección de bloques (core/block_detector.py).

Cubren especialmente la selección por identidad de nodo, que evita el crecimiento
exponencial cuando hay muchas copias sin anotar compartiendo la misma referencia.
"""

import unittest

from core.block_detector import BlockDetector
from core.sexpr import SExprParser


# Dos resistencias con la MISMA referencia sin anotar ("R?") y muy separadas,
# más una etiqueta global pegada a la primera.
TWO_UNANNOTATED_SYMBOLS = """(kicad_sch
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
	(global_label "OUT" (shape output) (at 50.8 50.8 0)
		(effects (font (size 1.27 1.27)))
		(uuid "aaaaaaaa-0000-0000-0000-000000000001")
	)
	(symbol (lib_id "Device:R") (at 50.8 50.8 0) (unit 1)
		(uuid "bbbbbbbb-0000-0000-0000-000000000001")
		(property "Reference" "R?" (at 50.8 48.26 0) (effects (font (size 1.27 1.27))))
		(property "Value" "1k" (at 50.8 53.34 0) (effects (font (size 1.27 1.27))))
	)
	(symbol (lib_id "Device:R") (at 250.0 250.0 0) (unit 1)
		(uuid "bbbbbbbb-0000-0000-0000-000000000002")
		(property "Reference" "R?" (at 250.0 248.26 0) (effects (font (size 1.27 1.27))))
		(property "Value" "10k" (at 250.0 253.34 0) (effects (font (size 1.27 1.27))))
	)
)"""


class TestBlockDetectorByNodes(unittest.TestCase):

    def test_selecting_one_node_ignores_far_symbol_with_same_reference(self):
        root = SExprParser.parse(TWO_UNANNOTATED_SYMBOLS)
        symbols = [it for it in root.items if it.tag == "symbol"]
        self.assertEqual(len(symbols), 2)

        # El usuario solo marca la primera resistencia (la que tiene la etiqueta OUT)
        block = BlockDetector.from_schematic_by_symbol_nodes(root, [symbols[0]])

        values = sorted(s.get_prop("Value") for s in block.symbols)
        self.assertEqual(values, ["1k"])

        names = [name for _, _, name in block.labels]
        self.assertIn("OUT", names)

    def test_selecting_node_keeps_lib_symbols_cache(self):
        root = SExprParser.parse(TWO_UNANNOTATED_SYMBOLS)
        symbols = [it for it in root.items if it.tag == "symbol"]
        block = BlockDetector.from_schematic_by_symbol_nodes(root, [symbols[1]])
        self.assertEqual(len(block.lib_symbols), 1)
        self.assertEqual(block.lib_symbols[0].get_atom(0), "Device:R")


if __name__ == "__main__":
    unittest.main()
