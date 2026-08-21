import math
import os

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


def create_pcb_group(board, footprints, group_name="Bloque_Alineado"):
    """Group footprints together as a native KiCad PCB_GROUP."""
    if not hasattr(pcbnew, "PCB_GROUP") or not footprints:
        return None
    try:
        group = pcbnew.PCB_GROUP(board)
        group.SetName(group_name)
        for fp in footprints:
            group.AddItem(fp)
        board.Add(group)
        return group
    except Exception:
        return None


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


def plan_block(reference, target, anchor_ref_name=None, rotation=0):
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

    # Build mapping from ref_fp -> target_fp
    pairs = []
    ref_to_target = {}
    for key, ref_parts in ref_groups.items():
        for ref_fp, target_fp in zip(ref_parts, target_groups[key]):
            pairs.append((ref_fp, target_fp))
            ref_to_target[ref_fp.GetReference()] = target_fp

    # Determine reference origin and target origin
    if not anchor_ref_name or anchor_ref_name in (
        "<Centroide>",
        "Centroide del bloque",
    ):
        ref_origin = ref_center
        target_origin = target_center
    else:
        ref_anchor_fp = next(
            (fp for fp in reference if fp.GetReference() == anchor_ref_name),
            None,
        )
        if ref_anchor_fp and anchor_ref_name in ref_to_target:
            target_anchor_fp = ref_to_target[anchor_ref_name]
            ref_origin = position(ref_anchor_fp)
            target_origin = position(target_anchor_fp)
        else:
            ref_origin = ref_center
            target_origin = target_center

    plan = []
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
        plan.append((target_fp, new_x, new_y, ref_fp, rotation))

    return True, plan


def apply_plan(plan):
    for target_fp, x, y, source_fp, rotation in plan:
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


