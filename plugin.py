import itertools
import math
import os
import re

import pcbnew
import wx


def footprint_name(footprint):
    """Return a stable library footprint name across KiCad API variants."""
    try:
        return str(footprint.GetFPID().GetLibItemName())
    except AttributeError:
        try:
            return str(footprint.GetFPID().GetLibId())
        except AttributeError:
            return ""


def footprint_key(footprint):
    """Properties that identify equivalent component roles in a block."""
    pad_count = len(list(footprint.Pads()))
    return (str(footprint.GetValue()), footprint_name(footprint), pad_count)


def position(footprint):
    point = footprint.GetPosition()
    return int(point[0]), int(point[1])


def set_position(footprint, x, y):
    try:
        footprint.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
    except TypeError:
        footprint.SetPosition(pcbnew.wxPoint(int(x), int(y)))


def rotate_point(dx, dy, degrees):
    """Rotate a relative vector (dx, dy) by degrees in KiCad coordinate space.

    In KiCad's screen coordinates (Y down), a CCW rotation (matching EDA_ANGLE)
    transforms (dx, dy) as:
        new_dx = dx * cos(a) + dy * sin(a)
        new_dy = -dx * sin(a) + dy * cos(a)
    """
    if degrees == 0:
        return dx, dy
    rad = math.radians(degrees)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    new_dx = dx * cos_a + dy * sin_a
    new_dy = -dx * sin_a + dy * cos_a
    return int(round(new_dx)), int(round(new_dy))


def create_pcb_group(board, items, group_name="Bloque_Alineado"):
    """Group footprints, tracks, and vias together as a native KiCad PCB_GROUP."""
    if not hasattr(pcbnew, "PCB_GROUP") or not items:
        return None
    try:
        group = pcbnew.PCB_GROUP(board)
        group.SetName(group_name)
        for item in items:
            group.AddItem(item)
        board.Add(group)
        return group
    except Exception:
        return None


def collect_reference_tracks(board, reference):
    """Find tracks, vias, and arcs associated with the reference block."""
    if not board or not reference:
        return []

    # 1. Recolectar códigos de red de los pads de la referencia
    ref_net_codes = set()
    for fp in reference:
        for pad in fp.Pads():
            net_id = pad_net_id(pad)
            if net_id not in (0, "", None, -1):
                ref_net_codes.add(net_id)

    # 2. Caja envolvente de los footprints de referencia con margen de 2.0 mm
    margin = 2000000
    xs = [position(fp)[0] for fp in reference]
    ys = [position(fp)[1] for fp in reference]
    min_x = min(xs) - margin
    max_x = max(xs) + margin
    min_y = min(ys) - margin
    max_y = max(ys) + margin

    def is_inside(x, y):
        return min_x <= x <= max_x and min_y <= y <= max_y

    collected = []
    seen_ids = set()

    for item in board.GetTracks():
        # La selección de una pista no debe saltarse el límite espacial: KiCad
        # puede conservar seleccionados objetos ajenos al bloque.
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
            if explicitly_selected or not ref_net_codes or net_code in ref_net_codes or net_code in (0, -1):
                if id(item) not in seen_ids:
                    collected.append(item)
                    seen_ids.add(id(item))

    return collected


def build_net_map(pairs):
    """Build a mapping from reference NetCode -> destination NETINFO_ITEM."""
    net_map = {}
    for ref_fp, target_fp in pairs:
        target_pads_by_num = {pad.GetNumber(): pad for pad in target_fp.Pads()}
        for ref_pad in ref_fp.Pads():
            ref_net_code = ref_pad.GetNetCode()
            pad_num = ref_pad.GetNumber()
            if pad_num in target_pads_by_num:
                target_pad = target_pads_by_num[pad_num]
                target_net = target_pad.GetNet()
                if target_net is not None and ref_net_code not in net_map:
                    net_map[ref_net_code] = target_net
    return net_map


def clone_and_transform_track(
    board, item, ref_origin, target_origin, rotation, net_map
):
    """Clone a track, via, or arc, transform its geometry and assign mapped net."""
    ax, ay = ref_origin
    dx, dy = target_origin

    item_class = item.GetClass()

    def transform_pt(pt):
        rel_x = pt.x - ax
        rel_y = pt.y - ay
        rot_x, rot_y = rotate_point(rel_x, rel_y, rotation)
        return pcbnew.VECTOR2I(int(dx + rot_x), int(dy + rot_y))

    target_net = net_map.get(item.GetNetCode(), None)
    # No crear cobre conectado a la red 0 cuando el destino no tiene una
    # correspondencia válida. Es preferible omitirlo a introducir una pista
    # eléctricamente incorrecta en la PCB.
    if item.GetNetCode() not in (0, -1, None, "") and target_net is None:
        return None

    if item_class == "PCB_VIA":
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(transform_pt(item.GetPosition()))
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

    elif item_class == "PCB_ARC":
        arc = pcbnew.PCB_ARC(board)
        arc.SetStart(transform_pt(item.GetStart()))
        arc.SetMid(transform_pt(item.GetMid()))
        arc.SetEnd(transform_pt(item.GetEnd()))
        arc.SetWidth(item.GetWidth())
        arc.SetLayer(item.GetLayer())
        if target_net:
            try:
                arc.SetNet(target_net)
            except Exception:
                pass
        return arc

    else:  # Default PCB_TRACK
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(transform_pt(item.GetStart()))
        track.SetEnd(transform_pt(item.GetEnd()))
        track.SetWidth(item.GetWidth())
        track.SetLayer(item.GetLayer())
        if target_net:
            try:
                track.SetNet(target_net)
            except Exception:
                pass
        return track


def set_orientation_with_rotation(footprint, source, rotation_degrees=0):
    """Copy source orientation and add block rotation."""
    base_orientation = source.GetOrientation()
    if rotation_degrees == 0:
        footprint.SetOrientation(base_orientation)
        return
    try:
        # KiCad 7+ EDA_ANGLE
        add_angle = pcbnew.EDA_ANGLE(float(rotation_degrees), pcbnew.DEGREES_T)
        footprint.SetOrientation(base_orientation + add_angle)
    except (AttributeError, TypeError):
        try:
            footprint.SetOrientation(base_orientation + int(rotation_degrees * 10))
        except (TypeError, ValueError):
            try:
                footprint.SetOrientation(base_orientation + float(rotation_degrees))
            except Exception:
                footprint.SetOrientation(base_orientation)


def set_orientation(footprint, source):
    """Copy KiCad's native angle object without modification."""
    footprint.SetOrientation(source.GetOrientation())


def select_footprints(board):
    return [fp for fp in board.GetFootprints() if fp.IsSelected()]


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


def pad_net_id(pad):
    """Get a net identifier without relying on the net name."""
    try:
        return int(pad.GetNetCode())
    except AttributeError:
        return str(pad.GetNetname())


def pad_net_name(pad):
    """Get pad net name string safely."""
    try:
        return str(pad.GetNetname())
    except Exception:
        return ""


def connectivity_signature(footprint, block):
    """Describe this footprint's connections to other footprints in its block.

    Net names and net codes are intentionally omitted because repeated schematic
    blocks normally use different nets. External connections are represented by
    an empty peer list.
    """
    peers_by_pad = []
    for pad in footprint.Pads():
        net_id = pad_net_id(pad)
        peers = []
        if net_id not in (0, "", None):
            for other in block:
                if other is footprint:
                    continue
                for other_pad in other.Pads():
                    if pad_net_id(other_pad) == net_id:
                        peers.append(
                            (
                                footprint_key(other),
                                str(other_pad.GetNumber()),
                            )
                        )
        peers_by_pad.append(
            (
                str(pad.GetNumber()),
                tuple(sorted(peers)) if peers else ("external",),
            )
        )
    return tuple(sorted(peers_by_pad))


