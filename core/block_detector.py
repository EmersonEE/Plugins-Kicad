"""Detección y extracción de bloques esquemáticos para KiCad.

Permite detectar bloques desde:
1. Portapapeles (texto S-expression copiado con Ctrl+C en KiCad).
2. Lista de referencias de componentes (ej. ['R5', 'U4', 'R6', 'Q1', 'K1', 'D6', 'J2']).
3. Bounding box o coordenadas rectangulares.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from core.sexpr import SAtom, SExprParser, SNode


@dataclass
class SchematicBlock:
    """Representa un bloque de elementos esquemáticos listo para ser duplicado."""

    items: List[SNode] = field(default_factory=list)
    lib_symbols: List[SNode] = field(default_factory=list)

    @property
    def symbols(self) -> List[SNode]:
        """Retorna todos los nodos de símbolos dentro del bloque."""
        return [item for item in self.items if item.tag == "symbol"]

    @property
    def wires(self) -> List[SNode]:
        """Retorna todos los cables dentro del bloque."""
        return [item for item in self.items if item.tag == "wire"]

    @property
    def junctions(self) -> List[SNode]:
        """Retorna todas las uniones de cables dentro del bloque."""
        return [item for item in self.items if item.tag == "junction"]

    @property
    def labels(self) -> List[Tuple[SNode, str, str]]:
        """Retorna tuplas (nodo, tipo_etiqueta, nombre_etiqueta).

        Tipos: 'local', 'global', 'hierarchical'.
        """
        results = []
        for item in self.items:
            if item.tag == "label":
                name = item.get_atom(0, "")
                results.append((item, "local", str(name)))
            elif item.tag == "global_label":
                name = item.get_atom(0, "")
                results.append((item, "global", str(name)))
            elif item.tag == "hierarchical_label":
                name = item.get_atom(0, "")
                results.append((item, "hierarchical", str(name)))
        return results

    def compute_bounding_box(self) -> Tuple[float, float, float, float]:
        """Calcula el rectángulo envolvente (min_x, min_y, max_x, max_y) de todos los elementos."""
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        found_coords = False

        for item in self.items:
            # Puntos para nodos con (at X Y)
            pos = item.get_position()
            if pos is not None:
                x, y, _ = pos
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
                found_coords = True

            # Puntos para cables y polilíneas (pts (xy X Y) ...)
            pts = item.get_child("pts")
            if pts:
                for pt in pts.get_children("xy"):
                    pt_pos = pt.get_position()
                    if pt_pos is not None:
                        x, y, _ = pt_pos
                        min_x = min(min_x, x)
                        min_y = min(min_y, y)
                        max_x = max(max_x, x)
                        max_y = max(max_y, y)
                        found_coords = True

        if not found_coords:
            return (0.0, 0.0, 0.0, 0.0)

        return (min_x, min_y, max_x, max_y)


class BlockDetector:
    """Utilidad para detectar y extraer bloques de esquemáticos."""

    BLOCK_TAGS = {
        "symbol", "wire", "bus", "bus_entry", "junction",
        "label", "global_label", "hierarchical_label",
        "text", "polyline", "sheet"
    }

    @classmethod
    def from_clipboard_text(cls, text: str) -> Optional[SchematicBlock]:
        """Extrae un bloque a partir del texto S-expression del portapapeles."""
        cleaned = text.strip()
        if not cleaned or not cleaned.startswith("("):
            return None

        nodes = SExprParser.parse_many(cleaned)
        if not nodes:
            return None

        items: List[SNode] = []
        lib_symbols: List[SNode] = []

        # Si viene envuelto en (kicad_sch ...)
        if len(nodes) == 1 and nodes[0].tag == "kicad_sch":
            root = nodes[0]
            lib_syms_node = root.get_child("lib_symbols")
            if lib_syms_node:
                lib_symbols = lib_syms_node.get_children("symbol")

            for child in root.items:
                if isinstance(child, SNode) and child.tag in cls.BLOCK_TAGS:
                    items.append(child)
        else:
            for node in nodes:
                if node.tag in cls.BLOCK_TAGS:
                    items.append(node)
                elif node.tag == "lib_symbols":
                    lib_symbols = node.get_children("symbol")

        if not items:
            return None

        return SchematicBlock(items=items, lib_symbols=lib_symbols)

    @classmethod
    def read_system_clipboard(cls) -> Optional[str]:
        """Lee el texto del portapapeles del sistema (prioriza MIME application/kicad de Wayland)."""
        # 1. Intentar con wl-paste especificando application/kicad
        try:
            res = subprocess.run(
                ["wl-paste", "-t", "application/kicad", "--no-newline"],
                capture_output=True,
                text=True,
                check=False,
                timeout=2
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout
        except Exception:
            pass

        # 2. Intentar con wl-paste general
        try:
            res = subprocess.run(
                ["wl-paste", "--no-newline"],
                capture_output=True,
                text=True,
                check=False,
                timeout=2
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout
        except Exception:
            pass

        return None

    @classmethod
    def from_schematic_by_references(
        cls, root: SNode, references: List[str], margin: float = 10.0
    ) -> SchematicBlock:
        """Extrae un bloque buscando los símbolos por referencia y los cables/etiquetas conectados o cercanos."""
        ref_set = set(references)
        selected_symbols: List[SNode] = []

        for item in root.items:
            if isinstance(item, SNode) and item.tag == "symbol":
                ref = item.get_prop("Reference")
                if ref in ref_set:
                    selected_symbols.append(item)

        if not selected_symbols:
            return SchematicBlock()

        # Calcular bounding box inicial de los componentes seleccionados
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        for sym in selected_symbols:
            pos = sym.get_position()
            if pos:
                x, y, _ = pos
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

        # Expandir con margen para incluir cables, etiquetas y uniones del bloque
        min_x -= margin
        min_y -= margin
        max_x += margin
        max_y += margin

        return cls.from_schematic_by_bbox(root, (min_x, min_y, max_x, max_y))

    @classmethod
    def from_schematic_by_bbox(
        cls, root: SNode, bbox: Tuple[float, float, float, float]
    ) -> SchematicBlock:
        """Extrae todos los elementos cuyo punto central o extremos caen dentro de bbox."""
        min_x, min_y, max_x, max_y = bbox
        selected_items: List[SNode] = []

        lib_syms_node = root.get_child("lib_symbols")
        lib_symbols = lib_syms_node.get_children("symbol") if lib_syms_node else []

        for item in root.items:
            if not (isinstance(item, SNode) and item.tag in cls.BLOCK_TAGS):
                continue

            pos = item.get_position()
            if pos is not None:
                x, y, _ = pos
                if min_x <= x <= max_x and min_y <= y <= max_y:
                    selected_items.append(item)
                    continue

            # Para cables o polilíneas, comprobar si al menos un extremo o punto está dentro
            pts = item.get_child("pts")
            if pts:
                all_pts = pts.get_children("xy")
                in_box = False
                for pt in all_pts:
                    pt_pos = pt.get_position()
                    if pt_pos:
                        x, y, _ = pt_pos
                        if min_x <= x <= max_x and min_y <= y <= max_y:
                            in_box = True
                            break
                if in_box:
                    selected_items.append(item)

        return SchematicBlock(items=selected_items, lib_symbols=lib_symbols)
