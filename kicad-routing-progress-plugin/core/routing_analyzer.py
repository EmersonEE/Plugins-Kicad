"""Routing progress and net connectivity analysis engine for KiCad 10."""

import csv
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import pcbnew

# Apply SwigPyIterator patch for Python 3.12+ / 3.14+ compatibility
try:
    for attr in dir(pcbnew):
        obj = getattr(pcbnew, attr, None)
        if isinstance(obj, type) and "SwigPyIterator" in attr:
            if hasattr(obj, "__next__") and not hasattr(obj, "next"):
                obj.next = lambda self: self.__next__()
except Exception:
    pass


@dataclass
class NetRoutingInfo:
    """Detailed routing progress information for a single net."""

    netname: str
    netcode: int
    total_pads: int
    total_connections: int
    connected_clusters: int
    pending_connections: int
    pct_pending: float
    pct_routed: float
    track_count: int
    via_count: int
    routed_length_mm: float
    status_label: str
    pads_info: List[str] = field(default_factory=list)


@dataclass
class BoardRoutingSummary:
    """Global board routing progress summary."""

    total_nets: int = 0
    active_nets: int = 0
    completed_nets: int = 0
    in_progress_nets: int = 0
    unrouted_nets: int = 0
    single_or_empty_nets: int = 0
    total_pads: int = 0
    total_expected_connections: int = 0
    total_pending_connections: int = 0
    global_pct_pending: float = 0.0
    global_pct_routed: float = 0.0
    total_track_length_mm: float = 0.0
    total_tracks: int = 0
    total_vias: int = 0
    analyzed_at: str = ""
    net_results: List[NetRoutingInfo] = field(default_factory=list)


def _get_pad_unique_id(pad) -> Tuple[int, int, str, str]:
    """Generate a stable hashable identifier for a pad."""
    pos = pad.GetPosition()
    fp = pad.GetParentFootprint()
    ref = fp.GetReference() if fp else ""
    num = str(pad.GetNumber())
    return (pos.x, pos.y, ref, num)


def _get_pad_display_name(pad) -> str:
    """Return human readable pad name like 'R1.1' or 'U2.GND'."""
    fp = pad.GetParentFootprint()
    ref = fp.GetReference() if fp else "PCB"
    num = str(pad.GetNumber())
    return f"{ref}.{num}" if num else ref


