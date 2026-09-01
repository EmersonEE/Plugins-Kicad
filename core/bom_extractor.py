"""BOM (Bill of Materials) extraction and grouping from KiCad schematics."""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class ProductMatch:
    """Represents a matched product from laelectronica.com.gt."""
    title: str
    price: float
    price_str: str
    available: bool
    url: str
    image_url: str = ""
    handle: str = ""

    @property
    def full_url(self) -> str:
        if self.url.startswith("http"):
            return self.url
        return f"https://laelectronica.com.gt{self.url}"


@dataclass
class BOMItem:
    """Represents a grouped component line in the Bill of Materials."""
    value: str
    footprint: str
    lib_id: str
    references: List[str] = field(default_factory=list)
    mpn: str = ""
    description: str = ""
    dnp: bool = False
    in_bom: bool = True
    sheet_name: str = ""
    matched_product: Optional[ProductMatch] = None
    custom_search_term: Optional[str] = None
    ignored: bool = False

    @property
    def quantity(self) -> int:
        return len(self.references)

    @property
    def references_str(self) -> str:
        # Natural sort references (R1, R2, R10)
        def ref_sort_key(r: str):
            m = re.match(r"^([A-Za-z_]+)(\d+)?(.*)$", r)
            if m:
                pfx = m.group(1)
                num = int(m.group(2)) if m.group(2) else 0
                sfx = m.group(3)
                return (pfx, num, sfx)
            return (r, 0, "")

        sorted_refs = sorted(self.references, key=ref_sort_key)
        return ", ".join(sorted_refs)

    @property
    def prefix(self) -> str:
        if self.references:
            m = re.match(r"^([A-Za-z_]+)", self.references[0])
            return m.group(1).upper() if m else ""
        return ""

    @property
    def unit_price(self) -> float:
        if self.matched_product and not self.ignored:
            return self.matched_product.price
        return 0.0

    @property
    def subtotal(self) -> float:
        return self.quantity * self.unit_price

    @property
    def is_matched(self) -> bool:
        return self.matched_product is not None

    @property
    def is_available(self) -> bool:
        if self.matched_product:
            return self.matched_product.available
        return False

    def generate_search_queries(self) -> List[str]:
        """Generate smart search queries for laelectronica.com.gt catalog."""
        if self.custom_search_term:
            return [self.custom_search_term.strip()]

        queries = []
        val = self.value.strip()
        pfx = self.prefix

        # 1. If explicit MPN / Part Number exists, try that first
        if self.mpn:
            queries.append(self.mpn.strip())

        # 2. Resistors (R)
        if pfx == "R":
            # Clean values like 10k, 1k, 4.7k, 100, 220, 10M, 0.1, 470R, etc.
            clean_val = val.replace(" ", "").replace("ohm", "").replace("Ohm", "").replace("Ω", "")
            queries.append(f"Resistencia {clean_val}")
            queries.append(f"Resistencia {val}")
            if clean_val.endswith("R"):
                queries.append(f"Resistencia {clean_val[:-1]}")
            queries.append(clean_val)

        # 3. Capacitors (C)
        elif pfx == "C":
            clean_val = val.replace(" ", "")
            queries.append(f"Capacitor {clean_val}")
            queries.append(f"Capacitor {val}")
            # Equivalencies (0.1uF -> 100nF, 100nF -> 0.1uF)
            if clean_val in ("0.1uF", "0.1µF", "100nF", "100n"):
                queries.extend(["Capacitor 100 nF", "Capacitor 0.1 uF", "100 nF"])
            elif clean_val in ("10uF", "10µF"):
                queries.extend(["Capacitor 10 uF", "10 uF"])
            elif clean_val in ("1000uF", "1000µF", "1000u"):
                queries.extend(["Capacitor 1000 uF", "Capacitor 1,000 uF"])
            queries.append(clean_val)

        # 4. Diodes & LEDs (D)
        elif pfx == "D":
            if "LED" in val.upper() or "LED" in self.lib_id.upper():
                queries.append("LED")
                queries.append(f"LED {val}")
            else:
                queries.append(val)
                queries.append(f"Diodo {val}")

        # 5. Transistors (Q)
        elif pfx == "Q":
            queries.append(val)
            queries.append(f"Transistor {val}")
            queries.append(f"Mosfet {val}")

        # 6. Integrated Circuits & Microcontrollers (U, IC)
        elif pfx in ("U", "IC"):
            # e.g. ESP32, LM358, NE555, ATmega328, CH340, AMS1117
            queries.append(val)
            # Remove minor suffixes if any (e.g. LM358N -> LM358)
            base_m = re.match(r"^([A-Za-z0-9]+)", val)
            if base_m and base_m.group(1) != val:
                queries.append(base_m.group(1))

        # 7. Connectors & Headers (J)
        elif pfx == "J":
            if "Screw" in val or "Terminal" in val or "Screw" in self.lib_id:
                queries.append("Bornera")
                queries.append("Terminal")
            elif "USB" in val or "USB" in self.lib_id:
                queries.append("USB")
                queries.append(f"Conector {val}")
            else:
                queries.append("Pin header")
                queries.append(f"Conector {val}")
                queries.append(val)

        # 8. Switches & Relays (SW, K)
        elif pfx in ("SW", "K"):
            if pfx == "K" or "Relay" in val or "Relay" in self.lib_id:
                queries.append("Rele")
                queries.append("Relay")
                queries.append(val)
            else:
                queries.append("Pulsador")
                queries.append("Switch")
                queries.append(val)

        # 9. Buzzers (BZ)
        elif pfx == "BZ" or "Buzzer" in val:
            queries.append("Buzzer")
            queries.append("Zumbador")

        # 10. Crystals (Y)
        elif pfx == "Y":
            queries.append("Cristal")
            queries.append(f"Cristal {val}")

        # Fallback default: use Value and LibID name
        else:
            queries.append(val)
            if ":" in self.lib_id:
                queries.append(self.lib_id.split(":")[1])

        # De-duplicate while preserving order
        seen = set()
        unique_queries = []
        for q in queries:
            q_clean = q.strip()
            if q_clean and q_clean not in seen:
                seen.add(q_clean)
                unique_queries.append(q_clean)

        return unique_queries


