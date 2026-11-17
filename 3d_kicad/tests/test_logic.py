"""Pruebas de la lógica usando los bindings reales de pcbnew 10."""

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

import pcbnew
import wx

from propagate_3d_models.action import _parent_window
from propagate_3d_models.logic import (
    clone_3d_model,
    find_candidates,
    footprint_id,
    has_3d_models,
    natural_reference_key,
    propagate_models,
    same_footprint,
)


class WindowParentTests(unittest.TestCase):
    def test_parent_lookup_does_not_require_get_top_window(self) -> None:
        # Fuera del editor puede devolver None; lo importante es que no dependa
        # de AppConsole.GetTopWindow(), que no existe en algunos paquetes KiCad.
        parent = _parent_window()
        self.assertTrue(parent is None or isinstance(parent, wx.Window))


def make_footprint(
    board: pcbnew.BOARD, reference: str, fpid: str, model_path: str | None = None
) -> pcbnew.FOOTPRINT:
    footprint = pcbnew.FOOTPRINT(board)
    footprint.SetReference(reference)
    footprint.SetFPIDAsString(fpid)
    if model_path is not None:
        model = pcbnew.FP_3DMODEL()
        model.m_Filename = model_path
        footprint.Add3DModel(model)
    board.Add(footprint)
    return footprint


class FootprintDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.board = pcbnew.BOARD()

    def test_full_fpid_is_required(self) -> None:
        first = make_footprint(self.board, "R1", "Lib_A:R_0805")
        same = make_footprint(self.board, "R2", "Lib_A:R_0805")
        other_library = make_footprint(self.board, "R3", "Lib_B:R_0805")

        self.assertEqual(footprint_id(first), "Lib_A:R_0805")
        self.assertTrue(same_footprint(first, same))
        self.assertFalse(same_footprint(first, other_library))

    def test_candidates_are_matching_empty_instances_only(self) -> None:
        source = make_footprint(self.board, "R1", "Device:R", "${MODEL_DIR}/r.step")
        r10 = make_footprint(self.board, "R10", "Device:R")
        r2 = make_footprint(self.board, "R2", "Device:R")
        occupied = make_footprint(self.board, "R3", "Device:R", "custom.step")
        different = make_footprint(self.board, "C1", "Device:C")

        candidates = find_candidates(self.board.GetFootprints(), source)

        self.assertEqual([item.GetReference() for item in candidates], ["R2", "R10"])
        self.assertNotIn(occupied, candidates)
        self.assertNotIn(different, candidates)

    def test_empty_fpid_never_matches(self) -> None:
        first = make_footprint(self.board, "U1", "")
        second = make_footprint(self.board, "U2", "")
        self.assertFalse(same_footprint(first, second))

    def test_reference_sort_is_natural(self) -> None:
        ordered = sorted(["R10", "R2", "R1"], key=natural_reference_key)
        self.assertEqual(ordered, ["R1", "R2", "R10"])


class ModelCopyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.board = pcbnew.BOARD()

    def test_clone_preserves_every_exposed_property(self) -> None:
        model = pcbnew.FP_3DMODEL()
        model.m_Filename = "${KICAD10_3DMODEL_DIR}/Package.step"
        model.m_Offset = pcbnew.VECTOR3D(1.1, 2.2, 3.3)
        model.m_Rotation = pcbnew.VECTOR3D(10.0, 20.0, 30.0)
        model.m_Scale = pcbnew.VECTOR3D(0.5, 0.75, 1.25)
        model.m_Opacity = 0.42
        model.m_Show = False

        clone = clone_3d_model(model)

        self.assertEqual(clone.m_Filename, model.m_Filename)
        self.assertEqual(tuple(clone.m_Offset), tuple(model.m_Offset))
        self.assertEqual(tuple(clone.m_Rotation), tuple(model.m_Rotation))
        self.assertEqual(tuple(clone.m_Scale), tuple(model.m_Scale))
        self.assertAlmostEqual(clone.m_Opacity, model.m_Opacity)
        self.assertEqual(clone.m_Show, model.m_Show)

    def test_propagation_copies_all_models_and_skips_occupied_target(self) -> None:
        source = make_footprint(self.board, "J1", "Conn:USB")
        first_model = pcbnew.FP_3DMODEL()
        first_model.m_Filename = "${MODELS}/body.step"
        first_model.m_Offset = pcbnew.VECTOR3D(1.0, 2.0, 3.0)
        source.Add3DModel(first_model)
        second_model = pcbnew.FP_3DMODEL()
        second_model.m_Filename = "${MODELS}/shield.wrl"
        second_model.m_Rotation = pcbnew.VECTOR3D(0.0, 0.0, 90.0)
        source.Add3DModel(second_model)

        empty = make_footprint(self.board, "J2", "Conn:USB")
        occupied = make_footprint(self.board, "J3", "Conn:USB", "do-not-touch.step")
        wrong_fpid = make_footprint(self.board, "J4", "Conn:Other")

        changed = propagate_models(source, [empty, occupied, wrong_fpid])

        self.assertEqual(changed, [empty])
        self.assertTrue(has_3d_models(empty))
        self.assertEqual([model.m_Filename for model in empty.Models()], [
            "${MODELS}/body.step",
            "${MODELS}/shield.wrl",
        ])
        self.assertEqual(tuple(empty.Models()[0].m_Offset), (1.0, 2.0, 3.0))
        self.assertEqual(tuple(empty.Models()[1].m_Rotation), (0.0, 0.0, 90.0))
        self.assertEqual([model.m_Filename for model in occupied.Models()], ["do-not-touch.step"])
        self.assertFalse(has_3d_models(wrong_fpid))

    def test_saved_board_preserves_copied_path_and_transform(self) -> None:
        source = make_footprint(self.board, "U1", "Package:BGA")
        model = pcbnew.FP_3DMODEL()
        model.m_Filename = "${KICAD10_3DMODEL_DIR}/Package_BGA.3dshapes/BGA.step"
        model.m_Offset = pcbnew.VECTOR3D(0.1, 0.2, 0.3)
        model.m_Rotation = pcbnew.VECTOR3D(0.0, 0.0, 45.0)
        model.m_Scale = pcbnew.VECTOR3D(1.0, 1.0, 1.1)
        source.Add3DModel(model)
        target = make_footprint(self.board, "U2", "Package:BGA")
        propagate_models(source, [target])

        with tempfile.TemporaryDirectory() as temporary_directory:
            board_path = Path(temporary_directory) / "roundtrip.kicad_pcb"
            self.assertTrue(pcbnew.SaveBoard(str(board_path), self.board))
            loaded = pcbnew.LoadBoard(str(board_path))

        loaded_target = next(
            item for item in loaded.GetFootprints() if item.GetReference() == "U2"
        )
        loaded_model = loaded_target.Models()[0]
        self.assertEqual(loaded_model.m_Filename, model.m_Filename)
        self.assertEqual(tuple(loaded_model.m_Offset), (0.1, 0.2, 0.3))
        self.assertEqual(tuple(loaded_model.m_Rotation), (0.0, 0.0, 45.0))
        self.assertEqual(tuple(loaded_model.m_Scale), (1.0, 1.0, 1.1))


if __name__ == "__main__":
    unittest.main()
