"""Gestor de referencias para componentes clonados en KiCad.

Soporta dos estrategias:
1. Modo Interrogación (Opción B - Recomendada): Cambia las referencias de las copias a 'R?', 'U?', 'Q?'
   para que KiCad las numere con su herramienta nativa de anotación.
2. Modo Secuencial: Encuentra los números libres más próximos para evitar colisiones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from core.sexpr import SAtom, SNode


@dataclass
class ReferenceAnnotationMode:
    RESET_TO_QUESTION_MARK: str = "question_mark"  # 'R?', 'C?', 'U?'
    AUTO_SEQUENTIAL: str = "sequential"             # 'R7', 'R8', 'U5'


class ReferenceAnnotator:
    """Maneja la anotación de componentes clonados."""

    REGEX_REF = re.compile(r"^([A-Za-z_#]+)(\d+|\?)$")

    @classmethod
    def is_power_symbol(cls, symbol_node: SNode) -> bool:
        """Determina si un símbolo es de alimentación (#PWR, GND, etc.)."""
        ref = symbol_node.get_prop("Reference") or ""
        if ref.startswith("#"):
            return True
        lib_id_node = symbol_node.get_child("lib_id")
        if lib_id_node and lib_id_node.items:
            lib_id = str(symbol_node.get_atom(0) if lib_id_node.items else "")
            # También revisar átomo del nodo lib_id
            first = lib_id_node.get_atom(0, "")
            if str(first).lower().startswith("power:"):
                return True
        return False

    @classmethod
    def extract_prefix(cls, reference: str) -> str:
        """Extrae el prefijo alfabético de una referencia (ej. 'R' de 'R5', 'U' de 'U4')."""
        m = cls.REGEX_REF.match(reference)
        if m:
            return m.group(1)
        # Si no coincide exactamente, tomar letras iniciales
        letters = re.match(r"^([A-Za-z_#]+)", reference)
        return letters.group(1) if letters else "U"

    @classmethod
    def annotate_for_copy(
        cls,
        symbol_node: SNode,
        copy_index: int,
        mode: str = ReferenceAnnotationMode.RESET_TO_QUESTION_MARK,
        allocated_refs: Optional[Set[str]] = None,
        prefix_counters: Optional[Dict[str, int]] = None,
    ) -> str:
        """Actualiza la referencia de un símbolo para una copia.

        Retorna la nueva referencia asignada.
        """
        orig_ref = symbol_node.get_prop("Reference") or ""

        # El original (copia 1) no se modifica
        if copy_index <= 1:
            return orig_ref

        # Símbolos de poder (#PWR01) se resetean a #PWR? o se dejan
        if orig_ref.startswith("#"):
            new_ref = "#PWR?" if mode == ReferenceAnnotationMode.RESET_TO_QUESTION_MARK else orig_ref
            symbol_node.set_prop("Reference", new_ref)
            cls._update_instance_references(symbol_node, new_ref)
            return new_ref

        prefix = cls.extract_prefix(orig_ref)

        if mode == ReferenceAnnotationMode.RESET_TO_QUESTION_MARK:
            new_ref = f"{prefix}?"
        else:
            # Modo secuencial
            if prefix_counters is None:
                prefix_counters = {}
            if allocated_refs is None:
                allocated_refs = set()

            start_num = prefix_counters.get(prefix, 1)
            candidate_num = start_num
            while f"{prefix}{candidate_num}" in allocated_refs:
                candidate_num += 1

            new_ref = f"{prefix}{candidate_num}"
            allocated_refs.add(new_ref)
            prefix_counters[prefix] = candidate_num + 1

        symbol_node.set_prop("Reference", new_ref)
        cls._update_instance_references(symbol_node, new_ref)
        return new_ref

    @classmethod
    def _update_instance_references(cls, symbol_node: SNode, new_ref: str) -> None:
        """Actualiza los bloques (instances ...) internos del símbolo."""
        instances_node = symbol_node.get_child("instances")
        if not instances_node:
            return

        for project_node in instances_node.get_children("project"):
            for path_node in project_node.get_children("path"):
                ref_node = path_node.get_child("reference")
                if ref_node and ref_node.items:
                    # KiCad espera la referencia entrecomillada. Escribirla como átomo
                    # suelto (p. ej. R?) rompe el lexer y el archivo no se puede abrir.
                    ref_node.items[0] = SAtom(new_ref, is_quoted=True)