class BOMExtractor:
    """Extracts and groups BOM items from KiCad schematic files."""

    @staticmethod
    def _find_matching_paren(text: str, start_index: int) -> int:
        depth = 0
        in_string = False
        escape = False
        length = len(text)

        for i in range(start_index, length):
            c = text[i]
            if in_string:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = False
            else:
                if c == '"':
                    in_string = True
                elif c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0:
                        return i + 1
        return -1

    @classmethod
    def extract_from_schematic(
        cls, file_path: str, include_dnp: bool = False
    ) -> List[BOMItem]:
        """Extract and group components from a single or multi-sheet KiCad schematic."""
        if not os.path.isfile(file_path):
            return []

        # If .kicad_pro is given, map to .kicad_sch
        if file_path.endswith(".kicad_pro"):
            base_sch = os.path.splitext(file_path)[0] + ".kicad_sch"
            if os.path.isfile(base_sch):
                file_path = base_sch
            else:
                return []

        # Discover all sheets
        queue = [os.path.abspath(file_path)]
        visited = set()
        all_raw_symbols = []

        while queue:
            curr_file = queue.pop(0)
            norm = os.path.normpath(curr_file)
            if norm in visited or not os.path.isfile(norm):
                continue
            visited.add(norm)

            with open(norm, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            base_dir = os.path.dirname(norm)

            # Skip lib_symbols
            lib_syms_m = re.search(r"\(lib_symbols\b", content)
            lib_syms_end = 0
            if lib_syms_m:
                lib_syms_end = cls._find_matching_paren(content, lib_syms_m.start())
                if lib_syms_end == -1:
                    lib_syms_end = 0

            # Parse top-level placed symbols
            pos = 0
            while pos < len(content):
                m = re.search(r"\(symbol\s", content[pos:])
                if not m:
                    break
                sym_start = pos + m.start()
                if lib_syms_m and lib_syms_m.start() <= sym_start < lib_syms_end:
                    pos = lib_syms_end
                    continue

                sym_end = cls._find_matching_paren(content, sym_start)
                if sym_end == -1:
                    pos = sym_start + 8
                    continue

                block = content[sym_start:sym_end]
                sym_data = cls._parse_single_symbol(block, norm)
                if sym_data:
                    all_raw_symbols.append(sym_data)
                pos = sym_end

            # Find sub-sheets
            pos = 0
            while pos < len(content):
                m = re.search(r"\(sheet\s", content[pos:])
                if not m:
                    break
                sh_start = pos + m.start()
                sh_end = cls._find_matching_paren(content, sh_start)
                if sh_end == -1:
                    pos = sh_start + 7
                    continue

                sh_block = content[sh_start:sh_end]
                sf_m = re.search(r'\(property\s+"Sheetfile"\s+"([^"]+)"', sh_block)
                if sf_m:
                    sub_abs = os.path.normpath(os.path.join(base_dir, sf_m.group(1)))
                    if sub_abs not in visited:
                        queue.append(sub_abs)
                pos = sh_end

        # Group symbols into BOMItem entries
        groups: Dict[Tuple[str, str, str, str], BOMItem] = {}
        seen_refs_per_sheet: Set[Tuple[str, str]] = set()

        for s in all_raw_symbols:
            # Filter power flags and non-BOM items
            ref = s["reference"]
            if ref.startswith("#") or s["lib_id"].lower().startswith("power:"):
                continue
            if not s["in_bom"]:
                continue
            if s["dnp"] and not include_dnp:
                continue

            # Dedup multi-unit symbols on same sheet
            dedup = (s["sheet_file"], ref)
            if dedup in seen_refs_per_sheet:
                continue
            seen_refs_per_sheet.add(dedup)

            key = (s["value"], s["footprint"], s["lib_id"], s["mpn"])
            if key not in groups:
                groups[key] = BOMItem(
                    value=s["value"],
                    footprint=s["footprint"],
                    lib_id=s["lib_id"],
                    references=[ref],
                    mpn=s["mpn"],
                    description=s["description"],
                    dnp=s["dnp"],
                    in_bom=s["in_bom"],
                    sheet_name=os.path.basename(s["sheet_file"]),
                )
            else:
                groups[key].references.append(ref)

        # Sort BOM items by prefix and value
        def group_sort_key(item: BOMItem):
            pfx = item.prefix
            pfx_order = {
                "U": 1, "IC": 1, "Q": 2, "D": 3, "R": 4, "C": 5, "L": 6,
                "J": 7, "SW": 8, "K": 8, "BZ": 9, "Y": 10
            }
            return (pfx_order.get(pfx, 99), pfx, item.value)

        bom_list = list(groups.values())
        bom_list.sort(key=group_sort_key)
        return bom_list

    @classmethod
    def _parse_single_symbol(cls, block: str, sheet_file: str) -> Optional[dict]:
        lib_id_m = re.search(r'\(lib_id\s+"([^"]+)"\)', block)
        lib_id = lib_id_m.group(1) if lib_id_m else ""

        dnp = bool(re.search(r'\(dnp\s+yes\)', block))
        in_bom = not bool(re.search(r'\(in_bom\s+no\)', block))

        def get_prop(name: str) -> str:
            m = re.search(r'\(property\s+"' + re.escape(name) + r'"\s+"([^"]*)"', block)
            return m.group(1) if m else ""

        ref = get_prop("Reference")
        val = get_prop("Value")
        fp = get_prop("Footprint")
        desc = get_prop("Description")
        mpn = get_prop("MPN") or get_prop("PartNumber") or get_prop("LCSC")

        if not ref and not lib_id:
            return None

        return {
            "reference": ref,
            "value": val,
            "footprint": fp,
            "lib_id": lib_id,
            "description": desc,
            "mpn": mpn,
            "dnp": dnp,
            "in_bom": in_bom,
            "sheet_file": sheet_file,
        }
