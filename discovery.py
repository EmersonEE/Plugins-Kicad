"""Automatic discovery of repeated blocks on the board.

Pure duck-typed logic (no pcbnew/wx import) so it can be unit-tested. The
discovery uses three deterministic strategies:

1. hierarchical sheets (sheet path / sheet name),
2. reference-designator suffixes (``R1_A`` -> ``R1_B``),
3. internal connectivity graph growth with proximity scoring.
"""

import math
import re

try:
    from . import config as config_module
    from . import core
except ImportError:  # standalone execution (unit tests without KiCad)
    import config as config_module
    import core


def _is_global_net(
    net_id, reference_len, pad_counts_by_net, net_names_by_id,
    net_objects_by_id, config,
):
    """Determine whether a net is global (power/unconnected) rather than a
    block-internal signal.

    Prefers the net class name when the API exposes one (KiCad 8+), falling back
    to the pad-count heuristic and the configurable name list.
    """
    if net_id in (0, "", None, -1):
        return True

    if pad_counts_by_net.get(net_id, 0) > max(
        reference_len + config["global_net_threshold_extra"],
        config["global_net_min_pads"],
    ):
        return True

    net_obj = net_objects_by_id.get(net_id)
    if net_obj is not None:
        try:
            net_class = net_obj.GetNetClass()
            if net_class is not None:
                class_name = str(net_class.GetName()).upper().strip()
                if any(
                    token in class_name
                    for token in ("PWR", "POWER", "GND")
                ):
                    return True
        except Exception:
            pass

    name = str(net_names_by_id.get(net_id, "")).upper().strip()
    upper_keys = [str(k).upper() for k in config["power_net_names"]]
    return any(
        k == name
        or name.startswith("+")
        or name.endswith("GND")
        or name.startswith("GND")
        for k in upper_keys
    )