def auto_discover_blocks(board, reference, existing_targets):
    """Automatically find and return valid destination blocks across the PCB."""
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

    discovered_blocks = []
    discovered_refs = set()

    # Estrategia 1: Hojas jerárquicas
    sheet_groups = {}
    for fp in all_board_fps:
        sheet_key = (fp.GetSheetfile(), fp.GetSheetname())
        if sheet_key != ("", ""):
            sheet_groups.setdefault(sheet_key, []).append(fp)

    for sheet_key, fps in sheet_groups.items():
        if len(fps) == len(reference):
            errors, matched = validate_block(reference, fps)
            if not errors and matched == len(reference):
                discovered_blocks.append(fps)
                for fp in fps:
                    discovered_refs.add(fp.GetReference())

    # Estrategia 2: Crecimiento por componente clave y conectividad interna
    remaining_fps = [
        fp for fp in all_board_fps if fp.GetReference() not in discovered_refs
    ]
    least_common_key = min(ref_counts, key=lambda k: ref_counts[k])
    seed_fps = [
        fp for fp in remaining_fps if footprint_key(fp) == least_common_key
    ]

    for seed in seed_fps:
        if seed.GetReference() in discovered_refs:
            continue

        cluster = [seed]
        cluster_refs = {seed.GetReference()}
        queue = [seed]

        while queue and len(cluster) < len(reference):
            curr = queue.pop(0)
            curr_nets = set()
            for pad in curr.Pads():
                net_id = pad_net_id(pad)
                if net_id not in (0, "", None):
                    curr_nets.add(net_id)

            for neighbor in remaining_fps:
                n_ref = neighbor.GetReference()
                if n_ref not in cluster_refs and n_ref not in discovered_refs:
                    shares_net = any(
                        pad_net_id(p) in curr_nets
                        for p in neighbor.Pads()
                        if pad_net_id(p) not in (0, "", None)
                    )
                    if shares_net:
                        n_key = footprint_key(neighbor)
                        curr_key_count = sum(
                            1 for fp in cluster if footprint_key(fp) == n_key
                        )
                        if curr_key_count < ref_counts.get(n_key, 0):
                            cluster.append(neighbor)
                            cluster_refs.add(n_ref)
                            queue.append(neighbor)

        if len(cluster) == len(reference):
            errors, matched = validate_block(reference, cluster)
            if not errors and matched == len(reference):
                discovered_blocks.append(cluster)
                for fp in cluster:
                    discovered_refs.add(fp.GetReference())

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
        btn_close.Bind(wx.EVT_BUTTON, lambda _evt: self.Close())
        btn_sizer.Add(btn_close, 0, wx.ALL, 6)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 6)

        self.SetSizer(main_sizer)


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
        self.btn_clear = wx.Button(self, label="Limpiar todo")

        self.btn_add_target.Bind(wx.EVT_BUTTON, self.add_target)
        self.btn_auto_discover.Bind(wx.EVT_BUTTON, self.auto_discover)
        self.btn_remove_target.Bind(wx.EVT_BUTTON, self.remove_target)
        self.btn_view_target.Bind(wx.EVT_BUTTON, self.view_target_in_pcb)
        self.btn_inspect_error.Bind(wx.EVT_BUTTON, self.show_error_details)
        self.btn_clear.Bind(wx.EVT_BUTTON, self.clear)

        target_btn_row.Add(self.btn_add_target, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_auto_discover, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_remove_target, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_view_target, 0, wx.RIGHT, 4)
        target_btn_row.Add(self.btn_inspect_error, 0, wx.RIGHT, 4)
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

        # Opción de agrupación nativa
        options_row = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_create_groups = wx.CheckBox(
            self, label="Agrupar componentes en KiCad tras alinear (PCB_GROUP)"
        )
        self.chk_create_groups.SetValue(True)
        options_row.Add(self.chk_create_groups, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 6)
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
        refs = sorted(fp.GetReference() for fp in selected)
        refs_str = format_references(selected, max_display=12)
        self.ref_status.SetLabel(
            f"✓ Referencia capturada: {len(selected)} footprints"
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

    def auto_discover(self, _event):
        if not self.reference:
            wx.MessageBox(
                "Captura primero el bloque de referencia antes de auto-detectar.",
                "Block Aligner",
                wx.OK | wx.ICON_WARNING,
            )
            return
        discovered = auto_discover_blocks(
            self.board, self.reference, self.targets
        )
        if not discovered:
            wx.MessageBox(
                "No se encontraron bloques adicionales coincidentes con la referencia en la PCB.",
                "Auto-Detección de Bloques",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        for block in discovered:
            self.targets.append({"footprints": block, "rotation": 0})
        self._update_targets_table()
        wx.MessageBox(
            "Se auto-detectaron y añadieron {} bloque(s) destino válido(s).".format(
                len(discovered)
            ),
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

        for index, entry in enumerate(self.targets, 1):
            target_fps = entry["footprints"]
            rot = entry.get("rotation", 0)
            validation_errors, matched = validate_block(self.reference, target_fps)
            if validation_errors:
                errors.append(
                    "Destino {}: {}".format(index, "; ".join(validation_errors))
                )
            else:
                summary.append(
                    "Destino {}: {} footprints coincidentes (Rotación: {}°)".format(
                        index, matched, rot
                    )
                )
                ok, result = plan_block(
                    self.reference,
                    target_fps,
                    anchor_ref_name=anchor_name,
                    rotation=rot,
                )
                if ok:
                    plans.append(result)
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

        original_positions = []
        for plan in plans:
            for target_fp, x, y, source_fp, rot in plan:
                original_positions.append(
                    (target_fp, position(target_fp), target_fp.GetOrientation())
                )
        for plan in plans:
            apply_plan(plan)
        pcbnew.Refresh()

        confirmation = wx.MessageDialog(
            self,
            "Vista previa activa. Los footprints se muestran temporalmente en "
            "sus nuevas posiciones (Anclaje: {}, rotaciones aplicadas).\n\n{}\n\n¿Deseas aplicar estos cambios definitivamente?".format(
                anchor_name, "\n".join(summary)
            ),
            "Vista previa de Block Aligner",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
        )
        proceed = confirmation.ShowModal() == wx.ID_YES
        confirmation.Destroy()
        if not proceed:
            for target_fp, (x, y), old_orientation in original_positions:
                set_position(target_fp, x, y)
                target_fp.SetOrientation(old_orientation)
            pcbnew.Refresh()
            self.summary_status.SetLabel(
                "Vista previa cancelada. Posiciones restauradas."
            )
            return
        if self.chk_create_groups.GetValue():
            for index, entry in enumerate(self.targets, 1):
                target_fps = entry["footprints"]
                create_pcb_group(
                    self.board,
                    target_fps,
                    group_name="Bloque_Destino_{}".format(index),
                )
            pcbnew.Refresh()

        self.summary_status.SetLabel(
            "Alineación aplicada correctamente (grupos creados)."
            if self.chk_create_groups.GetValue()
            else "Alineación aplicada correctamente."
        )
        wx.MessageBox(
            "Alineación aplicada con éxito.",
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
