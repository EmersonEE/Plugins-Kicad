"""Unit tests for 3D model propagation logic."""

import os
import tempfile
import unittest
import pcbnew

from core.model_propagator import (
    FootprintCandidate,
    apply_3d_models_to_footprint,
    audit_and_propagate_all_board,
    clear_3d_models_for_entire_family,
    clear_3d_models_from_candidates,
    clear_3d_models_from_footprint,
    clone_3d_model,
    export_3d_presets,
    filter_candidate_footprints,
    find_candidate_footprints,
    find_matching_3d_models,
    get_footprint_fpid,
    get_footprint_models,
    get_footprint_name,
    get_model_transform,
    import_3d_presets,
    update_footprint_model_transform,
)


class TestModelPropagator(unittest.TestCase):

    def setUp(self):
        self.board = pcbnew.BOARD()
        self.fp1 = pcbnew.FOOTPRINT(self.board)
        self.fp1.SetReference("R1")
        self.fp1.SetValue("10k")
        self.fp1.SetFPIDAsString("Resistor_SMD:R_0805_2012Metric")

        self.fp2 = pcbnew.FOOTPRINT(self.board)
        self.fp2.SetReference("R2")
        self.fp2.SetValue("10k")
        self.fp2.SetFPIDAsString("Resistor_SMD:R_0805_2012Metric")

        self.fp3 = pcbnew.FOOTPRINT(self.board)
        self.fp3.SetReference("R3")
        self.fp3.SetValue("22k")
        self.fp3.SetFPIDAsString("Custom_Lib:R_0805_2012Metric")

        self.board.Add(self.fp1)
        self.board.Add(self.fp2)
        self.board.Add(self.fp3)

        # Add a 3D model to fp1
        mod = pcbnew.FP_3DMODEL()
        mod.m_Filename = "${KICAD8_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0805_2012Metric.wrl"
        mod.m_Offset = pcbnew.VECTOR3D(0.5, 0.2, 0.0)
        mod.m_Scale = pcbnew.VECTOR3D(1.0, 1.0, 1.0)
        mod.m_Rotation = pcbnew.VECTOR3D(0.0, 0.0, 90.0)
        mod.m_Opacity = 0.9
        mod.m_Show = True
        self.fp1.Add3DModel(mod)

    def test_fpid_extraction(self):
        fpid = get_footprint_fpid(self.fp1)
        name = get_footprint_name(self.fp1)
        self.assertEqual(fpid, "Resistor_SMD:R_0805_2012Metric")
        self.assertEqual(name, "R_0805_2012Metric")

    def test_model_cloning(self):
        src_mod = get_footprint_models(self.fp1)[0]
        cloned = clone_3d_model(src_mod)

        self.assertEqual(cloned.m_Filename, src_mod.m_Filename)
        self.assertAlmostEqual(cloned.m_Offset.x, 0.5)
        self.assertAlmostEqual(cloned.m_Offset.y, 0.2)
        self.assertAlmostEqual(cloned.m_Rotation.z, 90.0)
        self.assertAlmostEqual(cloned.m_Opacity, 0.9)
        self.assertTrue(cloned.m_Show)

    def test_model_tuning_transform(self):
        src_mod = get_footprint_models(self.fp1)[0]
        t = get_model_transform(src_mod)
        self.assertEqual(t["offset"], (0.5, 0.2, 0.0))
        self.assertEqual(t["rotation"], (0.0, 0.0, 90.0))
        self.assertEqual(t["scale"], (1.0, 1.0, 1.0))

        ok = update_footprint_model_transform(
            self.fp1, 0, offset=(1.2, -0.4, 0.8), rotation=(0.0, 180.0, -90.0), scale=(0.3937, 0.3937, 0.3937)
        )
        self.assertTrue(ok)

        updated_mod = get_footprint_models(self.fp1)[0]
        t2 = get_model_transform(updated_mod)
        self.assertAlmostEqual(t2["offset"][0], 1.2)
        self.assertAlmostEqual(t2["offset"][1], -0.4)
        self.assertAlmostEqual(t2["offset"][2], 0.8)
        self.assertAlmostEqual(t2["rotation"][1], 180.0)
        self.assertAlmostEqual(t2["rotation"][2], -90.0)
        self.assertAlmostEqual(t2["scale"][0], 0.3937)

    def test_find_candidates_strict(self):
        candidates = find_candidate_footprints(
            self.board, self.fp1, match_by_name_only=False, include_with_models=False
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].reference, "R2")

    def test_find_candidates_by_name_only(self):
        candidates = find_candidate_footprints(
            self.board, self.fp1, match_by_name_only=True, include_with_models=False
        )
        self.assertEqual(len(candidates), 2)
        refs = [c.reference for c in candidates]
        self.assertIn("R2", refs)
        self.assertIn("R3", refs)

    def test_apply_models(self):
        src_models = get_footprint_models(self.fp1)
        self.assertEqual(len(get_footprint_models(self.fp2)), 0)

        applied = apply_3d_models_to_footprint(src_models, self.fp2)
        self.assertEqual(applied, 1)

        fp2_models = get_footprint_models(self.fp2)
        self.assertEqual(len(fp2_models), 1)
        self.assertEqual(fp2_models[0].m_Filename, src_models[0].m_Filename)

    def test_global_audit_and_propagate(self):
        board = pcbnew.BOARD()

        r1 = pcbnew.FOOTPRINT(board)
        r1.SetReference("R1")
        r1.SetFPIDAsString("Resistor_SMD:R_0805_2012Metric")
        mod = pcbnew.FP_3DMODEL()
        mod.m_Filename = "resistor.step"
        r1.Add3DModel(mod)

        r2 = pcbnew.FOOTPRINT(board)
        r2.SetReference("R2")
        r2.SetFPIDAsString("Resistor_SMD:R_0805_2012Metric")

        r3 = pcbnew.FOOTPRINT(board)
        r3.SetReference("R3")
        r3.SetFPIDAsString("Resistor_SMD:R_0805_2012Metric")

        c1 = pcbnew.FOOTPRINT(board)
        c1.SetReference("C1")
        c1.SetFPIDAsString("Capacitor_SMD:C_0805_2012Metric")

        c2 = pcbnew.FOOTPRINT(board)
        c2.SetReference("C2")
        c2.SetFPIDAsString("Capacitor_SMD:C_0805_2012Metric")

        d1 = pcbnew.FOOTPRINT(board)
        d1.SetReference("D1")
        d1.SetFPIDAsString("Diode_SMD:D_SOD-123")
        d_mod = pcbnew.FP_3DMODEL()
        d_mod.m_Filename = "diode.step"
        d1.Add3DModel(d_mod)

        for fp in [r1, r2, r3, c1, c2, d1]:
            board.Add(fp)

        audit = audit_and_propagate_all_board(board, match_by_name_only=False, overwrite=False)

        self.assertEqual(audit.total_footprints, 6)
        self.assertEqual(audit.total_families, 3)
        self.assertEqual(len(audit.families_completed), 1)
        self.assertEqual(audit.families_completed[0].family_key, "Resistor_SMD:R_0805_2012Metric")
        self.assertEqual(audit.families_completed[0].updated_refs, ["R2", "R3"])
        self.assertEqual(audit.total_fps_updated, 2)

        self.assertEqual(len(audit.families_skipped_no_model), 1)
        self.assertEqual(audit.families_skipped_no_model[0].family_key, "Capacitor_SMD:C_0805_2012Metric")

        self.assertEqual(len(audit.families_already_full), 1)
        self.assertEqual(audit.families_already_full[0].family_key, "Diode_SMD:D_SOD-123")

    def test_export_and_import_presets(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            preset_file = tf.name

        try:
            count = export_3d_presets(self.board, preset_file, preset_name="TestPreset")
            self.assertEqual(count, 1)

            new_board = pcbnew.BOARD()
            target_r10 = pcbnew.FOOTPRINT(new_board)
            target_r10.SetReference("R10")
            target_r10.SetFPIDAsString("Resistor_SMD:R_0805_2012Metric")

            target_r11 = pcbnew.FOOTPRINT(new_board)
            target_r11.SetReference("R11")
            target_r11.SetFPIDAsString("Resistor_SMD:R_0805_2012Metric")

            new_board.Add(target_r10)
            new_board.Add(target_r11)

            res = import_3d_presets(new_board, preset_file)
            self.assertTrue(res["success"])
            self.assertEqual(res["total_updated"], 2)
            self.assertEqual(res["matched_families"], 1)

            r10_models = get_footprint_models(target_r10)
            self.assertEqual(len(r10_models), 1)
            self.assertEqual(r10_models[0].m_Filename, "${KICAD8_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0805_2012Metric.wrl")
            self.assertAlmostEqual(r10_models[0].m_Offset.x, 0.5)
            self.assertAlmostEqual(r10_models[0].m_Rotation.z, 90.0)

        finally:
            if os.path.exists(preset_file):
                os.remove(preset_file)

    def test_export_and_import_presets_more_than_12_fps(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            preset_file = tf.name

        try:
            export_3d_presets(self.board, preset_file, preset_name="TestPreset15")

            new_board = pcbnew.BOARD()
            for i in range(1, 16):
                fp = pcbnew.FOOTPRINT(new_board)
                fp.SetReference(f"R{i}")
                fp.SetFPIDAsString("Resistor_SMD:R_0805_2012Metric")
                new_board.Add(fp)

            res = import_3d_presets(new_board, preset_file)
            self.assertTrue(res["success"])
            self.assertEqual(res["total_updated"], 15)
            self.assertEqual(len(res["updated_refs"]), 15)

            # Test formatting logic from _on_import_preset
            updated_refs = res.get("updated_refs", [])
            refs_str = ", ".join(updated_refs[:12])
            if len(updated_refs) > 12:
                refs_str += f" ... (+{len(updated_refs) - 12} más)"
            self.assertIn("(+3 más)", refs_str)

        finally:
            if os.path.exists(preset_file):
                os.remove(preset_file)

    def test_library_model_auto_search(self):
        results = find_matching_3d_models(self.fp1)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].filename, "R_0805_2012Metric.step")
        self.assertGreaterEqual(results[0].score, 80)
        self.assertTrue(results[0].kicad_path.endswith("R_0805_2012Metric.step"))

        soic_results = find_matching_3d_models(None, custom_query="SOIC-8")
        self.assertGreater(len(soic_results), 0)
        self.assertTrue(any("SOIC-8" in r.filename for r in soic_results))

    def test_filter_candidate_footprints(self):
        c1 = FootprintCandidate(None, "R2", "10k", "Resistor_SMD:R_0805", "R_0805", 0.0, 0.0, False, 0, "")
        c2 = FootprintCandidate(None, "R3", "22k", "Resistor_SMD:R_0805", "R_0805", 0.0, 0.0, False, 0, "")
        c3 = FootprintCandidate(None, "R4", "10k", "Resistor_SMD:R_0805", "R_0805", 0.0, 0.0, True, 1, "r.step")
        c4 = FootprintCandidate(None, "C1", "100nF", "Capacitor_SMD:C_0805", "C_0805", 0.0, 0.0, False, 0, "")

        cands = [c1, c2, c3, c4]

        # 1. Filter by text query
        f_10k = filter_candidate_footprints(cands, query="10k")
        self.assertEqual(len(f_10k), 2)
        self.assertEqual([c.reference for c in f_10k], ["R2", "R4"])

        # 2. Filter by wildcard query
        f_r = filter_candidate_footprints(cands, query="R*")
        self.assertEqual(len(f_r), 3)

        # 3. Filter by status: no_3d
        f_no_3d = filter_candidate_footprints(cands, status_filter="no_3d")
        self.assertEqual(len(f_no_3d), 3)
        self.assertNotIn("R4", [c.reference for c in f_no_3d])

        # 4. Filter by status: has_3d
        f_has_3d = filter_candidate_footprints(cands, status_filter="has_3d")
        self.assertEqual(len(f_has_3d), 1)
        self.assertEqual(f_has_3d[0].reference, "R4")

        # 5. Combined query + status
        f_comb = filter_candidate_footprints(cands, query="10k", status_filter="no_3d")
        self.assertEqual(len(f_comb), 1)
        self.assertEqual(f_comb[0].reference, "R2")

    def test_clear_3d_models(self):
        # 1. Clear single footprint
        self.assertEqual(len(get_footprint_models(self.fp1)), 1)
        cleared_count = clear_3d_models_from_footprint(self.fp1)
        self.assertEqual(cleared_count, 1)
        self.assertEqual(len(get_footprint_models(self.fp1)), 0)

        # 2. Clear candidate list
        m2 = pcbnew.FP_3DMODEL()
        m2.m_Filename = "r2.step"
        self.fp2.Add3DModel(m2)
        self.assertEqual(len(get_footprint_models(self.fp2)), 1)

        c2 = FootprintCandidate(self.fp2, "R2", "10k", "Resistor_SMD:R_0805", "R_0805", 0.0, 0.0, True, 1, "r2.step")
        fps_c, mods_c = clear_3d_models_from_candidates([c2])
        self.assertEqual(fps_c, 1)
        self.assertEqual(mods_c, 1)
        self.assertEqual(len(get_footprint_models(self.fp2)), 0)

        # 3. Clear entire family
        m_r1 = pcbnew.FP_3DMODEL()
        m_r1.m_Filename = "r1.step"
        self.fp1.Add3DModel(m_r1)

        m_r2 = pcbnew.FP_3DMODEL()
        m_r2.m_Filename = "r2.step"
        self.fp2.Add3DModel(m_r2)

        fps_fam, mods_fam, refs = clear_3d_models_for_entire_family(
            self.board, "Resistor_SMD:R_0805_2012Metric", match_by_name_only=False
        )
        self.assertEqual(fps_fam, 2)
        self.assertEqual(mods_fam, 2)
        self.assertIn("R1", refs)
        self.assertIn("R2", refs)
        self.assertEqual(len(get_footprint_models(self.fp1)), 0)
        self.assertEqual(len(get_footprint_models(self.fp2)), 0)


if __name__ == "__main__":
    unittest.main()
