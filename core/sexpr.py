"""Parser y serializador de S-expressions para archivos KiCad (.kicad_sch).

Diseñado específicamente para esquemáticos de KiCad 8, 9 y 10.
Preserva tipos de datos (cadenas entrecomilladas vs átomos/símbolos),
y genera una sintaxis limpia y conforme a las especificaciones oficiales.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterator, List, Optional, Tuple, Union


class SAtom:
    """Representa un valor atómico (símbolo o cadena entrecomillada)."""

    __slots__ = ("value", "is_quoted")

    def __init__(self, value: Any, is_quoted: bool = False):
        self.value = value
        self.is_quoted = is_quoted

    def __repr__(self) -> str:
        if self.is_quoted:
            return f'"{self.value}"'
        return str(self.value)

    def __str__(self) -> str:
        return str(self.value)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, SAtom):
            return self.value == other.value and self.is_quoted == other.is_quoted
        return self.value == other

    def serialize(self) -> str:
        """Serializa el átomo para S-expression."""
        if self.is_quoted:
            # Escapar comillas dobles y barras invertidas
            escaped = str(self.value).replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return str(self.value)


class SNode:
    """Representa un nodo/lista de S-expression: (tag item1 item2 ...)."""

    __slots__ = ("tag", "items")

    def __init__(self, tag: str, items: Optional[List[Union[SNode, SAtom, str, int, float]]] = None):
        self.tag = str(tag)
        self.items: List[Union[SNode, SAtom, str, int, float]] = items if items is not None else []

    def clone(self) -> SNode:
        """Copia profunda del nodo."""
        new_items = []
        for item in self.items:
            if isinstance(item, SNode):
                new_items.append(item.clone())
            elif isinstance(item, SAtom):
                new_items.append(SAtom(item.value, item.is_quoted))
            else:
                new_items.append(copy.deepcopy(item))
        return SNode(self.tag, new_items)

    def get_child(self, tag: str) -> Optional[SNode]:
        """Retorna el primer subnodo hijo con el tag especificado."""
        for item in self.items:
            if isinstance(item, SNode) and item.tag == tag:
                return item
        return None

    def get_children(self, tag: str) -> List[SNode]:
        """Retorna todos los subnodos hijos con el tag especificado."""
        return [item for item in self.items if isinstance(item, SNode) and item.tag == tag]

    def remove_children(self, tag: str) -> None:
        """Elimina todos los hijos con el tag especificado."""
        self.items = [item for item in self.items if not (isinstance(item, SNode) and item.tag == tag)]

    def add_child(self, child: Union[SNode, SAtom, str, int, float]) -> None:
        """Añade un hijo a este nodo."""
        self.items.append(child)

    def get_atom(self, index: int, default: Any = None) -> Any:
        """Retorna el valor del átomo en la posición index de items."""
        if 0 <= index < len(self.items):
            item = self.items[index]
            if isinstance(item, SAtom):
                return item.value
            return item
        return default

    # --- Métodos específicos para entidades KiCad ---

    def get_prop(self, name: str) -> Optional[str]:
        """Retorna el valor de una propiedad: (property "Name" "Value" ...)."""
        for item in self.items:
            if isinstance(item, SNode) and item.tag == "property":
                prop_name = item.get_atom(0)
                if prop_name == name:
                    return str(item.get_atom(1, ""))
        return None

    def set_prop(self, name: str, value: str) -> bool:
        """Actualiza el valor de una propiedad existente."""
        for item in self.items:
            if isinstance(item, SNode) and item.tag == "property":
                prop_name = item.get_atom(0)
                if prop_name == name:
                    if len(item.items) > 1:
                        if isinstance(item.items[1], SAtom):
                            item.items[1] = SAtom(value, is_quoted=True)
                        else:
                            item.items[1] = SAtom(value, is_quoted=True)
                    else:
                        item.items.append(SAtom(value, is_quoted=True))
                    return True
        return False

    def get_uuid(self) -> Optional[str]:
        """Obtiene el UUID del elemento (uuid "xxx-xxx")."""
        uuid_node = self.get_child("uuid")
        if uuid_node:
            return str(uuid_node.get_atom(0, ""))
        return None

    def set_uuid(self, new_uuid: str) -> None:
        """Establece o reemplaza el UUID."""
        uuid_node = self.get_child("uuid")
        if uuid_node:
            uuid_node.items = [SAtom(new_uuid, is_quoted=True)]
        else:
            self.items.append(SNode("uuid", [SAtom(new_uuid, is_quoted=True)]))

    def get_position(self) -> Optional[Tuple[float, float, Optional[float]]]:
        """Obtiene la posición (at X Y [R]) del nodo."""
        at_node = self.get_child("at")
        if at_node and len(at_node.items) >= 2:
            try:
                x = float(str(at_node.get_atom(0)))
                y = float(str(at_node.get_atom(1)))
                r = float(str(at_node.get_atom(2))) if len(at_node.items) > 2 else None
                return (x, y, r)
            except ValueError:
                return None
        return None

    def set_position(self, x: float, y: float, r: Optional[float] = None) -> None:
        """Establece la posición (at X Y [R])."""
        at_node = self.get_child("at")
        formatted_x = round(x, 4)
        formatted_y = round(y, 4)
        new_items: List[Union[SNode, SAtom, str, int, float]] = [
            SAtom(formatted_x if formatted_x != int(formatted_x) else int(formatted_x)),
            SAtom(formatted_y if formatted_y != int(formatted_y) else int(formatted_y)),
        ]
        if r is not None:
            formatted_r = round(r, 4)
            new_items.append(SAtom(formatted_r if formatted_r != int(formatted_r) else int(formatted_r)))

        if at_node:
            at_node.items = new_items
        else:
            self.items.insert(0, SNode("at", new_items))

    def shift_position(self, dx: float, dy: float) -> None:
        """Desplaza la posición (at X Y [R]) por dx, dy recursivamente en este nodo y subpropiedades."""
        at_node = self.get_child("at")
        if at_node and len(at_node.items) >= 2:
            try:
                x = float(str(at_node.get_atom(0))) + dx
                y = float(str(at_node.get_atom(1))) + dy
                r = at_node.get_atom(2) if len(at_node.items) > 2 else None
                r_val = float(str(r)) if r is not None else None
                self.set_position(x, y, r_val)
            except ValueError:
                pass

        # Desplazar propiedades hijas que tengan (at ...)
        for item in self.items:
            if isinstance(item, SNode) and item.tag == "property":
                prop_at = item.get_child("at")
                if prop_at and len(prop_at.items) >= 2:
                    try:
                        px = float(str(prop_at.get_atom(0))) + dx
                        py = float(str(prop_at.get_atom(1))) + dy
                        pr = prop_at.get_atom(2) if len(prop_at.items) > 2 else None
                        pr_val = float(str(pr)) if pr is not None else None
                        item.set_position(px, py, pr_val)
                    except ValueError:
                        pass

        # Desplazar polilíneas o cables (pts (xy X Y) ...)
        pts_node = self.get_child("pts")
        if pts_node:
            for pt in pts_node.get_children("xy"):
                if len(pt.items) >= 2:
                    try:
                        px = float(str(pt.get_atom(0))) + dx
                        py = float(str(pt.get_atom(1))) + dy
                        pt.set_position(px, py)
                    except ValueError:
                        pass

    def __repr__(self) -> str:
        return f"SNode({self.tag}, len={len(self.items)})"


class SExprParser:
    """Tokenizador y parser para expresiones S-expression de KiCad."""

    @staticmethod
    def tokenize(text: str) -> Iterator[Tuple[str, bool]]:
        """Genera tuplas (token, is_quoted)."""
        idx = 0
        length = len(text)
        while idx < length:
            ch = text[idx]

            # Espacios en blanco
            if ch.isspace():
                idx += 1
                continue

            # Comentarios (KiCad rara vez los tiene, pero permitidos)
            if ch == ";":
                idx = text.find("\n", idx)
                if idx == -1:
                    break
                continue

            # Paréntesis
            if ch == "(" or ch == ")":
                yield (ch, False)
                idx += 1
                continue

            # Cadenas entrecomilladas
            if ch == '"':
                idx += 1
                start = idx
                chars = []
                while idx < length:
                    c = text[idx]
                    if c == "\\":
                        idx += 1
                        if idx < length:
                            chars.append(text[idx])
                            idx += 1
                        continue
                    if c == '"':
                        break
                    chars.append(c)
                    idx += 1
                token = "".join(chars)
                yield (token, True)
                idx += 1  # saltar comilla de cierre
                continue

            # Átomo / símbolo sin comillas
            start = idx
            while idx < length and not text[idx].isspace() and text[idx] not in "();\"":
                idx += 1
            yield (text[start:idx], False)

    @classmethod
    def parse_many(cls, text: str) -> List[SNode]:
        """Parsea una secuencia de S-expressions en la raíz (ej. portapapeles con múltiples bloques)."""
        tokens = cls.tokenize(text)
        stack: List[List[Any]] = []
        root_nodes: List[SNode] = []

        for token, is_quoted in tokens:
            if token == "(":
                stack.append([])
            elif token == ")":
                if not stack:
                    continue
                current_items = stack.pop()
                if not current_items:
                    continue
                tag_item = current_items[0]
                tag = tag_item.value if isinstance(tag_item, SAtom) else str(tag_item)
                node = SNode(tag, current_items[1:])
                if stack:
                    stack[-1].append(node)
                else:
                    root_nodes.append(node)
            else:
                atom = SAtom(token, is_quoted=is_quoted)
                if stack:
                    stack[-1].append(atom)
                else:
                    # Átomo suelto en la raíz (raro)
                    pass

        return root_nodes

    @classmethod
    def parse(cls, text: str) -> Optional[SNode]:
        """Parsea un archivo o bloque completo. Retorna el nodo raíz principal."""
        nodes = cls.parse_many(text)
        if not nodes:
            return None
        return nodes[0]


class SExprSerializer:
    """Serializador para convertir nodos AST en texto S-expression formateado."""

    # Tags que se deben mantener en una sola línea por legibilidad
    INLINE_TAGS = {
        "at", "xy", "size", "font", "stroke", "fill", "effects", "uuid", "unit",
        "in_bom", "on_board", "dnp", "fields_autoplaced", "shape", "color",
        "diameter", "length", "width", "number", "name", "pin", "mirror",
        "hide", "justify", "exclude_from_sim", "version", "generator", "generator_version"
    }

    @classmethod
    def serialize_node(cls, node: SNode, indent_level: int = 0, indent_str: str = "\t") -> str:
        """Serializa un SNode recursivamente respetando el estilo de KiCad."""
        # Verificar si este nodo puede serializarse en una sola línea
        if cls._can_be_inline(node):
            return cls._serialize_inline(node)

        pad = indent_str * indent_level
        lines = [f"{pad}({node.tag}"]

        for item in node.items:
            if isinstance(item, SNode):
                lines.append(cls.serialize_node(item, indent_level + 1, indent_str))
            elif isinstance(item, SAtom):
                lines.append(f"{indent_str * (indent_level + 1)}{item.serialize()}")
            else:
                lines.append(f"{indent_str * (indent_level + 1)}{item}")

        lines.append(f"{pad})")
        return "\n".join(lines)

    @classmethod
    def _can_be_inline(cls, node: SNode) -> bool:
        """Determina si un nodo y todos sus descendientes caben limpiamente en una línea."""
        if node.tag not in cls.INLINE_TAGS:
            return False
        # Si tiene muchos hijos o hijos no inlines, no debe ser inline
        for item in node.items:
            if isinstance(item, SNode):
                if item.tag not in cls.INLINE_TAGS:
                    return False
                if not cls._can_be_inline(item):
                    return False
        return True

    @classmethod
    def _serialize_inline(cls, node: SNode) -> str:
        """Serializa un nodo en una sola línea."""
        parts = [f"({node.tag}"]
        for item in node.items:
            if isinstance(item, SNode):
                parts.append(cls._serialize_inline(item))
            elif isinstance(item, SAtom):
                parts.append(item.serialize())
            else:
                parts.append(str(item))
        return " ".join(parts) + ")"

    @classmethod
    def serialize(cls, root: Union[SNode, List[SNode]], indent_str: str = "\t") -> str:
        """Serializa un nodo raíz o lista de nodos a formato de texto."""
        if isinstance(root, list):
            return "\n".join(cls.serialize_node(n, 0, indent_str) for n in root) + "\n"
        return cls.serialize_node(root, 0, indent_str) + "\n"
