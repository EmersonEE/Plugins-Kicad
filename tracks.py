"""KiCad PCB editor integrations: positions, orientations, copper replication.

This module is the only place that touches the mutable ``pcbnew`` API for board
objects. Pure geometry lives in ``core.py``; this module imports from it.
"""

import pcbnew

from . import config as config_module
from . import core

# Patch SwigPyIterator for Python 3.12+ / 3.14+ compatibility. KiCad's SWIG
# bindings still expect an object with ``next()`` in some code paths.
try:
    for attr in dir(pcbnew):
        obj = getattr(pcbnew, attr, None)
        if isinstance(obj, type) and "SwigPyIterator" in attr:
            if hasattr(obj, "__next__") and not hasattr(obj, "next"):
                obj.next = lambda self: self.__next__()
except Exception:
    pass


def get_current_board(fallback=None):
    """Backend boundary for obtaining the active PCB editor board."""
    try:
        return pcbnew.GetBoard() or fallback
    except Exception:
        return fallback


def refresh_editor():
    """Backend boundary for repainting PCB Editor."""
    try:
        pcbnew.Refresh()
    except Exception:
        pass


def set_position(footprint, x, y):
    try:
        footprint.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
    except (AttributeError, TypeError):
        footprint.SetPosition(pcbnew.wxPoint(int(x), int(y)))


def set_orientation_with_rotation(footprint, source, rotation_degrees=0.0, mirror_x=False):
    """Copy source orientation, optionally mirror it, then add block rotation."""
    base_orientation = source.GetOrientation()

    if mirror_x:
        try:
            base_orientation = -base_orientation
        except (AttributeError, TypeError):
            base_orientation = -int(base_orientation)

    if rotation_degrees == 0:
        footprint.SetOrientation(base_orientation)
        return

    try:
        # KiCad 7+ EDA_ANGLE
        add_angle = pcbnew.EDA_ANGLE(float(rotation_degrees), pcbnew.DEGREES_T)
        footprint.SetOrientation(base_orientation + add_angle)
    except (AttributeError, TypeError):
        try:
            footprint.SetOrientation(
                base_orientation + int(round(rotation_degrees * 10))
            )
        except (TypeError, ValueError):
            try:
                footprint.SetOrientation(base_orientation + float(rotation_degrees))
            except Exception:
                footprint.SetOrientation(base_orientation)


def set_orientation(footprint, source):
    """Copy KiCad's native angle object without modification."""
    footprint.SetOrientation(source.GetOrientation())


def apply_plan(fp_plan):
    """Apply a footprint plan produced by ``core.plan_block``."""
    for entry in fp_plan:
        target_fp, x, y, source_fp, rotation, mirror_x = entry
        set_position(target_fp, x, y)
        set_orientation_with_rotation(target_fp, source_fp, rotation, mirror_x)


def select_footprints(board):
    if not board:
        try:
            board = pcbnew.GetBoard()
        except Exception:
            return []
    selected = []
    for fp in board.GetFootprints():
        try:
            if fp.IsSelected():
                selected.append(fp)
            elif hasattr(fp, "HasSelectedAncestorGroup") and fp.HasSelectedAncestorGroup():
                selected.append(fp)
        except Exception:
            pass
    return selected


def select_in_board(board, footprints):
    """Highlight a set of footprints in the PCB editor by selecting them."""
    if not footprints:
        return
    for fp in board.GetFootprints():
        try:
            fp.ClearSelected()
        except AttributeError:
            try:
                fp.SetSelected(False)
            except Exception:
                pass
    for fp in footprints:
        try:
            fp.SetSelected()
        except TypeError:
            fp.SetSelected(True)
        except Exception:
            pass
    pcbnew.Refresh()


def create_pcb_group(
    board, items, group_name="Bloque_Alineado", add_to_board=True
):
    """Group footprints, tracks, and vias together as a native KiCad PCB_GROUP."""
    if not hasattr(pcbnew, "PCB_GROUP") or not items:
        return None
    try:
        group = pcbnew.PCB_GROUP(board)
        group.SetName(group_name)
        for item in items:
            group.AddItem(item)
        if add_to_board:
            board.Add(group)
        return group
    except Exception:
        return None


def _board_tracks(board):
    """Return board tracks/vias/arcs across KiCad API variants."""
    try:
        return list(board.GetTracks())
    except Exception:
        try:
            return list(board.Tracks())
        except Exception:
            return []


def _board_zones(board):
    """Return board zones across KiCad API variants."""
    for method in ("Zones", "GetZones"):
        try:
            return list(getattr(board, method)())
        except Exception:
            continue
    return []


def _board_drawings(board):
    """Return board graphic shapes across KiCad API variants."""
    for method in ("GetDrawings", "Drawings"):
        try:
            return list(getattr(board, method)())
        except Exception:
            continue
    return []


