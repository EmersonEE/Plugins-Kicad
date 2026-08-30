"""Unit tests for the pure deterministic logic in core.py."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
from tests._fakes import FakeFootprint, FakePad  # noqa: E402


class TestTransformVector(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(core.transform_vector(10, 20, 0), (10, 20))

    def test_rotation_90_ccw(self):
        # Y-down space: CCW 90deg moves a right-pointing vector to point up
        # (negative Y) and a down-pointing vector to point right.
        self.assertEqual(core.transform_vector(10, 0, 90), (0, -10))
        self.assertEqual(core.transform_vector(0, 10, 90), (10, 0))

    def test_rotation_180(self):
        dx, dy = core.transform_vector(10, 20, 180)
        self.assertEqual(dx, -10)
        self.assertEqual(dy, -20)

    def test_rotation_270(self):
        self.assertEqual(core.transform_vector(10, 0, 270), (0, 10))

    def test_mirror_x(self):
        dx, dy = core.transform_vector(10, 20, 0, mirror_x=True)
        self.assertEqual(dx, -10)
        self.assertEqual(dy, 20)

    def test_mirror_then_rotate(self):
        # mirror_x reflects dx first, then rotates.
        dx, dy = core.transform_vector(10, 0, 90, mirror_x=True)
        # mirror -> (-10, 0); rotate 90 CCW -> (0, 10)
        self.assertEqual((dx, dy), (0, 10))


class TestCentroid(unittest.TestCase):
    def test_centroid(self):
        fps = [FakeFootprint("R1", x=0, y=0), FakeFootprint("R2", x=10, y=20)]
        cx, cy = core.centroid(fps)
        self.assertEqual((cx, cy), (5.0, 10.0))


class TestFootprintKey(unittest.TestCase):
    def test_key(self):
        fp = FakeFootprint("R1", value="10k", fp_name="R_0805", pads=[FakePad("1", 0), FakePad("2", 0)])
        self.assertEqual(core.footprint_key(fp), ("10k", "R_0805", 2))

    def test_footprint_name(self):
        fp = FakeFootprint("R1", fp_name="R_0805")
        self.assertEqual(core.footprint_name(fp), "R_0805")


class TestConnectivitySignature(unittest.TestCase):
    def test_shared_net_vs_external(self):
        # R1.pad2 <-> R2.pad1 share net 200.
        r1 = FakeFootprint("R1", pads=[FakePad("1", 100), FakePad("2", 200)])
        r2 = FakeFootprint("R2", pads=[FakePad("1", 200), FakePad("2", 300)])
        block = [r1, r2]
        sig1 = core.connectivity_signature(r1, block)
        sig2 = core.connectivity_signature(r2, block)
        # The shared-net pads are internal (non-empty peers) and the two roles
        # are distinguishable.
        self.assertNotEqual(sig1, sig2)


class TestHungarianAssignment(unittest.TestCase):
    def test_known_3x3(self):
        cost = [[4, 1, 3], [2, 0, 5], [3, 2, 2]]
        order = core.hungarian_assignment(cost)
        self.assertEqual(order, [1, 0, 2])
        self.assertEqual(sum(cost[i][order[i]] for i in range(3)), 5)

    def test_identity(self):
        cost = [[0, 10, 10], [10, 0, 10], [10, 10, 0]]
        self.assertEqual(core.hungarian_assignment(cost), [0, 1, 2])

    def test_single(self):
        self.assertEqual(core.hungarian_assignment([[7]]), [0])

    def test_empty(self):
        self.assertEqual(core.hungarian_assignment([]), [])


class TestMatchGroupByGeometry(unittest.TestCase):
    def _mk(self, ref, x, y):
        return FakeFootprint(ref, x=x, y=y)

    def test_exhaustive_path(self):
        # 3 reference parts on a line; targets are shuffled.
        refs = [self._mk("R1", 0, 0), self._mk("R2", 1000, 0), self._mk("R3", 2000, 0)]
        targets = [self._mk("R1b", 2000, 0), self._mk("R2b", 0, 0), self._mk("R3b", 1000, 0)]
        pairs = core.match_group_by_geometry(refs, targets, (0, 0), (0, 0), 0)
        for ref_fp, target_fp in pairs:
            self.assertEqual(
                core.position(ref_fp), core.position(target_fp)
            )

    def test_hungarian_path_large_group(self):
        # >8 identical-position parts forces the Hungarian branch; every pair
        # should land with zero cost (exact position match).
        coords = [(i * 1000, 0) for i in range(9)]
        refs = [self._mk("R{}".format(i), x, y) for i, (x, y) in enumerate(coords)]
        targets = [self._mk("T{}".format(i), x, y) for i, (x, y) in enumerate(reversed(coords))]
        pairs = core.match_group_by_geometry(refs, targets, (0, 0), (0, 0), 0)
        self.assertEqual(len(pairs), 9)
        for ref_fp, target_fp in pairs:
            self.assertEqual(core.position(ref_fp), core.position(target_fp))


class TestPlanBlock(unittest.TestCase):
    def test_empty_reference_rejected(self):
        ok, result = core.plan_block([], [FakeFootprint("R2")])
        self.assertFalse(ok)
        self.assertIn("referencia", result)

    def test_empty_target_rejected(self):
        ok, result = core.plan_block([FakeFootprint("R1")], [])
        self.assertFalse(ok)
        self.assertIn("destino", result)

    def test_anchor_and_rotation_plan(self):
        refs = [
            FakeFootprint("R1", x=0, y=0),
            FakeFootprint("R2", x=1000, y=0),
        ]
        targets = [
            FakeFootprint("R3", x=10000, y=10000),
            FakeFootprint("R4", x=11000, y=10000),
        ]
        ok, result = core.plan_block(
            refs, targets, anchor_ref_name="R1", rotation=90
        )
        self.assertTrue(ok)
        planned = {(entry[1], entry[2]) for entry in result["footprint_plan"]}
        self.assertEqual(planned, {(10000, 10000), (10000, 9000)})

    def test_mapping_analysis_lists_confirmed_pairs(self):
        refs = [FakeFootprint("R1", x=0), FakeFootprint("R2", x=1000000)]
        targets = [
            FakeFootprint("R3", x=10000000),
            FakeFootprint("R4", x=11000000),
        ]
        result = core.mapping_analysis(refs, targets)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(result["ambiguous"], [])

    def test_mapping_analysis_accepts_unhashable_footprints(self):
        class UnhashableFootprint(FakeFootprint):
            __hash__ = None

        refs = [UnhashableFootprint("R1", x=0)]
        targets = [UnhashableFootprint("R2", x=1000000)]
        result = core.mapping_analysis(refs, targets)
        self.assertTrue(result["ok"])
        self.assertEqual(result["rows"][0]["target"], "R2")

    def test_target_origin_override_places_block_on_matrix_point(self):
        refs = [FakeFootprint("R1", x=0), FakeFootprint("R2", x=1000000)]
        targets = [FakeFootprint("R3", x=5000000), FakeFootprint("R4", x=6000000)]
        ok, result = core.plan_block(
            refs, targets, target_origin_override=(20000000, 30000000)
        )
        self.assertTrue(ok)
        planned = {(entry[1], entry[2]) for entry in result["footprint_plan"]}
        self.assertEqual(
            planned,
            {(19500000, 30000000), (20500000, 30000000)},
        )

    def test_locked_target_rejected(self):
        ref = FakeFootprint("R1", x=0, y=0)
        target = FakeFootprint("R2", x=500, y=500, locked=True)
        ok, result = core.plan_block([ref], [target])
        self.assertFalse(ok)
        self.assertIn("bloqueado", result)

    def test_mismatched_keys(self):
        ref = FakeFootprint("R1", value="10k")
        target = FakeFootprint("R2", value="1k")
        ok, result = core.plan_block([ref], [target])
        self.assertFalse(ok)


class TestBuildNetMap(unittest.TestCase):
    def test_map_built(self):
        class Net:
            pass

        net_a = Net()
        net_b = Net()
        ref = FakeFootprint("R1", pads=[FakePad("1", 100, net=net_a)])
        target = FakeFootprint("R2", pads=[FakePad("1", 200, net=net_b)])
        net_map = core.build_net_map([(ref, target)])
        self.assertEqual(net_map, {100: net_b})


class TestValidateDiagnose(unittest.TestCase):
    def test_empty_blocks_report_clear_errors(self):
        errors, matched = core.validate_block([], [])
        self.assertEqual(matched, 0)
        self.assertTrue(any("referencia" in error for error in errors))

    def test_valid(self):
        ref = FakeFootprint("R1", x=0, y=0)
        target = FakeFootprint("R1b", x=10, y=10)
        errors, matched = core.validate_block([ref], [target])
        self.assertEqual(errors, [])
        self.assertEqual(matched, 1)

    def test_locked(self):
        ref = FakeFootprint("R1")
        target = FakeFootprint("R2", locked=True)
        errors, _ = core.validate_block([ref], [target])
        self.assertTrue(any("bloqueados" in e for e in errors))

    def test_diagnose_extra(self):
        ref = FakeFootprint("R1", value="10k", fp_name="R_0805")
        target1 = FakeFootprint("R2", value="10k", fp_name="R_0805")
        target2 = FakeFootprint("R3", value="10k", fp_name="R_0805")
        diag = core.diagnose_block([ref], [target1, target2])
        self.assertEqual(len(diag["extra"]), 1)

    def test_suggest_fixes_locked(self):
        diag = {"locked": ["R2"], "overlap": [], "missing": [], "extra": [], "is_valid": False}
        hints = core.suggest_fixes(diag)
        self.assertTrue(any("Desbloquea" in h for h in hints))


class TestHelpers(unittest.TestCase):
    def test_extract_ref_number(self):
        self.assertEqual(core.extract_ref_number("R12"), 12)
        self.assertEqual(core.extract_ref_number("U7_A"), 7)

    def test_format_references(self):
        fps = [FakeFootprint("R2"), FakeFootprint("R1"), FakeFootprint("R3")]
        self.assertEqual(core.format_references(fps), "R1, R2, R3")

    def test_overlapping_pairs(self):
        bboxes = [(0, 0, 100, 100), (150, 0, 250, 100)]
        self.assertEqual(core.overlapping_pairs(bboxes, margin_nm=0), [])
        self.assertEqual(core.overlapping_pairs(bboxes, margin_nm=100), [(1, 2)])


if __name__ == "__main__":
    unittest.main()