def analyze_board_routing(board) -> BoardRoutingSummary:
    """Analyze routing connectivity for all nets in the given KiCad board."""
    summary = BoardRoutingSummary(analyzed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if not board:
        return summary

    try:
        board.BuildConnectivity()
        conn = board.GetConnectivity()
    except Exception:
        conn = None

    # 1. Group pads by netcode
    pads_by_net: Dict[int, List[any]] = {}
    try:
        for pad in board.GetPads():
            netcode = pad.GetNetCode()
            if netcode > 0:
                pads_by_net.setdefault(netcode, []).append(pad)
    except Exception:
        pass

    # 2. Group tracks and vias by netcode
    tracks_by_net: Dict[int, List[any]] = {}
    vias_by_net: Dict[int, List[any]] = {}
    total_track_length_nm = 0

    try:
        for tr in board.GetTracks():
            netcode = tr.GetNetCode()
            if netcode <= 0:
                continue

            is_via = hasattr(pcbnew, "PCB_VIA") and isinstance(tr, pcbnew.PCB_VIA)
            if not is_via and hasattr(tr, "Type") and hasattr(pcbnew, "PCB_VIA_T"):
                is_via = (tr.Type() == pcbnew.PCB_VIA_T)

            if is_via:
                vias_by_net.setdefault(netcode, []).append(tr)
                summary.total_vias += 1
            else:
                tracks_by_net.setdefault(netcode, []).append(tr)
                summary.total_tracks += 1
                try:
                    total_track_length_nm += tr.GetLength()
                except Exception:
                    pass
    except Exception:
        pass

    summary.total_track_length_mm = round(total_track_length_nm / 1e6, 2)

    # 3. Process every net
    nets_by_name = {}
    try:
        nets_by_name = board.GetNetsByName()
    except Exception:
        pass

    net_list: List[NetRoutingInfo] = []

    for netname_raw, net_item in nets_by_name.items():
        netname = str(netname_raw).strip()
        if not netname:
            continue

        try:
            netcode = net_item.GetNetCode()
        except Exception:
            continue

        if netcode <= 0:
            continue

        summary.total_nets += 1
        pads = pads_by_net.get(netcode, [])
        total_pads = len(pads)
        summary.total_pads += total_pads

        tracks = tracks_by_net.get(netcode, [])
        vias = vias_by_net.get(netcode, [])
        track_count = len(tracks)
        via_count = len(vias)

        routed_len_nm = sum(getattr(t, "GetLength", lambda: 0)() for t in tracks)
        routed_len_mm = round(routed_len_nm / 1e6, 2)

        pads_display = [_get_pad_display_name(p) for p in pads]

        if total_pads <= 1:
            summary.single_or_empty_nets += 1
            total_conns = 0
            clusters = total_pads
            pending_conns = 0
            pct_pending = 0.0
            pct_routed = 100.0
            status = "Completo (1 pad)" if total_pads == 1 else "Sin pads"
        else:
            summary.active_nets += 1
            total_conns = total_pads - 1
            summary.total_expected_connections += total_conns

            visited_pad_ids: Set[Tuple[int, int, str, str]] = set()
            clusters = 0

            for p in pads:
                p_id = _get_pad_unique_id(p)
                if p_id in visited_pad_ids:
                    continue

                clusters += 1
                visited_pad_ids.add(p_id)

                if conn:
                    try:
                        connected_items = conn.GetConnectedItems(p)
                        for item in connected_items:
                            if isinstance(item, pcbnew.PAD):
                                visited_pad_ids.add(_get_pad_unique_id(item))
                    except Exception:
                        pass

            pending_conns = max(0, clusters - 1)
            summary.total_pending_connections += pending_conns

            pct_pending = (pending_conns / total_conns) * 100.0 if total_conns > 0 else 0.0
            pct_routed = 100.0 - pct_pending

            if pending_conns == 0:
                summary.completed_nets += 1
                status = "100% Ruteado"
            elif pending_conns == total_conns:
                summary.unrouted_nets += 1
                status = "100% Pendiente"
            else:
                summary.in_progress_nets += 1
                status = f"{pct_pending:.1f}% Pendiente"

        net_list.append(
            NetRoutingInfo(
                netname=netname,
                netcode=netcode,
                total_pads=total_pads,
                total_connections=total_conns,
                connected_clusters=clusters,
                pending_connections=pending_conns,
                pct_pending=round(pct_pending, 1),
                pct_routed=round(pct_routed, 1),
                track_count=track_count,
                via_count=via_count,
                routed_length_mm=routed_len_mm,
                status_label=status,
                pads_info=pads_display,
            )
        )

    # Sort nets by % pending descending (most unrouted first), then by netname
    net_list.sort(key=lambda item: (-item.pct_pending, -item.pending_connections, item.netname.lower()))
    summary.net_results = net_list

    if summary.total_expected_connections > 0:
        summary.global_pct_pending = round(
            (summary.total_pending_connections / summary.total_expected_connections) * 100.0, 1
        )
        summary.global_pct_routed = round(100.0 - summary.global_pct_pending, 1)
    else:
        summary.global_pct_pending = 0.0
        summary.global_pct_routed = 100.0

    return summary


def export_routing_report_to_csv(summary: BoardRoutingSummary, filepath: str) -> bool:
    """Export board routing progress analysis to a CSV file."""
    if not summary or not filepath:
        return False

    try:
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)

            # Metadata Header
            writer.writerow(["# INFORME DE PROGRESO DE RUTEO DE NETS - KICAD"])
            writer.writerow(["# Fecha de análisis", summary.analyzed_at])
            writer.writerow(["# Total de Nets", summary.total_nets])
            writer.writerow(["# Nets Activas (>=2 pads)", summary.active_nets])
            writer.writerow(["# Nets 100% Ruteadas", summary.completed_nets])
            writer.writerow(["# Nets En Progreso", summary.in_progress_nets])
            writer.writerow(["# Nets 100% Pendientes", summary.unrouted_nets])
            writer.writerow(["# Conexiones Totales Esperadas", summary.total_expected_connections])
            writer.writerow(["# Conexiones Pendientes (Ratsnest)", summary.total_pending_connections])
            writer.writerow(["# % Ruteo Global Pendiente", f"{summary.global_pct_pending}%"])
            writer.writerow(["# % Ruteo Global Completado", f"{summary.global_pct_routed}%"])
            writer.writerow(["# Longitud Total de Pistas (mm)", f"{summary.total_track_length_mm} mm"])
            writer.writerow([])

            # Table Header
            writer.writerow([
                "Nombre de Net",
                "NetCode",
                "Total Pads",
                "Conexiones Requeridas",
                "Islas/Clusters",
                "Conexiones Pendientes",
                "% Ruteo Pendiente",
                "% Ruteo Completado",
                "Nº Pistas",
                "Nº Vías",
                "Longitud Pistas (mm)",
                "Estado",
                "Pads",
            ])

            for net in summary.net_results:
                writer.writerow([
                    net.netname,
                    net.netcode,
                    net.total_pads,
                    net.total_connections,
                    net.connected_clusters,
                    net.pending_connections,
                    f"{net.pct_pending}%",
                    f"{net.pct_routed}%",
                    net.track_count,
                    net.via_count,
                    net.routed_length_mm,
                    net.status_label,
                    "; ".join(net.pads_info),
                ])

        return True
    except Exception:
        return False
