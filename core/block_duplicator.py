"""Motor de duplicación, generación de UUIDs y posicionamiento en grilla para KiCad.

Clona bloques esquemáticos N veces con:
- Alineación estricta a la grilla de KiCad (1.27 mm / 50 mil).
- Renovación integral de UUIDs (v4) en símbolos, pines, cables, etiquetas y hojas.
- Aplicación de reglas de renombrado a etiquetas (LabelRenamer).
- Anotación de componentes según la estrategia seleccionada (ReferenceAnnotator).
"""

from __future__ import annotations

import copy
import subprocess
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from core.block_detector import SchematicBlock
from core.label_renamer import LabelRenamer, RenamingRule
from core.reference_annotator import ReferenceAnnotationMode, ReferenceAnnotator
from core.sexpr import SAtom, SExprParser, SExprSerializer, SNode


KICAD_GRID_MM = 1.27  # Grilla estándar de KiCad (50 mil = 1.27 mm)


def snap_to_grid(val: float, grid: float = KICAD_GRID_MM) -> float:
    """Alinea un valor a la grilla especificada."""
    return round(round(val / grid) * grid, 4)


@dataclass
class DuplicationConfig:
    """Configuración para la duplicación de bloques."""

    num_copies: int = 4  # Total incluyendo el bloque original (1 original + 3 copias)
    direction: str = "vertical"  # 'vertical', 'horizontal', 'matrix'
    pitch_x_mm: float = 0.0
    pitch_y_mm: float = 50.8  # 2 pulgadas / 2000 mil por defecto para vertical
    columns_per_row: int = 2   # Para modo matrix
    annotation_mode: str = ReferenceAnnotationMode.RESET_TO_QUESTION_MARK
    renaming_rule: RenamingRule = field(default_factory=RenamingRule)


@dataclass
class DuplicationReport:
    """Informe detallado del resultado de duplicación (para Dry-Run o confirmación)."""

    total_copies_created: int = 0
    symbols_created: int = 0
    wires_created: int = 0
    labels_renamed: List[Tuple[str, str, int]] = field(default_factory=list)  # (original, nuevo, copia_num)
    references_assigned: List[Tuple[str, str, int]] = field(default_factory=list)
    new_items: List[SNode] = field(default_factory=list)