def collect_reference_tracks(board, reference, config=None):
    """Find tracks, vias, and arcs associated with the reference block."""
    if not board or not reference:
        return []

    config = config or config_module.default_config()

    # 1. Collect net codes of the reference pads.
    ref_net_codes = set()
    for fp in reference:
        for pad in fp.Pads():
            net_id = core.pad_net_id(pad)
            if net_id not in (0, "", None, -1):
                ref_net_codes.add(net_id)

    # 2. Bounding box of the reference footprints with a configurable margin.
    margin = config["track_collect_margin_nm"]
    xs = [core.position(fp)[0] for fp in reference]
    ys = [core.position(fp)[1] for fp in reference]
    min_x = min(xs) - margin
    max_x = max(xs) + margin
    min_y = min(ys) - margin
    max_y = max(ys) + margin

    def is_inside(x, y):
        return min_x <= x <= max_x and min_y <= y <= max_y

    collected = []
    seen_ids = set()

    for item in _board_tracks(board):
        start = item.GetStart()
        end = item.GetEnd()
        in_area = is_inside(start.x, start.y) and is_inside(end.x, end.y)
        net_code = item.GetNetCode()

        if in_area:
            explicitly_selected = False
            try:
                explicitly_selected = item.IsSelected()
            except Exception:
                pass
            if (
                explicitly_selected
                or not ref_net_codes
                or net_code in ref_net_codes
                or net_code in (0, -1)
            ):
                if id(item) not in seen_ids:
                    collected.append(item)
                    seen_ids.add(id(item))

    return collected


def collect_reference_zones_and_shapes(board, reference, config=None):
    """Find copper zones and graphic shapes inside the reference block area."""
    if not board or not reference:
        return [], []

    config = config or config_module.default_config()
    margin = config["track_collect_margin_nm"]
    xs = [core.position(fp)[0] for fp in reference]
    ys = [core.position(fp)[1] for fp in reference]
    min_x = min(xs) - margin
    max_x = max(xs) + margin
    min_y = min(ys) - margin
    max_y = max(ys) + margin

    def bbox_inside(bbox):
        if bbox is None:
            return False
        try:
            pmin = bbox.GetPosition()
            psize = bbox.GetSize()
            return (
                pmin.x >= min_x
                and pmin.y >= min_y
                and pmin.x + psize.x <= max_x
                and pmin.y + psize.y <= max_y
            )
        except Exception:
            return False

    zones = []
    for zone in _board_zones(board):
        try:
            if zone.IsOnCopperLayer() and bbox_inside(zone.GetBoundingBox()):
                zones.append(zone)
        except Exception:
            continue

    shapes = []
    for shape in _board_drawings(board):
        try:
            if bbox_inside(shape.GetBoundingBox()):
                shapes.append(shape)
        except Exception:
            continue

    return zones, shapes


def _transform_pt(pt, ref_origin, target_origin, rotation, mirror_x):
    ax, ay = ref_origin
    dx, dy = target_origin
    rel_x = pt.x - ax
    rel_y = pt.y - ay
    rot_x, rot_y = core.transform_vector(rel_x, rel_y, rotation, mirror_x)
    return pcbnew.VECTOR2I(int(dx + rot_x), int(dy + rot_y))


def _clone_via(board, item, ref_origin, target_origin, rotation, mirror_x, net_map):
    target_net = net_map.get(item.GetNetCode(), None)
    if item.GetNetCode() not in (0, -1, None, "") and target_net is None:
        return None
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(_transform_pt(item.GetPosition(), ref_origin, target_origin, rotation, mirror_x))
    try:
        via_w = item.GetFrontWidth()
    except Exception:
        try:
            via_w = item.GetWidth(pcbnew.F_Cu)
        except Exception:
            via_w = item.GetWidth()
    via.SetWidth(via_w)
    via.SetDrill(item.GetDrill())
    try:
        via.SetViaType(item.GetViaType())
    except Exception:
        pass
    try:
        via.SetLayerPair(item.TopLayer(), item.BottomLayer())
    except Exception:
        try:
            via.SetLayer(item.GetLayer())
        except Exception:
            pass
    if target_net:
        try:
            via.SetNet(target_net)
        except Exception:
            pass
    return via


def _clone_arc(board, item, ref_origin, target_origin, rotation, mirror_x, net_map):
    target_net = net_map.get(item.GetNetCode(), None)
    if item.GetNetCode() not in (0, -1, None, "") and target_net is None:
        return None
    arc = pcbnew.PCB_ARC(board)
    arc.SetStart(_transform_pt(item.GetStart(), ref_origin, target_origin, rotation, mirror_x))
    arc.SetMid(_transform_pt(item.GetMid(), ref_origin, target_origin, rotation, mirror_x))
    arc.SetEnd(_transform_pt(item.GetEnd(), ref_origin, target_origin, rotation, mirror_x))
    arc.SetWidth(item.GetWidth())
    arc.SetLayer(item.GetLayer())
    if target_net:
        try:
            arc.SetNet(target_net)
        except Exception:
            pass
    return arc


def _clone_track(board, item, ref_origin, target_origin, rotation, mirror_x, net_map):
    target_net = net_map.get(item.GetNetCode(), None)
    if item.GetNetCode() not in (0, -1, None, "") and target_net is None:
        return None
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(_transform_pt(item.GetStart(), ref_origin, target_origin, rotation, mirror_x))
    track.SetEnd(_transform_pt(item.GetEnd(), ref_origin, target_origin, rotation, mirror_x))
    track.SetWidth(item.GetWidth())
    track.SetLayer(item.GetLayer())
    if target_net:
        try:
            track.SetNet(target_net)
        except Exception:
            pass
    return track