def auto_discover_blocks(board, reference, existing_targets, config=None, progress_cb=None):
    """Automatically find valid destination blocks across the PCB without mixing.

    ``progress_cb(done, total)``, when provided, is called periodically so the
    UI can show progress.
    """
    if not reference:
        return []

    config = config or config_module.default_config()

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
        k = core.footprint_key(fp)
        ref_counts[k] = ref_counts.get(k, 0) + 1
    ref_diameter = core.block_diameter(reference)
    area_margin = config["block_area_margin_nm"]

    discovered_blocks = []
    discovered_refs = set()

    # Precompute global / power nets and net objects.
    pad_counts_by_net = {}
    net_names_by_id = {}
    net_objects_by_id = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            nid = core.pad_net_id(pad)
            if nid not in (0, "", None, -1):
                pad_counts_by_net[nid] = pad_counts_by_net.get(nid, 0) + 1
                if nid not in net_names_by_id:
                    net_names_by_id[nid] = core.pad_net_name(pad)
                if nid not in net_objects_by_id:
                    try:
                        net_obj = pad.GetNet()
                        if net_obj is not None:
                            net_objects_by_id[nid] = net_obj
                    except Exception:
                        pass

    def is_global_net(net_id):
        return _is_global_net(
            net_id, len(reference), pad_counts_by_net, net_names_by_id,
            net_objects_by_id, config,
        )

    # -------------------------------------------------------------------------
    # Strategy 1: hierarchical sheets (Sheet Path & Sheet Name)
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
                sheet_key = "{}::{}".format(sheet_file, sheet_name)

        if sheet_key:
            sheet_groups.setdefault(sheet_key, []).append(fp)

    for sheet_key, fps in sheet_groups.items():
        if len(fps) == len(reference):
            errors, matched = core.validate_block(reference, fps)
            if not errors and matched == len(reference):
                discovered_blocks.append(fps)
                for fp in fps:
                    discovered_refs.add(fp.GetReference())

    # -------------------------------------------------------------------------
    # Strategy 2: reference-designator suffixes (e.g. _A -> _B, _C)
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
                cand_refs = ["{}{}{}".format(p, n, sfx) for p, n, s in parsed]
                if all(
                    r in fps_by_ref and r not in discovered_refs
                    for r in cand_refs
                ):
                    cand_block = [fps_by_ref[r] for r in cand_refs]
                    errors, matched = core.validate_block(reference, cand_block)
                    if not errors and matched == len(reference):
                        discovered_blocks.append(cand_block)
                        for r in cand_refs:
                            discovered_refs.add(r)

    # -------------------------------------------------------------------------
    # Strategy 3: internal graph growth, net names and proximity
    # -------------------------------------------------------------------------
    remaining_fps = [
        fp for fp in all_board_fps if fp.GetReference() not in discovered_refs
    ]

    def seed_score(fp):
        named_cnt = len(core.extract_named_references_from_nets(fp))
        pads_cnt = len(
            [p for p in fp.Pads() if core.pad_net_id(p) not in (0, "", None, -1)]
        )
        return (named_cnt, pads_cnt)

    best_ref_seed = max(reference, key=seed_score)
    seed_key = core.footprint_key(best_ref_seed)
    seed_x, seed_y = core.position(best_ref_seed)
    expected_distances = {}
    for ref_fp in reference:
        x, y = core.position(ref_fp)
        expected_distances.setdefault(core.footprint_key(ref_fp), []).append(
            math.hypot(x - seed_x, y - seed_y)
        )

    seed_fps = [
        fp for fp in remaining_fps if core.footprint_key(fp) == seed_key
    ]
    seed_fps.sort(key=lambda fp: core.extract_ref_number(fp.GetReference()))

    total_seeds = len(seed_fps)
    for seed_index, seed in enumerate(seed_fps, 1):
        if progress_cb:
            progress_cb(seed_index, total_seeds)
        if seed.GetReference() in discovered_refs:
            continue

        cluster = [seed]
        cluster_refs = {seed.GetReference()}
        queue = [seed]

        # 3A. BFS over internal signals and component names in nets.
        while queue and len(cluster) < len(reference):
            curr = queue.pop(0)
            curr_internal_nets = set()
            for pad in curr.Pads():
                nid = core.pad_net_id(pad)
                if not is_global_net(nid):
                    curr_internal_nets.add(nid)

            named_in_curr = core.extract_named_references_from_nets(curr)

            for neighbor in remaining_fps:
                n_ref = neighbor.GetReference()
                if n_ref not in cluster_refs and n_ref not in discovered_refs:
                    shares = any(
                        core.pad_net_id(p) in curr_internal_nets
                        for p in neighbor.Pads()
                        if not is_global_net(core.pad_net_id(p))
                    )
                    is_named = (n_ref in named_in_curr) or (
                        curr.GetReference()
                        in core.extract_named_references_from_nets(neighbor)
                    )

                    if not (shares or is_named) and not core.within_block_area(
                        neighbor, seed, ref_diameter, area_margin
                    ):
                        continue
                    if shares or is_named:
                        n_key = core.footprint_key(neighbor)
                        curr_k_count = sum(
                            1 for fp in cluster if core.footprint_key(fp) == n_key
                        )
                        if curr_k_count < ref_counts.get(n_key, 0):
                            cluster.append(neighbor)
                            cluster_refs.add(n_ref)
                            queue.append(neighbor)

        # 3B. Complete associated components (cross nets + weighted proximity).
        needed_keys = ref_counts.copy()
        for fp in cluster:
            needed_keys[core.footprint_key(fp)] -= 1
            if needed_keys[core.footprint_key(fp)] == 0:
                del needed_keys[core.footprint_key(fp)]

        if needed_keys:
            cx = sum(core.position(fp)[0] for fp in cluster) // len(cluster)
            cy = sum(core.position(fp)[1] for fp in cluster) // len(cluster)
            avg_num = (
                sum(core.extract_ref_number(f.GetReference()) for f in cluster)
                / len(cluster)
            )

            for k, count in list(needed_keys.items()):
                available = [
                    fp
                    for fp in remaining_fps
                    if fp.GetReference() not in cluster_refs
                    and fp.GetReference() not in discovered_refs
                    and core.footprint_key(fp) == k
                    and core.within_block_area(fp, seed, ref_diameter, area_margin)
                ]

                def score_part(fp):
                    fp_x, fp_y = core.position(fp)
                    dist_sq = (fp_x - cx) ** 2 + (fp_y - cy) ** 2
                    actual_distance = math.hypot(
                        fp_x - core.position(seed)[0],
                        fp_y - core.position(seed)[1],
                    )
                    geometry_error = min(
                        abs(actual_distance - expected)
                        for expected in expected_distances.get(k, [0])
                    )
                    num_diff = abs(
                        core.extract_ref_number(fp.GetReference()) - avg_num
                    )
                    named_in_fp = core.extract_named_references_from_nets(fp)
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
            errors, matched = core.validate_block(reference, cluster)
            if not errors and matched == len(reference):
                discovered_blocks.append(cluster)
                for fp in cluster:
                    discovered_refs.add(fp.GetReference())

    discovered_blocks.sort(
        key=lambda blk: min(
            core.extract_ref_number(fp.GetReference()) for fp in blk
        )
    )
    return discovered_blocks
