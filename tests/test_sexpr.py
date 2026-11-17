"""Pruebas unitarias para core/sexpr.py."""

import unittest
from core.sexpr import SExprParser, SExprSerializer, SNode, SAtom


SAMPLE_TEXT = """(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "bfe657c0-e4c3-4a68-802c-828858edf143")
	(paper "A4")
	(symbol
		(lib_id "Device:R")
		(at 100 100 0)
		(unit 1)
		(in_bom yes)
		(uuid "11111111-1111-1111-1111-111111111111")
		(property "Reference" "R1" (at 100 98 0) (effects (font (size 1.27 1.27))))
		(property "Value" "10k" (at 100 102 0) (effects (font (size 1.27 1.27))))
		(pin "1" (uuid "22222222-2222-2222-2222-222222222222"))
	)
)"""


class TestSExpr(unittest.TestCase):

    def test_parse_and_serialize_roundtrip(self):
        root = SExprParser.parse(SAMPLE_TEXT)
        self.assertIsNotNone(root)
        self.assertEqual(root.tag, "kicad_sch")
        self.assertEqual(root.get_uuid(), "bfe657c0-e4c3-4a68-802c-828858edf143")

        sym = root.get_child("symbol")
        self.assertIsNotNone(sym)
        self.assertEqual(sym.get_prop("Reference"), "R1")
        self.assertEqual(sym.get_prop("Value"), "10k")

        pos = sym.get_position()
        self.assertIsNotNone(pos)
        self.assertEqual(pos[0], 100.0)
        self.assertEqual(pos[1], 100.0)

    def test_property_update(self):
        root = SExprParser.parse(SAMPLE_TEXT)
        sym = root.get_child("symbol")
        self.assertTrue(sym.set_prop("Reference", "R5"))
        self.assertEqual(sym.get_prop("Reference"), "R5")

    def test_shift_position(self):
        root = SExprParser.parse(SAMPLE_TEXT)
        sym = root.get_child("symbol")
        sym.shift_position(25.4, 50.8)
        pos = sym.get_position()
        self.assertAlmostEqual(pos[0], 125.4, places=3)
        self.assertAlmostEqual(pos[1], 150.8, places=3)

        # Verificar que la propiedad Reference también se desplazó
        prop_ref = None
        for item in sym.items:
            if isinstance(item, SNode) and item.tag == "property" and item.get_atom(0) == "Reference":
                prop_ref = item
                break
        self.assertIsNotNone(prop_ref)
        prop_pos = prop_ref.get_position()
        self.assertAlmostEqual(prop_pos[0], 125.4, places=3)
        self.assertAlmostEqual(prop_pos[1], 148.8, places=3)

    def test_shift_wire_points_does_not_insert_at(self):
        """Desplazar un cable debe actualizar sus (xy X Y), nunca añadir un (at ...)."""
        wire = SExprParser.parse(
            '(wire (pts (xy 50.8 50.8) (xy 63.5 50.8)) '
            '(stroke (width 0) (type default)) (uuid "c0000000-0000-0000-0000-000000000001"))'
        )
        wire.shift_position(0.0, 50.8)

        pts = wire.get_child("pts")
        xy_nodes = pts.get_children("xy")
        self.assertEqual(len(xy_nodes), 2)

        for pt in xy_nodes:
            # Exactamente dos átomos de coordenadas y ningún hijo (at ...).
            self.assertEqual(len(pt.items), 2)
            self.assertFalse(any(isinstance(i, SNode) for i in pt.items))

        self.assertEqual(str(xy_nodes[0].get_atom(0)), "50.8")
        self.assertEqual(str(xy_nodes[0].get_atom(1)), "101.6")
        self.assertEqual(str(xy_nodes[1].get_atom(1)), "101.6")

        # El texto serializado no debe contener (xy (at ...
        self.assertNotIn("(xy (at", SExprSerializer.serialize(wire))

    def test_clone_independence(self):
        root = SExprParser.parse(SAMPLE_TEXT)
        sym = root.get_child("symbol")
        sym_clone = sym.clone()

        sym_clone.set_prop("Reference", "R99")
        sym_clone.set_uuid("99999999-9999-9999-9999-999999999999")

        self.assertEqual(sym.get_prop("Reference"), "R1")
        self.assertEqual(sym_clone.get_prop("Reference"), "R99")
        self.assertEqual(sym.get_uuid(), "11111111-1111-1111-1111-111111111111")
        self.assertEqual(sym_clone.get_uuid(), "99999999-9999-9999-9999-999999999999")


if __name__ == "__main__":
    unittest.main()