def centroid(footprints):
    xs = [position(fp)[0] for fp in footprints]
    ys = [position(fp)[1] for fp in footprints]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def ordered_components(footprints, center, block):
    """Group equivalent parts and order duplicates by circuit role."""
    groups = {}
    for footprint in footprints:
        groups.setdefault(footprint_key(footprint), []).append(footprint)

    result = {}
    for key, group in groups.items():
        result[key] = sorted(
            group,
            key=lambda fp: (
                connectivity_signature(fp, block),
                position(fp)[1] - center[1],
                position(fp)[0] - center[0],
                fp.GetReference(),
            ),
        )
    return result


def match_group_by_geometry(
    ref_parts, target_parts, ref_origin, target_origin, rotation
):
    """Match equivalent parts as a group, preserving their block geometry."""
    if len(ref_parts) != len(target_parts):
        return []

    def expected_position(ref_fp):
        rx, ry = position(ref_fp)
        rel_x, rel_y = rotate_point(
            rx - ref_origin[0], ry - ref_origin[1], rotation
        )
        return target_origin[0] + rel_x, target_origin[1] + rel_y

    expected = [expected_position(fp) for fp in ref_parts]
    actual = [position(fp) for fp in target_parts]

    def cost(ref_index, target_index):
        ex, ey = expected[ref_index]
        ax, ay = actual[target_index]
        return (ex - ax) ** 2 + (ey - ay) ** 2

    # Most groups are small. Exhaustive assignment avoids the independent
    # sorting bug (R1-D2 / R2-D1) while still handling unusually large groups.
    if len(ref_parts) <= 8:
        best_order = None
        best_cost = None
        for order in itertools.permutations(range(len(target_parts))):
            current_cost = sum(
                cost(ref_index, target_index)
                for ref_index, target_index in enumerate(order)
            )
            if best_cost is None or current_cost < best_cost:
                best_cost = current_cost
                best_order = order
        return [
            (ref_fp, target_parts[target_index])
            for ref_fp, target_index in zip(ref_parts, best_order)
        ]

    remaining = set(range(len(target_parts)))
    pairs = []
    for ref_index, ref_fp in enumerate(ref_parts):
        target_index = min(remaining, key=lambda idx: cost(ref_index, idx))
        remaining.remove(target_index)
        pairs.append((ref_fp, target_parts[target_index]))
    return pairs


def plan_block(
    reference,
    target,
    anchor_ref_name=None,
    rotation=0,
    ref_tracks=None,
    board=None,
):
    ref_center = centroid(reference)
    target_center = centroid(target)
    ref_groups = ordered_components(reference, ref_center, reference)
    target_groups = ordered_components(target, target_center, target)

    if set(ref_groups) != set(target_groups):
        return False, "Los componentes o footprints no coinciden."

    for key, ref_parts in ref_groups.items():
        target_parts = target_groups[key]
        if len(ref_parts) != len(target_parts):
            return False, "La cantidad de componentes equivalentes no coincide."

    # Start with centroids. For an explicit anchor, the first matching pass
    # identifies its target counterpart before rematching with that anchor.
    ref_origin = ref_center
    target_origin = target_center

    # Match equivalent components using the whole block geometry, not by
    # independently sorting each footprint type.
    pairs = []
    ref_to_target = {}
    for key, ref_parts in ref_groups.items():
        group_pairs = match_group_by_geometry(
            ref_parts,
            target_groups[key],
            ref_origin,
            target_origin,
            rotation,
        )
        for ref_fp, target_fp in group_pairs:
            pairs.append((ref_fp, target_fp))
            ref_to_target[ref_fp.GetReference()] = target_fp

    # An explicit anchor needs the target selected by the same geometric
    # matching used for the rest of the block.
    if anchor_ref_name and anchor_ref_name not in (
        "<Centroide>",
        "Centroide del bloque",
    ):
        ref_anchor_fp = next(
            (fp for fp in reference if fp.GetReference() == anchor_ref_name),
            None,
        )
        target_anchor_fp = ref_to_target.get(anchor_ref_name)
        if ref_anchor_fp and target_anchor_fp:
            ref_origin = position(ref_anchor_fp)
            target_origin = position(target_anchor_fp)
            rematched_pairs = []
            ref_to_target = {}
            for key, ref_parts in ref_groups.items():
                rematched_pairs.extend(
                    match_group_by_geometry(
                        ref_parts,
                        target_groups[key],
                        ref_origin,
                        target_origin,
                        rotation,
                    )
                )
            pairs = rematched_pairs
            ref_to_target = {
                ref_fp.GetReference(): target_fp
                for ref_fp, target_fp in pairs
            }

    fp_plan = []
    for ref_fp, target_fp in pairs:
        ref_x, ref_y = position(ref_fp)
        dx = ref_x - ref_origin[0]
        dy = ref_y - ref_origin[1]
        rot_dx, rot_dy = rotate_point(dx, dy, rotation)
        new_x = target_origin[0] + rot_dx
        new_y = target_origin[1] + rot_dy
        if target_fp.IsLocked():
            return False, "El footprint {} está bloqueado.".format(
                target_fp.GetReference()
            )
        fp_plan.append((target_fp, new_x, new_y, ref_fp, rotation))

    cloned_tracks = []
    if ref_tracks and board:
        net_map = build_net_map(pairs)
        for item in ref_tracks:
            cloned = clone_and_transform_track(
                board, item, ref_origin, target_origin, rotation, net_map
            )
            if cloned:
                cloned_tracks.append(cloned)

    return True, {
        "footprint_plan": fp_plan,
        "cloned_tracks": cloned_tracks,
        "target_footprints": target,
    }


def apply_plan(plan_result):
    if isinstance(plan_result, dict):
        fp_plan = plan_result.get("footprint_plan", [])
    else:
        fp_plan = plan_result
    for target_fp, x, y, source_fp, rotation in fp_plan:
        set_position(target_fp, x, y)
        set_orientation_with_rotation(target_fp, source_fp, rotation)


def validate_block(reference, target):
    """Validate a destination without changing the board."""
    errors = []
    if any(
        target_fp.GetReference() == ref_fp.GetReference()
        for target_fp in target
        for ref_fp in reference
    ):
        errors.append("incluye footprints del bloque de referencia")

    ref_groups = ordered_components(reference, centroid(reference), reference)
    target_groups = ordered_components(target, centroid(target), target)
    if set(ref_groups) != set(target_groups):
        errors.append("sus componentes o footprints no coinciden")
    else:
        for key, ref_parts in ref_groups.items():
            if len(ref_parts) != len(target_groups[key]):
                errors.append(
                    "la cantidad de componentes equivalentes no coincide"
                )
                break

    locked = [fp.GetReference() for fp in target if fp.IsLocked()]
    if locked:
        errors.append(
            "tiene footprints bloqueados: {}".format(", ".join(locked))
        )

    matched = min(len(reference), len(target)) if not errors else 0
    return errors, matched


def block_diameter(footprints):
    """Return the maximum distance between footprint origins in nanometres."""
    if len(footprints) < 2:
        return 0
    points = [position(fp) for fp in footprints]
    return max(
        math.hypot(x1 - x2, y1 - y2)
        for x1, y1 in points
        for x2, y2 in points
    )


def within_block_area(fp, seed, max_diameter):
    """Reject components that cannot belong to the same physical block."""
    sx, sy = position(seed)
    x, y = position(fp)
    # Margin for footprint body/pad extents and small placement differences.
    return math.hypot(x - sx, y - sy) <= max_diameter + 3000000


