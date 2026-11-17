"""Unit tests for Net Routing Progress analysis engine in KiCad 10."""

import os
import tempfile
import unittest
import pcbnew

from core.routing_analyzer import (
    BoardRoutingSummary,
    NetRoutingInfo,
    analyze_board_routing,
    export_routing_report_to_csv,
)


class TestRoutingAnalyzer(unittest.TestCase):

    def setUp(self):
        self.board = pcbnew.BOARD()

    def test_empty_board(self):
        summary = analyze_board_routing(self.board)
        self.assertEqual(summary.total_nets, 0)
        self.assertEqual(summary.total_pads, 0)
        self.assertEqual(summary.total_expected_connections, 0)
        self.assertEqual(summary.total_pending_connections, 0)
        self.assertEqual(summary.global_pct_pending, 0.0)
        self.assertEqual(summary.global_pct_routed, 100.0)

    def test_single_pad_and_empty_nets(self):
        net_dummy = pcbnew.NETINFO_ITEM(self.board, "DUMMY_EMPTY", 1)
        net_single = pcbnew.NETINFO_ITEM(self.board, "TEST_POINT", 2)
        self.board.Add(net_dummy)
        self.board.Add(net_single)

        fp = pcbnew.FOOTPRINT(self.board)
        fp.SetReference("TP1")
        p = pcbnew.PAD(fp)
        p.SetNumber("1")
        p.SetNetCode(2)
        p.SetPosition(pcbnew.VECTOR2I(0, 0))
        fp.Add(p)
        self.board.Add(fp)

        summary = analyze_board_routing(self.board)
        self.assertEqual(summary.total_nets, 2)
        self.assertEqual(summary.active_nets, 0)
        self.assertEqual(summary.single_or_empty_nets, 2)
        self.assertEqual(summary.total_expected_connections, 0)
        self.assertEqual(summary.total_pending_connections, 0)

        nets_map = {n.netname: n for n in summary.net_results}
        self.assertEqual(nets_map["DUMMY_EMPTY"].total_pads, 0)
        self.assertEqual(nets_map["DUMMY_EMPTY"].pct_pending, 0.0)
        self.assertEqual(nets_map["TEST_POINT"].total_pads, 1)
        self.assertEqual(nets_map["TEST_POINT"].pct_pending, 0.0)

    def test_unrouted_and_partially_routed_nets(self):
        net_gnd = pcbnew.NETINFO_ITEM(self.board, "GND", 1)
        net_vcc = pcbnew.NETINFO_ITEM(self.board, "VCC", 2)
        self.board.Add(net_gnd)
        self.board.Add(net_vcc)

        # 4 pads on GND at (0,0), (10,0), (20,0), (30,0) mm
        gnd_pads = []
        for i in range(4):
            fp = pcbnew.FOOTPRINT(self.board)
            fp.SetReference(f"R{i+1}")
            pad = pcbnew.PAD(fp)
            pad.SetNumber("1")
            pad.SetNetCode(1)
            pad.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(i * 10), 0))
            fp.Add(pad)
            self.board.Add(fp)
            gnd_pads.append(pad)

        # 3 pads on VCC (completely unrouted)
        for j in range(3):
            fp = pcbnew.FOOTPRINT(self.board)
            fp.SetReference(f"C{j+1}")
            pad = pcbnew.PAD(fp)
            pad.SetNumber("1")
            pad.SetNetCode(2)
            pad.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(j * 10), pcbnew.FromMM(20)))
            fp.Add(pad)
            self.board.Add(fp)

        # Connect GND pad 0 to pad 1 with 1 track (10mm)
        t = pcbnew.PCB_TRACK(self.board)
        t.SetStart(gnd_pads[0].GetPosition())
        t.SetEnd(gnd_pads[1].GetPosition())
        t.SetWidth(pcbnew.FromMM(0.25))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNetCode(1)
        self.board.Add(t)

        summary = analyze_board_routing(self.board)
        self.assertEqual(summary.total_nets, 2)
        self.assertEqual(summary.active_nets, 2)

        nets_map = {n.netname: n for n in summary.net_results}

        # VCC: 3 pads -> 2 expected connections, 3 clusters, 2 pending -> 100.0% pending
        vcc_res = nets_map["VCC"]
        self.assertEqual(vcc_res.total_pads, 3)
        self.assertEqual(vcc_res.total_connections, 2)
        self.assertEqual(vcc_res.connected_clusters, 3)
        self.assertEqual(vcc_res.pending_connections, 2)
        self.assertEqual(vcc_res.pct_pending, 100.0)
        self.assertEqual(vcc_res.pct_routed, 0.0)

        # GND: 4 pads -> 3 expected connections, 3 clusters ({p0, p1}, {p2}, {p3}), 2 pending -> 66.7% pending
        gnd_res = nets_map["GND"]
        self.assertEqual(gnd_res.total_pads, 4)
        self.assertEqual(gnd_res.total_connections, 3)
        self.assertEqual(gnd_res.connected_clusters, 3)
        self.assertEqual(gnd_res.pending_connections, 2)
        self.assertAlmostEqual(gnd_res.pct_pending, 66.7, places=1)
        self.assertAlmostEqual(gnd_res.pct_routed, 33.3, places=1)
        self.assertEqual(gnd_res.track_count, 1)
        self.assertAlmostEqual(gnd_res.routed_length_mm, 10.0, places=1)

        # Global stats: total expected = 2 + 3 = 5, total pending = 2 + 2 = 4 -> 80.0% pending
        self.assertEqual(summary.total_expected_connections, 5)
        self.assertEqual(summary.total_pending_connections, 4)
        self.assertEqual(summary.global_pct_pending, 80.0)
        self.assertEqual(summary.global_pct_routed, 20.0)

    def test_fully_routed_net(self):
        net_clk = pcbnew.NETINFO_ITEM(self.board, "CLK", 1)
        self.board.Add(net_clk)

        pads = []
        for i in range(3):
            fp = pcbnew.FOOTPRINT(self.board)
            fp.SetReference(f"U{i+1}")
            pad = pcbnew.PAD(fp)
            pad.SetNumber("1")
            pad.SetNetCode(1)
            pad.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(i * 15), 0))
            fp.Add(pad)
            self.board.Add(fp)
            pads.append(pad)

        # Track 1: U1.1 to U2.1
        t1 = pcbnew.PCB_TRACK(self.board)
        t1.SetStart(pads[0].GetPosition())
        t1.SetEnd(pads[1].GetPosition())
        t1.SetWidth(pcbnew.FromMM(0.2))
        t1.SetLayer(pcbnew.F_Cu)
        t1.SetNetCode(1)
        self.board.Add(t1)

        # Track 2: U2.1 to U3.1
        t2 = pcbnew.PCB_TRACK(self.board)
        t2.SetStart(pads[1].GetPosition())
        t2.SetEnd(pads[2].GetPosition())
        t2.SetWidth(pcbnew.FromMM(0.2))
        t2.SetLayer(pcbnew.F_Cu)
        t2.SetNetCode(1)
        self.board.Add(t2)

        summary = analyze_board_routing(self.board)
        self.assertEqual(summary.completed_nets, 1)
        self.assertEqual(summary.unrouted_nets, 0)
        self.assertEqual(summary.in_progress_nets, 0)

        clk_res = summary.net_results[0]
        self.assertEqual(clk_res.total_pads, 3)
        self.assertEqual(clk_res.total_connections, 2)
        self.assertEqual(clk_res.connected_clusters, 1)
        self.assertEqual(clk_res.pending_connections, 0)
        self.assertEqual(clk_res.pct_pending, 0.0)
        self.assertEqual(clk_res.pct_routed, 100.0)
        self.assertEqual(clk_res.status_label, "100% Ruteado")

    def test_csv_export(self):
        net_clk = pcbnew.NETINFO_ITEM(self.board, "CLK", 1)
        self.board.Add(net_clk)
        fp = pcbnew.FOOTPRINT(self.board)
        fp.SetReference("U1")
        pad = pcbnew.PAD(fp)
        pad.SetNetCode(1)
        pad.SetPosition(pcbnew.VECTOR2I(0, 0))
        fp.Add(pad)
        self.board.Add(fp)

        summary = analyze_board_routing(self.board)

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
            csv_path = tf.name

        try:
            ok = export_routing_report_to_csv(summary, csv_path)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
                self.assertIn("INFORME DE PROGRESO DE RUTEO DE NETS", content)
                self.assertIn("CLK", content)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)


if __name__ == "__main__":
    unittest.main()