def _clone_zone(board, item, ref_origin, target_origin, rotation, mirror_x, net_map):
    if not hasattr(pcbnew, "PCB_ZONE"):
        return None
    target_net = net_map.get(item.GetNetCode(), None)
    if item.GetNetCode() not in (0, -1, None, "") and target_net is None:
        return None
    zone = pcbnew.PCB_ZONE(board)

    def transform_poly(src_poly):
        new_poly = pcbnew.SHAPE_POLY_SET()
        for i in range(src_poly.OutlineCount()):
            chain = src_poly.COutline(i)
            pts = [
                _transform_pt(chain.CPoint(j), ref_origin, target_origin, rotation, mirror_x)
                for j in range(chain.PointCount())
            ]
            if i == 0:
                new_poly.NewOutline()
            else:
                new_poly.NewHole()
            for p in pts:
                new_poly.Append(int(p.x), int(p.y))
        return new_poly

    try:
        zone.SetOutline(transform_poly(item.Outline()))
    except Exception:
        return None

    try:
        zone.SetLayerSet(item.GetLayerSet())
    except Exception:
        try:
            zone.SetLayer(item.GetLayer())
        except Exception:
            pass
    if target_net:
        try:
            zone.SetNet(target_net)
        except Exception:
            pass
    try:
        zone.SetMinThickness(item.GetMinThickness())
    except Exception:
        pass
    try:
        zone.SetAssignedPriority(item.GetAssignedPriority())
    except Exception:
        pass
    return zone


def _clone_shape(board, item, ref_origin, target_origin, rotation, mirror_x, net_map):
    if not hasattr(pcbnew, "PCB_SHAPE"):
        return None
    shape = pcbnew.PCB_SHAPE(board)
    try:
        shape.SetShape(item.GetShape())
        shape.SetWidth(item.GetWidth())
        shape.SetLayer(item.GetLayer())

        def tp(pt):
            return _transform_pt(pt, ref_origin, target_origin, rotation, mirror_x)

        shape_type = item.GetShape()
        if shape_type in (pcbnew.SHAPE_T_SEGMENT, pcbnew.SHAPE_T_RECT):
            shape.SetStart(tp(item.GetStart()))
            shape.SetEnd(tp(item.GetEnd()))
        elif shape_type == pcbnew.SHAPE_T_ARC:
            shape.SetStart(tp(item.GetStart()))
            shape.SetMid(tp(item.GetMid()))
            shape.SetEnd(tp(item.GetEnd()))
        elif shape_type == pcbnew.SHAPE_T_CIRCLE:
            shape.SetCenter(tp(item.GetCenter()))
            shape.SetEnd(tp(item.GetEnd()))
        else:
            # Unsupported shape type: skip silently (best-effort).
            return None
        return shape
    except Exception:
        return None


def clone_and_transform_track(
    board, item, ref_origin, target_origin, rotation, net_map, mirror_x=False
):
    """Clone a track, via, or arc, transform its geometry and assign mapped net."""
    item_class = item.GetClass()

    # No crear cobre conectado a una red sin correspondencia válida: es
    # preferible omitirlo a introducir una pista eléctricamente incorrecta.
    if item.GetNetCode() not in (0, -1, None, "") and net_map.get(item.GetNetCode()) is None:
        return None

    if item_class == "PCB_VIA":
        return _clone_via(board, item, ref_origin, target_origin, rotation, mirror_x, net_map)
    elif item_class == "PCB_ARC":
        return _clone_arc(board, item, ref_origin, target_origin, rotation, mirror_x, net_map)
    else:
        return _clone_track(board, item, ref_origin, target_origin, rotation, mirror_x, net_map)


def plan_tracks(board, pairs, ref_tracks, ref_origin, target_origin, rotation, mirror_x=False, zones=None, shapes=None):
    """Clone reference copper + zones + shapes into one destination block.

    Returns a dict with ``cloned_tracks`` (list) and ``omitted_count`` (int)
    so the UI can report how many items were skipped for lack of a valid net.
    """
    net_map = core.build_net_map(pairs)
    cloned = []
    omitted = 0

    for item in ref_tracks:
        result = clone_and_transform_track(
            board, item, ref_origin, target_origin, rotation, net_map, mirror_x
        )
        if result is not None:
            cloned.append(result)
        else:
            omitted += 1

    for zone in (zones or []):
        result = _clone_zone(board, zone, ref_origin, target_origin, rotation, mirror_x, net_map)
        if result is not None:
            cloned.append(result)
        else:
            omitted += 1

    for shape in (shapes or []):
        result = _clone_shape(board, shape, ref_origin, target_origin, rotation, mirror_x, net_map)
        if result is not None:
            cloned.append(result)
        else:
            omitted += 1

    return {"cloned_tracks": cloned, "omitted_count": omitted}