def diagnose_block(reference, target):
    """Provide a comprehensive diagnostic breakdown between reference and target."""
    ref_counts = {}
    for fp in reference:
        k = footprint_key(fp)
        ref_counts.setdefault(k, []).append(fp)

    target_counts = {}
    for fp in target:
        k = footprint_key(fp)
        target_counts.setdefault(k, []).append(fp)

    missing = []
    extra = []

    for k, ref_fps in ref_counts.items():
        val, fp_name, pads = k
        target_fps = target_counts.get(k, [])
        diff = len(ref_fps) - len(target_fps)
        if diff > 0:
            example_refs = ", ".join(fp.GetReference() for fp in ref_fps[:3])
            missing.append(
                "{}x {} (Valor: '{}', {} pads) [Ej: {}]".format(
                    diff, fp_name or "Huella", val, pads, example_refs
                )
            )

    for k, target_fps in target_counts.items():
        val, fp_name, pads = k
        ref_fps = ref_counts.get(k, [])
        diff = len(target_fps) - len(ref_fps)
        if diff > 0:
            extra_refs = ", ".join(
                fp.GetReference() for fp in target_fps[-diff:]
            )
            extra.append(
                "{}x {} (Valor: '{}', {} pads) [Detectados: {}]".format(
                    diff, fp_name or "Huella", val, pads, extra_refs
                )
            )

    locked = [fp.GetReference() for fp in target if fp.IsLocked()]
    ref_set = set(fp.GetReference() for fp in reference)
    overlap = [
        fp.GetReference() for fp in target if fp.GetReference() in ref_set
    ]

    errors, matched = validate_block(reference, target)
    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "matched_count": matched,
        "expected_count": len(reference),
        "found_count": len(target),
        "missing": missing,
        "extra": extra,
        "locked": locked,
        "overlap": overlap,
    }


def extract_ref_number(ref_str):
    """Extract the integer numerical part from a reference designator."""
    m = re.search(r"\d+", ref_str)
    return int(m.group(0)) if m else 0


def extract_named_references_from_nets(fp):
    """Extract any component reference designators explicitly named in net strings."""
    named = set()
    for p in fp.Pads():
        try:
            net_name = str(p.GetNetname())
        except Exception:
            continue
        for m in re.findall(r"Net-\(([A-Za-z0-9_]+)[-_]", net_name):
            named.add(m)
    return named


def auto_discover_blocks(board, reference, existing_targets):
    """Automatically find and return valid destination blocks across the PCB without mixing."""
    if not reference:
        return []

    used_refs = set(fp.GetReference() for fp in reference)
    for entry in existing_targets:
        for fp in entry["footprints"]:
            used_refs.add(fp.GetReference())

    all_board_fps = [
        fp
        for fp in board.GetFootprints()
        if fp.GetReference() not in used_refs
    ]
    if not all_board_fps:
        return []

    ref_counts = {}
    for fp in reference:
        k = footprint_key(fp)
        ref_counts[k] = ref_counts.get(k, 0) + 1
    ref_diameter = block_diameter(reference)

    discovered_blocks = []
    discovered_refs = set()

    # Precomputar redes globales / de alimentación
    pad_counts_by_net = {}
    net_names_by_id = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            nid = pad_net_id(pad)
            if nid not in (0, "", None, -1):
                pad_counts_by_net[nid] = pad_counts_by_net.get(nid, 0) + 1
                if nid not in net_names_by_id:
                    net_names_by_id[nid] = pad_net_name(pad)

    def is_global_net(net_id):
        if net_id in (0, "", None, -1):
            return True
        if pad_counts_by_net.get(net_id, 0) > max(len(reference) + 2, 4):
            return True
        name = net_names_by_id.get(net_id, "").upper().strip()
        pwr_keys = [
            "GND", "VCC", "VDD", "VSS", "+3V3", "+5V", "+12V", "-12V",
            "3V3", "5V", "GNDA", "AGND", "DGND", "POWER", "PWR", "ADC1", "ADC2"
        ]
        return any(
            k == name
            or name.startswith("+")
            or name.endswith("GND")
            or name.startswith("GND")
            for k in pwr_keys
        )

    # -------------------------------------------------------------------------
    # Estrategia 1: Hojas jerárquicas (Sheet Path & Sheet Name)
    # -------------------------------------------------------------------------
    sheet_groups = {}
    for fp in all_board_fps:
        path_str = ""
        try:
            path_str = fp.GetPath().AsString()
        except Exception:
            pass

        sheet_key = ""
        if path_str and "/" in path_str and len(path_str.split("/")) > 2:
            sheet_key = path_str.rsplit("/", 1)[0]
        if not sheet_key:
            sheet_file = fp.GetSheetfile()
            sheet_name = fp.GetSheetname()
            if sheet_file or sheet_name:
                sheet_key = f"{sheet_file}::{sheet_name}"

        if sheet_key:
            sheet_groups.setdefault(sheet_key, []).append(fp)

    for sheet_key, fps in sheet_groups.items():
        if len(fps) == len(reference):
            errors, matched = validate_block(reference, fps)
            if not errors and matched == len(reference):
                discovered_blocks.append(fps)
                for fp in fps:
                    discovered_refs.add(fp.GetReference())

    # -------------------------------------------------------------------------
    # Estrategia 2: Sufijos de Designadores (ej. _A -> _B, _C)
    # -------------------------------------------------------------------------
    remaining_fps = [
        fp for fp in all_board_fps if fp.GetReference() not in discovered_refs
    ]
    fps_by_ref = {fp.GetReference(): fp for fp in remaining_fps}
    ref_names = [fp.GetReference() for fp in reference]

    parsed = []
    for r in ref_names:
        m = re.match(r"^([A-Za-z]+)(\d+)(.*)$", r)
        if m:
            parsed.append((m.group(1), int(m.group(2)), m.group(3)))

    if len(parsed) == len(ref_names):
        suffixes_in_ref = {s for p, n, s in parsed if s}
        if len(suffixes_in_ref) == 1:
            ref_sfx = list(suffixes_in_ref)[0]
            all_board_suffixes = set()
            for r in fps_by_ref:
                m = re.match(r"^([A-Za-z]+)(\d+)(.*)$", r)
                if m and m.group(3) and m.group(3) != ref_sfx:
                    all_board_suffixes.add(m.group(3))

            for sfx in sorted(all_board_suffixes):
                cand_refs = [f"{p}{n}{sfx}" for p, n, s in parsed]
                if all(
                    r in fps_by_ref and r not in discovered_refs
                    for r in cand_refs
                ):
                    cand_block = [fps_by_ref[r] for r in cand_refs]
                    errors, matched = validate_block(reference, cand_block)
                    if not errors and matched == len(reference):
                        discovered_blocks.append(cand_block)
                        for r in cand_refs:
                            discovered_refs.add(r)

    # -------------------------------------------------------------------------
    # Estrategia 3: Crecimiento por Grafo Interno, Nombres de Red y Proximidad
    # -------------------------------------------------------------------------
    remaining_fps = [
        fp for fp in all_board_fps if fp.GetReference() not in discovered_refs
    ]

    # Seleccionar como componente semilla el que tenga mayor conectividad interna (ej. IC / Optoacoplador)
    def seed_score(fp):
        named_cnt = len(extract_named_references_from_nets(fp))
        pads_cnt = len([p for p in fp.Pads() if pad_net_id(p) not in (0, "", None, -1)])
        return (named_cnt, pads_cnt)

    best_ref_seed = max(reference, key=seed_score)
    seed_key = footprint_key(best_ref_seed)
    seed_x, seed_y = position(best_ref_seed)
    expected_distances = {}
    for ref_fp in reference:
        x, y = position(ref_fp)
        expected_distances.setdefault(footprint_key(ref_fp), []).append(
            math.hypot(x - seed_x, y - seed_y)
        )
    seed_fps = [
        fp for fp in remaining_fps if footprint_key(fp) == seed_key
    ]

    seed_fps.sort(key=lambda fp: extract_ref_number(fp.GetReference()))

    for seed in seed_fps:
        if seed.GetReference() in discovered_refs:
            continue

        cluster = [seed]
        cluster_refs = {seed.GetReference()}
        queue = [seed]

        # 3A. BFS por señales internas y por nombres de componentes en redes
        while queue and len(cluster) < len(reference):
            curr = queue.pop(0)
            curr_internal_nets = set()
            for pad in curr.Pads():
                nid = pad_net_id(pad)
                if not is_global_net(nid):
                    curr_internal_nets.add(nid)

            named_in_curr = extract_named_references_from_nets(curr)

            for neighbor in remaining_fps:
                n_ref = neighbor.GetReference()
                if n_ref not in cluster_refs and n_ref not in discovered_refs:
                    shares = any(
                        pad_net_id(p) in curr_internal_nets
                        for p in neighbor.Pads()
                        if not is_global_net(pad_net_id(p))
                    )
                    is_named = (n_ref in named_in_curr) or (
                        curr.GetReference()
                        in extract_named_references_from_nets(neighbor)
                    )

                    # Una conexión interna inequívoca es más fiable que la
                    # distancia: el bloque destino puede estar más separado o
                    # haber sido colocado de forma distinta al de referencia.
                    # La distancia sigue limitando componentes añadidos solo
                    # por heurística de proximidad.
                    if not (shares or is_named) and not within_block_area(
                        neighbor, seed, ref_diameter
                    ):
                        continue
                    if shares or is_named:
                        n_key = footprint_key(neighbor)
                        curr_k_count = sum(
                            1 for fp in cluster if footprint_key(fp) == n_key
                        )
                        if curr_k_count < ref_counts.get(n_key, 0):
                            cluster.append(neighbor)
                            cluster_refs.add(n_ref)
                            queue.append(neighbor)

        # 3B. Completar componentes asociados (redes cruzadas + proximidad ponderada)
        needed_keys = ref_counts.copy()
        for fp in cluster:
            needed_keys[footprint_key(fp)] -= 1
            if needed_keys[footprint_key(fp)] == 0:
                del needed_keys[footprint_key(fp)]

        if needed_keys:
            cx = sum(position(fp)[0] for fp in cluster) // len(cluster)
            cy = sum(position(fp)[1] for fp in cluster) // len(cluster)
            avg_num = (
                sum(extract_ref_number(f.GetReference()) for f in cluster)
                / len(cluster)
            )

            for k, count in list(needed_keys.items()):
                available = [
                    fp
                    for fp in remaining_fps
                    if fp.GetReference() not in cluster_refs
                    and fp.GetReference() not in discovered_refs
                    and footprint_key(fp) == k
                    and within_block_area(fp, seed, ref_diameter)
                ]

                def score_part(fp):
                    fp_x, fp_y = position(fp)
                    dist_sq = (fp_x - cx) ** 2 + (fp_y - cy) ** 2
                    actual_distance = math.hypot(
                        fp_x - position(seed)[0], fp_y - position(seed)[1]
                    )
                    geometry_error = min(
                        abs(actual_distance - expected)
                        for expected in expected_distances.get(k, [0])
                    )
                    num_diff = abs(
                        extract_ref_number(fp.GetReference()) - avg_num
                    )
                    named_in_fp = extract_named_references_from_nets(fp)
                    is_named = (
                        -1e12
                        if any(
                            c.GetReference() in named_in_fp for c in cluster
                        )
                        else 0
                    )
                    return (is_named, geometry_error, dist_sq, num_diff)

                available.sort(key=score_part)
                for best_fp in available[:count]:
                    cluster.append(best_fp)
                    cluster_refs.add(best_fp.GetReference())

        if len(cluster) == len(reference):
            errors, matched = validate_block(reference, cluster)
            if not errors and matched == len(reference):
                discovered_blocks.append(cluster)
                for fp in cluster:
                    discovered_refs.add(fp.GetReference())

    discovered_blocks.sort(
        key=lambda blk: min(extract_ref_number(fp.GetReference()) for fp in blk)
    )
    return discovered_blocks