class BlockDuplicator:
    """Ejecuta la duplicación de bloques respetando la integridad del esquema."""

    def __init__(self, config: Optional[DuplicationConfig] = None):
        self.config = config or DuplicationConfig()
        self.renamer = LabelRenamer(self.config.renaming_rule)

    @classmethod
    def regenerate_uuids(cls, node: SNode) -> None:
        """Regenera recursivamente todos los UUIDs en el nodo (símbolo, pines, sheet, etc.)."""
        # Si el nodo tiene uuid
        if node.get_child("uuid"):
            node.set_uuid(str(uuid.uuid4()))

        # Regenerar en pines de símbolos (pin "1" (uuid "..."))
        for item in node.items:
            if isinstance(item, SNode):
                if item.tag == "pin" and item.get_child("uuid"):
                    item.set_uuid(str(uuid.uuid4()))
                else:
                    cls.regenerate_uuids(item)

    def calculate_offsets(self, copy_index: int, bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
        """Calcula el desplazamiento (dx, dy) alineado a la grilla para una copia específica.

        copy_index: 1 para original (dx=0, dy=0), 2 para primera copia, etc.
        """
        if copy_index <= 1:
            return (0.0, 0.0)

        step = copy_index - 1
        cfg = self.config

        if cfg.direction == "horizontal":
            step_x = cfg.pitch_x_mm if cfg.pitch_x_mm != 0.0 else (bbox[2] - bbox[0] + 12.7)
            dx = snap_to_grid(step * step_x)
            dy = 0.0
        elif cfg.direction == "matrix":
            cols = max(1, cfg.columns_per_row)
            col = step % cols
            row = step // cols
            step_x = cfg.pitch_x_mm if cfg.pitch_x_mm != 0.0 else (bbox[2] - bbox[0] + 12.7)
            step_y = cfg.pitch_y_mm if cfg.pitch_y_mm != 0.0 else (bbox[3] - bbox[1] + 12.7)
            dx = snap_to_grid(col * step_x)
            dy = snap_to_grid(row * step_y)
        else:
            # Vertical por defecto
            step_y = cfg.pitch_y_mm if cfg.pitch_y_mm != 0.0 else (bbox[3] - bbox[1] + 12.7)
            dx = 0.0
            dy = snap_to_grid(step * step_y)

        return (dx, dy)

    def duplicate_block(
        self, block: SchematicBlock, dry_run: bool = False
    ) -> DuplicationReport:
        """Duplica los elementos del bloque según la configuración."""
        report = DuplicationReport()
        bbox = block.compute_bounding_box()

        # Rastrear referencias existentes para el modo secuencial
        allocated_refs: Set[str] = set()
        prefix_counters: Dict[str, int] = {}
        for sym in block.symbols:
            ref = sym.get_prop("Reference")
            if ref and not ref.endswith("?"):
                allocated_refs.add(ref)

        new_all_items: List[SNode] = []

        # Generar las copias desde copy_index = 2 hasta N
        for copy_idx in range(2, self.config.num_copies + 1):
            dx, dy = self.calculate_offsets(copy_idx, bbox)

            for item in block.items:
                cloned = item.clone()

                # 1. Regenerar UUIDs únicos
                self.regenerate_uuids(cloned)

                # 2. Desplazar posición a la cuadrícula
                cloned.shift_position(dx, dy)

                # 3. Procesar etiquetas si es un nodo de etiqueta
                if cloned.tag in ("label", "global_label", "hierarchical_label"):
                    orig_name = str(cloned.get_atom(0, ""))
                    new_name = self.renamer.rename_label(orig_name, copy_idx)
                    if cloned.items and isinstance(cloned.items[0], SAtom):
                        cloned.items[0] = SAtom(new_name, is_quoted=cloned.items[0].is_quoted)
                    report.labels_renamed.append((orig_name, new_name, copy_idx))

                # 4. Procesar referencias si es un símbolo
                elif cloned.tag == "symbol":
                    orig_ref = cloned.get_prop("Reference") or ""
                    new_ref = ReferenceAnnotator.annotate_for_copy(
                        cloned,
                        copy_idx,
                        mode=self.config.annotation_mode,
                        allocated_refs=allocated_refs,
                        prefix_counters=prefix_counters,
                    )
                    report.references_assigned.append((orig_ref, new_ref, copy_idx))
                    report.symbols_created += 1

                elif cloned.tag == "wire":
                    report.wires_created += 1

                new_all_items.append(cloned)

            report.total_copies_created += 1

        report.new_items = new_all_items
        return report


def build_kicad_clipboard_payload(
    raw_input: str, block: SchematicBlock, new_items: List[SNode]
) -> str:
    """Construye un bloque S-expression válido para el portapapeles de KiCad (application/kicad)."""
    cleaned = raw_input.strip()
    if cleaned.startswith("("):
        nodes_orig = SExprParser.parse_many(cleaned)
        if len(nodes_orig) == 1 and nodes_orig[0].tag == "kicad_sch":
            root = nodes_orig[0].clone()
            for item in new_items:
                root.add_child(item)
            return SExprSerializer.serialize(root)

    # Si no venía envuelto en (kicad_sch), lo construimos estrictamente
    root = SNode("kicad_sch")
    root.add_child(SNode("version", [SAtom(20260306)]))
    root.add_child(SNode("generator", [SAtom("eeschema", is_quoted=True)]))
    root.add_child(SNode("generator_version", [SAtom("10.0", is_quoted=True)]))

    if block.lib_symbols:
        lib_node = SNode("lib_symbols")
        for sym in block.lib_symbols:
            lib_node.add_child(sym.clone())
        root.add_child(lib_node)

    for orig_item in block.items:
        root.add_child(orig_item.clone())

    for new_item in new_items:
        root.add_child(new_item.clone())

    return SExprSerializer.serialize(root)


def write_kicad_clipboard(sexpr_text: str) -> bool:
    """Escribe datos en el portapapeles con el MIME type 'application/kicad' que KiCad requiere."""
    # 1. Wayland nativo mediante wl-copy con -t application/kicad
    try:
        p = subprocess.Popen(
            ["wl-copy", "-t", "application/kicad"],
            stdin=subprocess.PIPE,
            text=True
        )
        p.communicate(input=sexpr_text)
        if p.returncode == 0:
            return True
    except Exception:
        pass

    # 2. Fallback con wxWidgets si está disponible
    try:
        import wx
        if wx.TheClipboard.Open():
            df = wx.DataFormat("application/kicad")
            custom_data = wx.CustomDataObject(df)
            custom_data.SetData(sexpr_text.encode("utf-8"))
            wx.TheClipboard.SetData(custom_data)
            wx.TheClipboard.Flush()
            wx.TheClipboard.Close()
            return True
    except Exception:
        pass

    return False
