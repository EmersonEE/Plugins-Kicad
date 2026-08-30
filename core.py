"""Pure, deterministic Block Aligner logic.

This module has **no dependency on pcbnew or wxPython**. Every function works on
duck-typed objects (footprints, pads, nets) so it can be unit-tested without a
running KiCad instance. Anything that touches the KiCad API lives in
``tracks.py`` and the UI in ``ui.py``.
"""

import itertools
import math
import re

# Above this group size the geometric matcher switches from an exhaustive
# assignment to the Hungarian algorithm (both are optimal; the exhaustive search
# is kept for the small, well-tested path).
MAX_EXHAUSTIVE_GROUP_SIZE = 8

# Placeholder sentinel used for "no anchor" selections.
CENTROID_ANCHORS = ("<Centroide>", "Centroide del bloque")


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
    """Return (x, y) as ints, tolerating both indexable and .x/.y points."""
    point = footprint.GetPosition()
    try:
        return int(point[0]), int(point[1])
    except (TypeError, IndexError):
        return int(point.x), int(point.y)


def transform_vector(dx, dy, rotation=0.0, mirror_x=False):
    """Transform a relative vector by an optional X-mirror and a rotation.

    Mirroring is applied first (reflect the block's internal layout about its
    vertical axis), then the rotation. KiCad screen space has Y pointing down,
    so a CCW rotation (matching EDA_ANGLE) is:

        new_dx = dx * cos(a) + dy * sin(a)
        new_dy = -dx * sin(a) + dy * cos(a)
    """
    if mirror_x:
        dx = -dx
    if rotation == 0:
        return int(round(dx)), int(round(dy))
    rad = math.radians(rotation)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    new_dx = dx * cos_a + dy * sin_a
    new_dy = -dx * sin_a + dy * cos_a
    return int(round(new_dx)), int(round(new_dy))


def rotate_point(dx, dy, degrees):
    """Backward-compatible alias for :func:`transform_vector` without mirror."""
    return transform_vector(dx, dy, degrees, mirror_x=False)


def centroid(footprints):
    xs = [position(fp)[0] for fp in footprints]
    ys = [position(fp)[1] for fp in footprints]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def pad_net_id(pad):
    """Get a net identifier without relying on the net name."""
    try:
        return int(pad.GetNetCode())
    except (AttributeError, TypeError, ValueError):
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
                            (footprint_key(other), str(other_pad.GetNumber()))
                        )
        # Empty tuple represents an external connection (no block-internal
        # peer). Using a tuple (rather than the previous "external" string)
        # keeps every element of the signature orderable, so sorting never
        # mixes str and tuple comparisons.
        peers_by_pad.append(
            (
                str(pad.GetNumber()),
                tuple(sorted(peers)) if peers else (),
            )
        )
    return tuple(sorted(peers_by_pad))


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