class ErrorDetailsDialog(wx.Dialog):
    """Modal dialog displaying formatted diagnostic breakdown of a destination block."""

    def __init__(self, parent, target_idx, diagnosis):
        super().__init__(
            parent,
            title="Diagnóstico de Error - Destino {}".format(target_idx),
            size=(640, 480),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetMinSize((520, 360))

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        header_pnl = wx.Panel(self)
        header_sizer = wx.BoxSizer(wx.VERTICAL)

        if diagnosis["is_valid"]:
            status_txt = wx.StaticText(
                header_pnl,
                label="✓ El bloque es válido y compatible con la referencia.",
            )
            status_txt.SetForegroundColour(wx.Colour(0, 140, 0))
        else:
            status_txt = wx.StaticText(
                header_pnl,
                label="✕ Se detectaron discrepancias en el Destino {}:".format(
                    target_idx
                ),
            )
            status_txt.SetForegroundColour(wx.Colour(200, 0, 0))
        status_txt.SetFont(status_txt.GetFont().Bold())

        summary_txt = wx.StaticText(
            header_pnl,
            label="Componentes esperados: {} | Encontrados en destino: {}".format(
                diagnosis["expected_count"], diagnosis["found_count"]
            ),
        )
        header_sizer.Add(status_txt, 0, wx.ALL, 4)
        header_sizer.Add(summary_txt, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        header_pnl.SetSizer(header_sizer)
        main_sizer.Add(header_pnl, 0, wx.EXPAND | wx.ALL, 8)

        report_lines = []
        if diagnosis["missing"]:
            report_lines.append("■ COMPONENTES FALTANTES EN EL DESTINO:")
            for item in diagnosis["missing"]:
                report_lines.append("   - {}".format(item))
            report_lines.append("")

        if diagnosis["extra"]:
            report_lines.append("■ COMPONENTES SOBRANTES O NO ESPERADOS:")
            for item in diagnosis["extra"]:
                report_lines.append("   + {}".format(item))
            report_lines.append("")

        if diagnosis["locked"]:
            report_lines.append(
                "■ FOOTPRINTS BLOQUEADOS EN PCB (Desbloquear para mover):"
            )
            report_lines.append("   ⚠ {}".format(", ".join(diagnosis["locked"])))
            report_lines.append("")

        if diagnosis["overlap"]:
            report_lines.append(
                "■ FOOTPRINTS QUE PERTENECEN AL BLOQUE DE REFERENCIA:"
            )
            report_lines.append(
                "   ✕ {}".format(", ".join(diagnosis["overlap"]))
            )
            report_lines.append("")

        if not report_lines:
            report_lines.append("No se detectaron problemas en este bloque.")

        text_ctrl = wx.TextCtrl(
            self,
            value="\n".join(report_lines),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SUNKEN,
        )
        text_ctrl.SetFont(
            wx.Font(
                9,
                wx.FONTFAMILY_TELETYPE,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
        )
        main_sizer.Add(
            text_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10
        )

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_close = wx.Button(self, wx.ID_CANCEL, label="Cerrar")
        btn_close.Bind(wx.EVT_BUTTON, lambda _evt: self.EndModal(wx.ID_CANCEL))
        btn_sizer.Add(btn_close, 0, wx.ALL, 6)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 6)

        self.SetSizer(main_sizer)


def generate_diagnostic_report(board, reference, existing_targets, discovered_blocks):
    """Generate a detailed diagnostic log of reference, board nets, and detected blocks."""
    lines = []
    lines.append("=== BLOCK ALIGNER DIAGNOSTIC LOG ===")
    lines.append(f"Total footprints on board: {len(list(board.GetFootprints()))}")
    lines.append("")

    # 1. Reference Block
    lines.append(f"--- REFERENCE BLOCK ({len(reference)} footprints) ---")
    for fp in sorted(reference, key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        val = fp.GetValue()
        fp_name = footprint_name(fp)
        sheet = (
            f"{fp.GetSheetfile()}::{fp.GetSheetname()}"
            if (fp.GetSheetfile() or fp.GetSheetname())
            else ""
        )
        try:
            path_str = fp.GetPath().AsString()
        except Exception:
            path_str = ""
        pads_info = []
        for pad in fp.Pads():
            p_num = str(pad.GetNumber())
            net_name = str(pad.GetNetname())
            net_code = pad.GetNetCode()
            pads_info.append(f"Pin {p_num}: Net '{net_name}' (ID {net_code})")
        lines.append(
            f"  [{ref}] Val: '{val}' | FP: '{fp_name}' | Sheet: '{sheet}' | Path: '{path_str}'"
        )
        lines.append(f"       Pads: {', '.join(pads_info)}")
    lines.append("")

    # 2. Existing Targets
    if existing_targets:
        lines.append(
            f"--- EXISTING TARGETS ({len(existing_targets)} targets) ---"
        )
        for idx, entry in enumerate(existing_targets, 1):
            fps = entry["footprints"]
            ref_names = [f.GetReference() for f in fps]
            lines.append(
                f"  Target {idx} ({len(fps)} fps, rot {entry.get('rotation', 0)}°): {', '.join(ref_names)}"
            )
        lines.append("")

    # 3. Discovered Blocks
    lines.append(
        f"--- DISCOVERED BLOCKS ({len(discovered_blocks)} blocks) ---"
    )
    for idx, block in enumerate(discovered_blocks, 1):
        lines.append(f"  Discovered Block {idx} ({len(block)} footprints):")
        for fp in sorted(block, key=lambda f: f.GetReference()):
            ref = fp.GetReference()
            val = fp.GetValue()
            fp_name = footprint_name(fp)
            pads_info = []
            for pad in fp.Pads():
                p_num = str(pad.GetNumber())
                net_name = str(pad.GetNetname())
                net_code = pad.GetNetCode()
                pads_info.append(
                    f"Pin {p_num}: Net '{net_name}' (ID {net_code})"
                )
            lines.append(f"    [{ref}] Val: '{val}' | FP: '{fp_name}'")
            lines.append(f"         Pads: {', '.join(pads_info)}")
    lines.append("")

    # 4. Remaining Footprints on Board with matching component types
    ref_keys = set(footprint_key(fp) for fp in reference)
    used_refs = set(fp.GetReference() for fp in reference)
    for entry in existing_targets:
        for fp in entry["footprints"]:
            used_refs.add(fp.GetReference())
    for block in discovered_blocks:
        for fp in block:
            used_refs.add(fp.GetReference())

    remaining_matching = [
        fp
        for fp in board.GetFootprints()
        if fp.GetReference() not in used_refs
        and footprint_key(fp) in ref_keys
    ]
    if remaining_matching:
        lines.append(
            f"--- OTHER MATCHING FOOTPRINTS ON BOARD ({len(remaining_matching)} footprints) ---"
        )
        for fp in sorted(remaining_matching, key=lambda f: f.GetReference()):
            ref = fp.GetReference()
            val = fp.GetValue()
            pads_info = [
                f"Pin {pad.GetNumber()}: Net '{pad.GetNetname()}'"
                for pad in fp.Pads()
            ]
            lines.append(
                f"  [{ref}] Val: '{val}' | Pads: {', '.join(pads_info)}"
            )
    lines.append("")
    lines.append("=== END OF DIAGNOSTIC LOG ===")

    return "\n".join(lines)


class DiagnosticLogDialog(wx.Dialog):
    """Modal dialog displaying full diagnostic breakdown and copy button."""

    def __init__(self, parent, report_text):
        super().__init__(
            parent,
            title="Diagnóstico de Auto-Detección y Componentes",
            size=(760, 540),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.report_text = report_text
        self._init_ui()

    def _init_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        info_lbl = wx.StaticText(
            self,
            label="Informe de componentes de referencia, conexiones de redes y bloques encontrados.\n"
            "Puedes copiar este informe o se guardará automáticamente en 'debug_log.txt'.",
        )
        main_sizer.Add(info_lbl, 0, wx.ALL, 10)

        self.text_ctrl = wx.TextCtrl(
            self,
            value=self.report_text,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SUNKEN,
        )
        self.text_ctrl.SetFont(
            wx.Font(
                9,
                wx.FONTFAMILY_TELETYPE,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
        )
        main_sizer.Add(
            self.text_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10
        )

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_copy = wx.Button(self, label="📋 Copiar al Portapapeles")
        btn_copy.Bind(wx.EVT_BUTTON, self._on_copy)
        btn_close = wx.Button(self, wx.ID_CANCEL, label="Cerrar")
        btn_close.Bind(wx.EVT_BUTTON, lambda _evt: self.EndModal(wx.ID_CANCEL))

        btn_sizer.Add(btn_copy, 0, wx.RIGHT, 8)
        btn_sizer.Add(btn_close, 0)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 10)

        self.SetSizer(main_sizer)

    def _on_copy(self, _event):
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.report_text))
            wx.TheClipboard.Close()
            wx.MessageBox(
                "¡Informe copiado al portapapeles con éxito!",
                "Diagnóstico",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )


def format_references(footprints, max_display=8):
    """Format a readable list of footprint reference designators."""
    if not footprints:
        return "Ninguno"
    refs = sorted(fp.GetReference() for fp in footprints)
    if len(refs) <= max_display:
        return ", ".join(refs)
    return ", ".join(refs[:max_display]) + f", ... (+{len(refs) - max_display} más)"


class BlockAlignerDialog(wx.Dialog):
    def __init__(self, parent, board):
        super().__init__(
            parent,
            title="Block Aligner",
            size=(920, 620),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetMinSize((740, 520))
        self.board = board
        self.reference = []
        self.targets = []

        self._init_ui()

    def _init_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---------------------------------------------------------------------
        # 1. Sección: Bloque de Referencia
        # ---------------------------------------------------------------------
        ref_box = wx.StaticBox(self, label=" 1. Bloque de Referencia ")
        ref_sizer = wx.StaticBoxSizer(ref_box, wx.VERTICAL)

        ref_top_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_capture = wx.Button(self, label="Capturar referencia")
        self.btn_view_ref = wx.Button(self, label="Ver en PCB")
        self.btn_capture.Bind(wx.EVT_BUTTON, self.capture_reference)
        self.btn_view_ref.Bind(wx.EVT_BUTTON, self.view_reference_in_pcb)

        self.ref_status = wx.StaticText(
            self, label="Ningún bloque de referencia capturado."
        )
        bold_font = self.ref_status.GetFont().Bold()
        self.ref_status.SetFont(bold_font)

        ref_top_row.Add(self.btn_capture, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        ref_top_row.Add(self.btn_view_ref, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        ref_top_row.Add(self.ref_status, 1, wx.ALIGN_CENTER_VERTICAL)

        self.ref_details = wx.StaticText(
            self,
            label="Selecciona los footprints en PCB Editor y haz clic en 'Capturar referencia'.",
        )
        self.ref_details.SetForegroundColour(wx.Colour(120, 120, 120))

        # Fila de Punto de Anclaje
        anchor_row = wx.BoxSizer(wx.HORIZONTAL)
        anchor_lbl = wx.StaticText(self, label="Punto de anclaje (origen):")
        self.anchor_choice = wx.Choice(self, choices=["Centroide del bloque"])
        self.anchor_choice.SetSelection(0)
        self.anchor_choice.Bind(wx.EVT_CHOICE, self._on_anchor_changed)

        anchor_row.Add(anchor_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        anchor_row.Add(self.anchor_choice, 0, wx.ALIGN_CENTER_VERTICAL)

        ref_sizer.Add(ref_top_row, 0, wx.EXPAND | wx.ALL, 6)
        ref_sizer.Add(
            self.ref_details, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4
        )
        ref_sizer.Add(
            anchor_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6
        )
        main_sizer.Add(ref_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # ---------------------------------------------------------------------
        # 2. Sección: Bloques Destino
        # ---------------------------------------------------------------------
        target_box = wx.StaticBox(self, label=" 2. Bloques Destino ")
        target_sizer = wx.StaticBoxSizer(target_box, wx.VERTICAL)

        # Tabla estructurada de destinos
        self.target_list = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
        )
        self.target_list.InsertColumn(0, "#", wx.LIST_FORMAT_CENTER, 40)
        self.target_list.InsertColumn(
            1, "Footprints / Componentes", wx.LIST_FORMAT_LEFT, 320
        )
        self.target_list.InsertColumn(2, "Cantidad", wx.LIST_FORMAT_CENTER, 75)
        self.target_list.InsertColumn(3, "Rotación", wx.LIST_FORMAT_CENTER, 75)
        self.target_list.InsertColumn(
            4, "Estado de Validación", wx.LIST_FORMAT_LEFT, 240
        )

        self.target_list.Bind(
            wx.EVT_LIST_ITEM_SELECTED, self._on_target_selection_change
        )
        self.target_list.Bind(
            wx.EVT_LIST_ITEM_DESELECTED, self._on_target_selection_change
        )
        self.target_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_target_activated)
        self.target_list.Bind(wx.EVT_KEY_DOWN, self._on_key_down)

        # Botones de gestión de destinos y selector de rotación
        target_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_add_target = wx.Button(self, label="Añadir selección")
        self.btn_auto_discover = wx.Button(self, label="Auto-detectar")
        self.btn_remove_target = wx.Button(self, label="Eliminar")
        self.btn_view_target = wx.Button(self, label="Ver en PCB")
        self.btn_inspect_error = wx.Button(self, label="Detalles error")
        self.btn_export_log = wx.Button(self, label="📋 Diagnóstico")
        self.btn_clear = wx.Button(self, label="Limpiar todo")

        self.btn_add_target.Bind(wx.EVT_BUTTON, self.add_target)
        self.btn_auto_discover.Bind(wx.EVT_BUTTON, self.auto_discover)
        self.btn_remove_target.Bind(wx.EVT_BUTTON, self.remove_target)
        self.btn_view_target.Bind(wx.EVT_BUTTON, self.view_target_in_pcb)
        self.btn_inspect_error.Bind(wx.EVT_BUTTON, self.show_error_details)
        self.btn_export_log.Bind(wx.EVT_BUTTON, self.export_diagnostic_log)
        self.btn_clear.Bind(wx.EVT_BUTTON, self.clear)

        target_btn_row.Add(self.btn_add_target, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_auto_discover, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_remove_target, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_view_target, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_inspect_error, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_export_log, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_clear, 0, wx.RIGHT, 12)

        # Selector de Rotación y botones de giro rápido
        rot_lbl = wx.StaticText(self, label="Rotación:")
        self.btn_rot_ccw = wx.Button(self, label="↺ -90°", size=(62, -1))
        self.btn_rot_cw = wx.Button(self, label="↻ +90°", size=(62, -1))
        self.rotation_choice = wx.Choice(
            self, choices=["0°", "90°", "180°", "270°"]
        )
        self.rotation_choice.SetSelection(0)
        self.rotation_choice.Bind(wx.EVT_CHOICE, self._on_rotation_changed)
        self.btn_rot_ccw.Bind(wx.EVT_BUTTON, self._on_rotate_ccw)
        self.btn_rot_cw.Bind(wx.EVT_BUTTON, self._on_rotate_cw)

        target_btn_row.Add(rot_lbl, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 4)
        target_btn_row.Add(self.btn_rot_ccw, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 2)
        target_btn_row.Add(self.btn_rot_cw, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 4)
        target_btn_row.Add(self.rotation_choice, 0, wx.ALIGN_CENTER_VERTICAL)

        target_sizer.Add(self.target_list, 1, wx.EXPAND | wx.ALL, 6)
        target_sizer.Add(
            target_btn_row, 0, wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6
        )
        main_sizer.Add(target_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ---------------------------------------------------------------------
        # 3. Sección: Barra Inferior de Acciones
        # ---------------------------------------------------------------------
        separator = wx.StaticLine(self, wx.ID_ANY, style=wx.LI_HORIZONTAL)
        main_sizer.Add(separator, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Opciones inferiores
        options_row = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_create_groups = wx.CheckBox(
            self, label="Agrupar componentes en KiCad (PCB_GROUP)"
        )
        self.chk_create_groups.SetValue(True)
        self.chk_replicate_tracks = wx.CheckBox(
            self, label="Replicar pistas y vías de la referencia"
        )
        self.chk_replicate_tracks.SetValue(False)

        options_row.Add(
            self.chk_create_groups, 0, wx.RIGHT | wx.TOP | wx.BOTTOM, 12
        )
        options_row.Add(
            self.chk_replicate_tracks, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 6
        )
        main_sizer.Add(options_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        bottom_row = wx.BoxSizer(wx.HORIZONTAL)
        self.summary_status = wx.StaticText(self, label="Listo.")
        self.summary_status.SetForegroundColour(wx.Colour(100, 100, 100))

        self.btn_preview = wx.Button(self, label="Vista previa")
        self.btn_close = wx.Button(self, wx.ID_CANCEL, label="Cerrar")

        self.btn_preview.Bind(wx.EVT_BUTTON, self.align_targets)
        self.btn_close.Bind(wx.EVT_BUTTON, lambda _evt: self.Close())

        bottom_row.Add(self.summary_status, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        bottom_row.Add(self.btn_preview, 0, wx.ALL, 6)
        bottom_row.Add(self.btn_close, 0, wx.ALL, 6)

        main_sizer.Add(bottom_row, 0, wx.EXPAND | wx.ALL, 6)
        self.SetSizer(main_sizer)
        self._update_ui_state()

    def _update_ui_state(self):
        """Update enable/disable status of buttons based on current state and selection."""
        has_reference = bool(self.reference)
        has_targets = bool(self.targets)
        selected_row = self.target_list.GetFirstSelected()
        has_target_selected = selected_row != -1 and selected_row < len(self.targets)

        self.btn_view_ref.Enable(has_reference)
        self.anchor_choice.Enable(has_reference)
        self.btn_add_target.Enable(has_reference)
        self.btn_auto_discover.Enable(has_reference)
        self.btn_remove_target.Enable(has_target_selected)
        self.btn_view_target.Enable(has_target_selected)
        self.btn_inspect_error.Enable(has_target_selected and has_reference)
        self.btn_export_log.Enable(has_reference)
        self.btn_rot_ccw.Enable(has_target_selected)
        self.btn_rot_cw.Enable(has_target_selected)
        self.rotation_choice.Enable(has_target_selected)
        self.btn_clear.Enable(has_reference or has_targets)
        self.btn_preview.Enable(has_reference and has_targets)

        if has_target_selected:
            rot = self.targets[selected_row].get("rotation", 0)
            self.rotation_choice.SetStringSelection(f"{rot}°")
        else:
            self.rotation_choice.SetSelection(0)

    def _on_target_selection_change(self, _event):
        self._update_ui_state()

    def _on_target_activated(self, event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx == -1 or selected_idx >= len(self.targets):
            return
        target_fps = self.targets[selected_idx]["footprints"]
        if self.reference:
            errors, _ = validate_block(self.reference, target_fps)
            if errors:
                self.show_error_details(event)
                return
        self.view_target_in_pcb(event)

    def _on_key_down(self, event):
        keycode = event.GetKeyCode()
        if keycode in (ord("R"), ord("r")):
            if event.ShiftDown():
                self._on_rotate_ccw(None)
            else:
                self._on_rotate_cw(None)
            return
        elif keycode == wx.WXK_DELETE:
            self.remove_target(None)
            return
        event.Skip()

    def _on_rotate_cw(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx != -1 and selected_idx < len(self.targets):
            current_rot = self.targets[selected_idx].get("rotation", 0)
            new_rot = (current_rot + 90) % 360
            self.targets[selected_idx]["rotation"] = new_rot
            self.rotation_choice.SetStringSelection(f"{new_rot}°")
            self.target_list.SetItem(selected_idx, 3, f"{new_rot}°")
            self.summary_status.SetLabel(
                f"Destino {selected_idx + 1}: Rotación configurada en {new_rot}°."
            )

    def _on_rotate_ccw(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx != -1 and selected_idx < len(self.targets):
            current_rot = self.targets[selected_idx].get("rotation", 0)
            new_rot = (current_rot - 90) % 360
            self.targets[selected_idx]["rotation"] = new_rot
            self.rotation_choice.SetStringSelection(f"{new_rot}°")
            self.target_list.SetItem(selected_idx, 3, f"{new_rot}°")
            self.summary_status.SetLabel(
                f"Destino {selected_idx + 1}: Rotación configurada en {new_rot}°."
            )

    def _on_rotation_changed(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx != -1 and selected_idx < len(self.targets):
            rot_str = self.rotation_choice.GetStringSelection().replace("°", "")
            rot = int(rot_str) if rot_str.isdigit() else 0
            self.targets[selected_idx]["rotation"] = rot
            self.target_list.SetItem(selected_idx, 3, f"{rot}°")
            self.summary_status.SetLabel(
                f"Destino {selected_idx + 1}: Rotación configurada en {rot}°."
            )

    def _on_anchor_changed(self, _event):
        anchor_name = self.anchor_choice.GetStringSelection()
        self.summary_status.SetLabel(f"Punto de anclaje seleccionado: {anchor_name}.")

    def _update_targets_table(self):
        """Refresh the target ListCtrl with current targets and validation status."""
        self.target_list.DeleteAllItems()
        for idx, entry in enumerate(self.targets, 1):
            target_fps = entry["footprints"]
            rot = entry.get("rotation", 0)
            item_idx = self.target_list.InsertItem(idx - 1, str(idx))
            refs_str = format_references(target_fps, max_display=10)
            self.target_list.SetItem(item_idx, 1, refs_str)
            self.target_list.SetItem(item_idx, 2, f"{len(target_fps)} fps")
            self.target_list.SetItem(item_idx, 3, f"{rot}°")

            if self.reference:
                errors, matched = validate_block(self.reference, target_fps)
                if errors:
                    self.target_list.SetItem(item_idx, 4, f"✕ Error: {errors[0]}")
                    self.target_list.SetItemTextColour(
                        item_idx, wx.Colour(180, 20, 20)
                    )
                    self.target_list.SetItemBackgroundColour(
                        item_idx, wx.Colour(255, 240, 240)
                    )
                else:
                    self.target_list.SetItem(
                        item_idx, 4, f"✓ Válido ({matched} coincidentes)"
                    )
                    self.target_list.SetItemTextColour(
                        item_idx, wx.Colour(20, 120, 20)
                    )
                    self.target_list.SetItemBackgroundColour(
                        item_idx, wx.Colour(240, 252, 240)
                    )
            else:
                self.target_list.SetItem(item_idx, 4, "Pendiente de referencia")

        self.summary_status.SetLabel(f"Destinos registrados: {len(self.targets)}.")
        self._update_ui_state()

    def capture_reference(self, _event):
        selected = select_footprints(self.board)
        if not selected:
            wx.MessageBox(
                "Selecciona primero los footprints del bloque de referencia en PCB Editor.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return
        self.reference = selected
        ref_tracks = collect_reference_tracks(self.board, selected)
        refs = sorted(fp.GetReference() for fp in selected)
        refs_str = format_references(selected, max_display=12)
        track_info = (
            f", {len(ref_tracks)} pistas/vías" if ref_tracks else ""
        )
        self.ref_status.SetLabel(
            f"✓ Referencia capturada: {len(selected)} footprints{track_info}"
        )
        self.ref_details.SetLabel(f"Componentes: {refs_str}")

        # Actualizar opciones de punto de anclaje
        current_anchor = self.anchor_choice.GetStringSelection()
        choices = ["Centroide del bloque"] + refs
        self.anchor_choice.Clear()
        self.anchor_choice.Append(choices)
        if current_anchor in choices:
            self.anchor_choice.SetStringSelection(current_anchor)
        else:
            self.anchor_choice.SetSelection(0)

        self._update_targets_table()

    def view_reference_in_pcb(self, _event):
        if not self.reference:
            return
        select_in_board(self.board, self.reference)
        self.summary_status.SetLabel(
            f"Referencia seleccionada en PCB ({len(self.reference)} footprints)."
        )

    def view_target_in_pcb(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx == -1 or selected_idx >= len(self.targets):
            return
        target_fps = self.targets[selected_idx]["footprints"]
        select_in_board(self.board, target_fps)
        self.summary_status.SetLabel(
            f"Destino {selected_idx + 1} seleccionado en PCB ({len(target_fps)} footprints)."
        )

    def show_error_details(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx == -1 or selected_idx >= len(self.targets):
            return
        if not self.reference:
            wx.MessageBox(
                "Captura primero un bloque de referencia para diagnosticar discrepancias.",
                "Block Aligner",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        target_fps = self.targets[selected_idx]["footprints"]
        diag = diagnose_block(self.reference, target_fps)
        dlg = ErrorDetailsDialog(self, selected_idx + 1, diag)
        dlg.ShowModal()
        dlg.Destroy()

    def export_diagnostic_log(self, _event):
        if not self.reference:
            wx.MessageBox(
                "Captura primero un bloque de referencia para generar el diagnóstico.",
                "Diagnóstico",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return
        discovered = auto_discover_blocks(
            self.board, self.reference, self.targets
        )
        report = generate_diagnostic_report(
            self.board, self.reference, self.targets, discovered
        )
        try:
            log_dir = os.path.expanduser("~/Block_Aligner")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "debug_log.txt")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(report)
        except OSError as exc:
            self.summary_status.SetLabel(
                "No se pudo guardar el diagnóstico: {}".format(exc)
            )

        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(report))
            wx.TheClipboard.Close()

        dlg = DiagnosticLogDialog(self, report)
        dlg.ShowModal()
        dlg.Destroy()

    def auto_discover(self, _event):
        if not self.reference:
            wx.MessageBox(
                "Captura primero el bloque de referencia antes de auto-detectar.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return

        # Limpiar destinos previos para descubrir desde cero sin mezclas residuales
        self.targets = []

        discovered = auto_discover_blocks(
            self.board, self.reference, []
        )
        report = generate_diagnostic_report(
            self.board, self.reference, self.targets, discovered
        )
        try:
            log_dir = os.path.expanduser("~/Block_Aligner")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "debug_log.txt")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(report)
        except OSError as exc:
            self.summary_status.SetLabel(
                "No se pudo guardar el diagnóstico: {}".format(exc)
            )

        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(report))
            wx.TheClipboard.Close()

        if not discovered:
            self._update_targets_table()
            wx.MessageBox(
                "No se encontraron bloques adicionales coincidentes con la referencia en la PCB.\n\n"
                "Se ha guardado un informe en 'debug_log.txt' y puedes verlo con el botón '📋 Diagnóstico'.",
                "Auto-Detección de Bloques",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        for block in discovered:
            self.targets.append({"footprints": block, "rotation": 0})
        self._update_targets_table()
        wx.MessageBox(
            f"Se auto-detectaron y añadieron {len(discovered)} bloque(s) destino válido(s).\n\n"
            f"📄 El log de diagnóstico se ha guardado en 'debug_log.txt' y copiado a tu portapapeles.",
            "Auto-Detección de Bloques",
            wx.OK | wx.ICON_INFORMATION,
        )

    def add_target(self, _event):
        if not self.reference:
            wx.MessageBox(
                "Captura primero el bloque de referencia antes de añadir destinos.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return
        selected = select_footprints(self.board)
        if not selected:
            wx.MessageBox(
                "Selecciona un bloque de footprints destino en PCB Editor.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return
        selected_refs = {fp.GetReference() for fp in selected}
        reference_refs = {fp.GetReference() for fp in self.reference}
        if selected_refs & reference_refs:
            wx.MessageBox(
                "El destino contiene footprints del bloque de referencia.",
                "Block Aligner",
                wx.OK | wx.ICON_ERROR,
            )
            return
        registered_refs = {
            fp.GetReference()
            for entry in self.targets
            for fp in entry["footprints"]
        }
        overlap = selected_refs & registered_refs
        if overlap:
            wx.MessageBox(
                "El destino se solapa con otro destino ya registrado: {}.".format(
                    ", ".join(sorted(overlap))
                ),
                "Block Aligner",
                wx.OK | wx.ICON_ERROR,
            )
            return
        self.targets.append({"footprints": selected, "rotation": 0})
        self._update_targets_table()

    def remove_target(self, _event):
        selected_idx = self.target_list.GetFirstSelected()
        if selected_idx == -1:
            wx.MessageBox(
                "Selecciona un destino en la tabla para eliminarlo.",
                "Block Aligner",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        del self.targets[selected_idx]
        self._update_targets_table()

    def align_targets(self, _event):
        if not self.reference or not self.targets:
            wx.MessageBox(
                "Captura una referencia y añade al menos un destino antes de alinear.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return
        errors = []
        summary = []
        plans = []
        anchor_name = self.anchor_choice.GetStringSelection()
        replicate_tracks = self.chk_replicate_tracks.GetValue()
        ref_tracks = (
            collect_reference_tracks(self.board, self.reference)
            if replicate_tracks
            else []
        )

        for index, entry in enumerate(self.targets, 1):
            target_fps = entry["footprints"]
            rot = entry.get("rotation", 0)
            validation_errors, matched = validate_block(self.reference, target_fps)
            if validation_errors:
                errors.append(
                    "Destino {}: {}".format(index, "; ".join(validation_errors))
                )
            else:
                ok, result = plan_block(
                    self.reference,
                    target_fps,
                    anchor_ref_name=anchor_name,
                    rotation=rot,
                    ref_tracks=ref_tracks,
                    board=self.board,
                )
                if ok:
                    plans.append(result)
                    track_count = len(result.get("cloned_tracks", []))
                    track_info = (
                        f", {track_count} pistas/vías" if track_count else ""
                    )
                    summary.append(
                        f"Destino {index}: {matched} footprints{track_info} (Rotación: {rot}°)"
                    )
                else:
                    errors.append("Destino {}: {}".format(index, result))

        if errors:
            wx.MessageBox(
                "No se aplicaron cambios debido a errores de validación:\n\n{}\n\nPuedes pulsar 'Detalles error' para inspeccionar qué componentes fallaron.".format(
                    "\n".join(errors)
                ),
                "Validación de Block Aligner",
                wx.OK | wx.ICON_ERROR,
            )
            return

        # Guardar posiciones y orientaciones originales para deshacer
        original_positions = []
        for plan in plans:
            for target_fp, x, y, source_fp, rot in plan["footprint_plan"]:
                original_positions.append(
                    (target_fp, position(target_fp), target_fp.GetOrientation())
                )

        # Aplicar alineación de footprints y crear pistas/vías clonadas
        created_tracks = []
        for plan in plans:
            apply_plan(plan["footprint_plan"])
            for track in plan["cloned_tracks"]:
                self.board.Add(track)
                created_tracks.append(track)
        pcbnew.Refresh()

        confirmation = wx.MessageDialog(
            self,
            "Vista previa activa. Los footprints y pistas/vías se muestran temporalmente en "
            "sus nuevas posiciones (Anclaje: {}, rotaciones aplicadas).\n\n{}\n\n¿Deseas aplicar estos cambios definitivamente?".format(
                anchor_name, "\n".join(summary)
            ),
            "Vista previa de Block Aligner",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
        )
        proceed = confirmation.ShowModal() == wx.ID_YES
        confirmation.Destroy()
        if not proceed:
            # Restaurar footprints a posiciones originales
            for target_fp, (x, y), old_orientation in original_positions:
                set_position(target_fp, x, y)
                target_fp.SetOrientation(old_orientation)
            # Eliminar pistas y vías creadas temporalmente
            for track in created_tracks:
                try:
                    self.board.Remove(track)
                except Exception:
                    pass
            pcbnew.Refresh()
            self.summary_status.SetLabel(
                "Vista previa cancelada. Posiciones y pistas restauradas."
            )
            return

        # Aplicar agrupación nativa de KiCad si está habilitada
        if self.chk_create_groups.GetValue():
            for index, plan in enumerate(plans, 1):
                group_items = plan["target_footprints"] + plan["cloned_tracks"]
                create_pcb_group(
                    self.board,
                    group_items,
                    group_name="Bloque_Destino_{}".format(index),
                )
            pcbnew.Refresh()

        total_tracks_count = len(created_tracks)
        tracks_msg = (
            f" y {total_tracks_count} pistas/vías replicadas"
            if total_tracks_count
            else ""
        )
        self.summary_status.SetLabel(
            f"Alineación aplicada con éxito{tracks_msg}."
        )
        wx.MessageBox(
            f"Alineación aplicada con éxito{tracks_msg}.",
            "Block Aligner",
            wx.OK | wx.ICON_INFORMATION,
        )

    def clear(self, _event):
        self.reference = []
        self.targets = []
        self.ref_status.SetLabel("Ningún bloque de referencia capturado.")
        self.ref_details.SetLabel(
            "Selecciona los footprints en PCB Editor y haz clic en 'Capturar referencia'."
        )
        self.anchor_choice.Clear()
        self.anchor_choice.Append(["Centroide del bloque"])
        self.anchor_choice.SetSelection(0)
        self.rotation_choice.SetSelection(0)
        self._update_targets_table()
        self.summary_status.SetLabel("Listo.")


class BlockAlignerPlugin(pcbnew.ActionPlugin):
    def __init__(self):
        super().__init__()
        self.dialog = None

    def defaults(self):
        self.name = "Block Aligner"
        self.category = "Layout Helper"
        self.description = "Alinea bloques repetidos copiando posiciones y orientaciones."
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "icon.png")

    def Run(self):
        board = pcbnew.GetBoard()
        if self.dialog is not None and self.dialog.IsShown():
            self.dialog.Raise()
            return
        self.dialog = BlockAlignerDialog(None, board)
        self.dialog.Bind(wx.EVT_CLOSE, self._close_dialog)
        self.dialog.Show()

    def _close_dialog(self, event):
        if self.dialog is not None:
            self.dialog.Destroy()
            self.dialog = None
        event.Skip()