def hungarian_assignment(cost):
    """Solve a square assignment problem (minimization) in O(n^3).

    ``cost`` is a list of rows; returns ``result`` where ``result[i]`` is the
    assigned column index for row ``i``.
    """
    n = len(cost)
    if n == 0:
        return []
    if n == 1:
        return [0]

    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [float("inf")] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float("inf")
            j1 = 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(0, n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    result = [-1] * n
    for j in range(1, n + 1):
        if p[j] != 0:
            result[p[j] - 1] = j - 1
    return result


def match_group_by_geometry(
    ref_parts, target_parts, ref_origin, target_origin, rotation, mirror_x=False
):
    """Match equivalent parts as a group, preserving their block geometry."""
    if len(ref_parts) != len(target_parts):
        return []

    def expected_position(ref_fp):
        rx, ry = position(ref_fp)
        rel_x, rel_y = transform_vector(
            rx - ref_origin[0], ry - ref_origin[1], rotation, mirror_x
        )
        return target_origin[0] + rel_x, target_origin[1] + rel_y

    expected = [expected_position(fp) for fp in ref_parts]
    actual = [position(fp) for fp in target_parts]

    def cost(ref_index, target_index):
        ex, ey = expected[ref_index]
        ax, ay = actual[target_index]
        return (ex - ax) ** 2 + (ey - ay) ** 2

    # Small groups use exhaustive assignment (the well-tested path). Larger
    # groups use the Hungarian algorithm instead of the previous greedy
    # nearest-neighbour fallback, which was not guaranteed to be optimal.
    if len(ref_parts) <= MAX_EXHAUSTIVE_GROUP_SIZE:
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

    cost_matrix = [
        [cost(i, j) for j in range(len(target_parts))]
        for i in range(len(ref_parts))
    ]
    order = hungarian_assignment(cost_matrix)
    return [
        (ref_parts[i], target_parts[order[i]])
        for i in range(len(ref_parts))
    ]


def plan_block(reference, target, anchor_ref_name=None, rotation=0.0, mirror_x=False):
    """Compute a non-destructive placement plan for one destination block.

    Returns ``(ok, result)`` where ``result`` on success is a dict with:

    * ``footprint_plan``: list of ``(target_fp, x, y, source_fp, rotation, mirror_x)``
    * ``target_footprints``: the target footprints
    * ``pairs``: list of ``(ref_fp, target_fp)`` matched pairs (for net mapping)
    """
    if not reference:
        return False, "El bloque de referencia está vacío."
    if not target:
        return False, "El bloque destino está vacío."

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

    ref_origin = ref_center
    target_origin = target_center

    pairs = []
    ref_to_target = {}
    for key, ref_parts in ref_groups.items():
        group_pairs = match_group_by_geometry(
            ref_parts, target_groups[key], ref_origin, target_origin,
            rotation, mirror_x,
        )
        for ref_fp, target_fp in group_pairs:
            pairs.append((ref_fp, target_fp))
            ref_to_target[ref_fp.GetReference()] = target_fp

    if anchor_ref_name and anchor_ref_name not in CENTROID_ANCHORS:
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
                        ref_parts, target_groups[key], ref_origin,
                        target_origin, rotation, mirror_x,
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
        rot_dx, rot_dy = transform_vector(dx, dy, rotation, mirror_x)
        new_x = target_origin[0] + rot_dx
        new_y = target_origin[1] + rot_dy
        if target_fp.IsLocked():
            return False, "El footprint {} está bloqueado.".format(
                target_fp.GetReference()
            )
        fp_plan.append((target_fp, new_x, new_y, ref_fp, rotation, mirror_x))

    return True, {
        "footprint_plan": fp_plan,
        "target_footprints": target,
        "pairs": pairs,
        "ref_origin": ref_origin,
        "target_origin": target_origin,
    }


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


def validate_block(reference, target):
    """Validate a destination without changing the board."""
    errors = []
    if not reference:
        return ["el bloque de referencia está vacío"], 0
    if not target:
        return ["el bloque destino está vacío"], 0
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


def within_block_area(fp, seed, max_diameter, margin_nm=3000000):
    """Reject components that cannot belong to the same physical block."""
    sx, sy = position(seed)
    x, y = position(fp)
    return math.hypot(x - sx, y - sy) <= max_diameter + margin_nm


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


def suggest_fixes(diagnosis):
    """Return deterministic, actionable natural-language hints for a diagnosis.

    This is intentionally a template-based suggestion engine, not a generative
    model: the recommendations are reproducible and always traceable to the
    concrete mismatch data.
    """
    hints = []
    if diagnosis.get("locked"):
        hints.append(
            "Desbloquea (o excluye de la selección) los footprints bloqueados: {}.".format(
                ", ".join(diagnosis["locked"])
            )
        )
    if diagnosis.get("overlap"):
        hints.append(
            "El destino incluye footprints que ya pertenecen a la referencia; "
            "retíralos de la selección: {}.".format(
                ", ".join(diagnosis["overlap"])
            )
        )
    if diagnosis.get("missing"):
        hints.append(
            "Faltan componentes en el destino. Añade los que faltan o ajusta "
            "el bloque de referencia para que coincida."
        )
    if diagnosis.get("extra"):
        hints.append(
            "Hay componentes de más en el destino. Quítalos de la selección."
        )
    if not hints and diagnosis.get("is_valid"):
        hints.append("El bloque es compatible y puede alinearse sin cambios.")
    return hints


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


def format_references(footprints, max_display=8):
    """Format a readable list of footprint reference designators."""
    if not footprints:
        return "Ninguno"
    refs = sorted(fp.GetReference() for fp in footprints)
    if len(refs) <= max_display:
        return ", ".join(refs)
    return (
        ", ".join(refs[:max_display])
        + ", ... (+{} más)".format(len(refs) - max_display)
    )


def planned_bboxes(footprint_plans):
    """Return bounding boxes (min_x, min_y, max_x, max_y) for each planned block."""
    bboxes = []
    for plan in footprint_plans:
        xs = [entry[1] for entry in plan]
        ys = [entry[2] for entry in plan]
        if xs:
            bboxes.append((min(xs), min(ys), max(xs), max(ys)))
        else:
            bboxes.append((0, 0, 0, 0))
    return bboxes


def overlapping_pairs(bboxes, margin_nm=1000000):
    """Return 1-based index pairs of bounding boxes that intersect (with margin)."""
    overlap = []
    for i in range(len(bboxes)):
        for j in range(i + 1, len(bboxes)):
            a, b = bboxes[i], bboxes[j]
            separated = (
                a[2] + margin_nm < b[0]
                or b[2] + margin_nm < a[0]
                or a[3] + margin_nm < b[1]
                or b[3] + margin_nm < a[1]
            )
            if not separated:
                overlap.append((i + 1, j + 1))
    return overlap
