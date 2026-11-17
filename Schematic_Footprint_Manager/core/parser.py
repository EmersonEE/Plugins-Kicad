"""KiCad Schematic (.kicad_sch) parser and safe footprint updater."""

import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class SchematicSymbol:
    """Represents a component/symbol instance in a KiCad schematic."""
    uuid: str
    reference: str
    value: str
    footprint: str
    lib_id: str
    unit: int = 1
    dnp: bool = False
    in_bom: bool = True
    on_board: bool = True
    sheet_file: str = ""
    sheet_name: str = ""
    start_pos: int = 0
    end_pos: int = 0
    raw_block: str = ""

    @property
    def is_power(self) -> bool:
        """Return True if symbol is a power rail or virtual flag (e.g. #PWR, GND, +3V3)."""
        if self.reference.startswith("#"):
            return True
        if self.lib_id.lower().startswith("power:"):
            return True
        return False

    @property
    def prefix(self) -> str:
        """Extract alphabetical prefix from reference designator (e.g. 'R' from 'R12')."""
        m = re.match(r"^([A-Za-z_]+)", self.reference)
        return m.group(1).upper() if m else ""


class SchematicFile:
    """Handles loading, parsing, and updating a single .kicad_sch file."""

    def __init__(self, file_path: str, sheet_name: str = "Root"):
        self.file_path = os.path.abspath(file_path)
        self.sheet_name = sheet_name
        self.content: str = ""
        self.symbols: List[SchematicSymbol] = []
        self.child_sheets: List[Tuple[str, str]] = []  # (subsheet_path, subsheet_name)

    def load(self) -> bool:
        """Read and parse the schematic file."""
        if not os.path.isfile(self.file_path):
            return False
        with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
            self.content = f.read()
        self._parse()
        return True

    def _parse(self):
        """Parse placed symbols and hierarchical sheets from S-expression content."""
        self.symbols = []
        self.child_sheets = []

        # 1. First, locate and skip (lib_symbols ...) block to only parse placed symbols
        lib_syms_match = re.search(r"\(lib_symbols\b", self.content)
        lib_syms_end = 0
        if lib_syms_match:
            lib_syms_start = lib_syms_match.start()
            lib_syms_end = self._find_matching_paren(self.content, lib_syms_start)
            if lib_syms_end == -1:
                lib_syms_end = 0

        # 2. Find all top-level (symbol ...) instances
        # Search for occurrences of '(symbol ' outside lib_symbols
        pos = 0
        length = len(self.content)
        while pos < length:
            match = re.search(r"\(symbol\s", self.content[pos:])
            if not match:
                break
            sym_start = pos + match.start()
            if lib_syms_match and lib_syms_start <= sym_start < lib_syms_end:
                pos = lib_syms_end
                continue

            sym_end = self._find_matching_paren(self.content, sym_start)
            if sym_end == -1:
                pos = sym_start + 8
                continue

            raw_block = self.content[sym_start:sym_end]
            sym = self._parse_symbol_block(raw_block, sym_start, sym_end)
            if sym:
                self.symbols.append(sym)
            pos = sym_end

        # 3. Find all hierarchical (sheet ...) definitions
        pos = 0
        base_dir = os.path.dirname(self.file_path)
        while pos < length:
            match = re.search(r"\(sheet\s", self.content[pos:])
            if not match:
                break
            sheet_start = pos + match.start()
            sheet_end = self._find_matching_paren(self.content, sheet_start)
            if sheet_end == -1:
                pos = sheet_start + 7
                continue

            sheet_block = self.content[sheet_start:sheet_end]
            sheet_file_m = re.search(
                r'\(property\s+"Sheetfile"\s+"([^"]+)"', sheet_block
            )
            sheet_name_m = re.search(
                r'\(property\s+"Sheetname"\s+"([^"]+)"', sheet_block
            )
            if sheet_file_m:
                sub_rel = sheet_file_m.group(1)
                sub_name = sheet_name_m.group(1) if sheet_name_m else os.path.splitext(sub_rel)[0]
                sub_abs = os.path.normpath(os.path.join(base_dir, sub_rel))
                self.child_sheets.append((sub_abs, sub_name))
            pos = sheet_end

    def _parse_symbol_block(
        self, block: str, start_pos: int, end_pos: int
    ) -> Optional[SchematicSymbol]:
        """Extract properties from an individual (symbol ...) S-expression block."""
        # Extract lib_id
        lib_id_m = re.search(r'\(lib_id\s+"([^"]+)"\)', block)
        lib_id = lib_id_m.group(1) if lib_id_m else ""

        # Extract UUID
        uuid_m = re.search(r'\(uuid\s+"([^"]+)"\)', block)
        uuid_str = uuid_m.group(1) if uuid_m else ""

        # Extract unit
        unit_m = re.search(r'\(unit\s+(\d+)\)', block)
        unit = int(unit_m.group(1)) if unit_m else 1

        # Extract DNP, in_bom, on_board
        dnp = bool(re.search(r'\(dnp\s+yes\)', block))
        in_bom = not bool(re.search(r'\(in_bom\s+no\)', block))
        on_board = not bool(re.search(r'\(on_board\s+no\)', block))

        # Extract standard properties
        def get_prop(name: str) -> str:
            # Matches (property "Name" "Value" ...
            m = re.search(
                r'\(property\s+"' + re.escape(name) + r'"\s+"([^"]*)"', block
            )
            return m.group(1) if m else ""

        reference = get_prop("Reference")
        value = get_prop("Value")
        footprint = get_prop("Footprint")

        if not reference and not lib_id:
            return None

        return SchematicSymbol(
            uuid=uuid_str,
            reference=reference,
            value=value,
            footprint=footprint,
            lib_id=lib_id,
            unit=unit,
            dnp=dnp,
            in_bom=in_bom,
            on_board=on_board,
            sheet_file=self.file_path,
            sheet_name=self.sheet_name,
            start_pos=start_pos,
            end_pos=end_pos,
            raw_block=block,
        )

    @staticmethod
    def _find_matching_paren(text: str, start_index: int) -> int:
        """Find the index of the closing parenthesis that matches the opening one at start_index."""
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

    def update_footprints(
        self, ref_to_new_footprint: Dict[str, str], make_backup: bool = True
    ) -> Tuple[bool, int, str]:
        """Update footprints for specified component references in this schematic.

        Returns (success, count_updated, error_message).
        """
        if not ref_to_new_footprint:
            return True, 0, ""

        if make_backup:
            try:
                bak_path = self.file_path + ".bak"
                shutil.copy2(self.file_path, bak_path)
            except Exception as e:
                return False, 0, f"Error creando copia de respaldo: {e}"

        # Re-read fresh content
        with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Parse symbol positions freshly to be 100% accurate
        lib_syms_match = re.search(r"\(lib_symbols\b", content)
        lib_syms_start = lib_syms_match.start() if lib_syms_match else -1
        lib_syms_end = (
            self._find_matching_paren(content, lib_syms_start)
            if lib_syms_match
            else -1
        )

        pos = 0
        updated_blocks = []
        count_updated = 0

        while pos < len(content):
            match = re.search(r"\(symbol\s", content[pos:])
            if not match:
                updated_blocks.append(content[pos:])
                break
            sym_start = pos + match.start()
            if lib_syms_match and lib_syms_start <= sym_start < lib_syms_end:
                updated_blocks.append(content[pos:lib_syms_end])
                pos = lib_syms_end
                continue

            # Append content leading up to this symbol
            updated_blocks.append(content[pos:sym_start])

            sym_end = self._find_matching_paren(content, sym_start)
            if sym_end == -1:
                updated_blocks.append(content[sym_start:])
                break

            block = content[sym_start:sym_end]
            ref_m = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', block)
            ref = ref_m.group(1) if ref_m else ""

            if ref in ref_to_new_footprint:
                new_fp = ref_to_new_footprint[ref]
                # Replace the Footprint property inside this symbol block
                # Pattern: (property "Footprint" "OLD_VAL" ...
                fp_pattern = r'(\(property\s+"Footprint"\s+)"([^"]*)"'
                if re.search(fp_pattern, block):
                    new_block = re.sub(
                        fp_pattern,
                        r'\g<1>"' + new_fp.replace('\\', '\\\\') + r'"',
                        block,
                        count=1,
                    )
                else:
                    # If symbol doesn't have Footprint property yet, insert one after Reference or Value
                    insert_pattern = r'(\(property\s+"Reference"\s+"[^"]*"[^\)]*\))'
                    new_prop = f'\n\t\t(property "Footprint" "{new_fp}" (at 0 0 0) (hide yes))'
                    new_block = re.sub(
                        insert_pattern,
                        r'\g<1>' + new_prop,
                        block,
                        count=1,
                    )

                if new_block != block:
                    count_updated += 1
                updated_blocks.append(new_block)
            else:
                updated_blocks.append(block)

            pos = sym_end

        new_content = "".join(updated_blocks)

        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            self.content = new_content
            self._parse()
            return True, count_updated, ""
        except Exception as e:
            return False, 0, f"Error escribiendo archivo {self.file_path}: {e}"


class SchematicProject:
    """Manages an entire KiCad schematic project (root + all hierarchical sheets)."""

    def __init__(self, root_or_project_file: str):
        self.root_file = os.path.abspath(root_or_project_file)
        self.sheets: Dict[str, SchematicFile] = {}
        self.is_loaded = False

    def load(self) -> bool:
        """Discover and load all hierarchical sheets starting from the root file."""
        self.sheets = {}

        # If user opened a .kicad_pro, find corresponding .kicad_sch
        if self.root_file.endswith(".kicad_pro"):
            base_sch = os.path.splitext(self.root_file)[0] + ".kicad_sch"
            if os.path.isfile(base_sch):
                self.root_file = base_sch
            else:
                return False

        if not os.path.isfile(self.root_file):
            return False

        # Queue of files to load: (file_path, sheet_name)
        queue = [(self.root_file, "Raíz (Root)")]
        visited = set()

        while queue:
            fpath, sname = queue.pop(0)
            norm_path = os.path.normpath(fpath)
            if norm_path in visited:
                continue
            visited.add(norm_path)

            if not os.path.isfile(norm_path):
                continue

            sch = SchematicFile(norm_path, sheet_name=sname)
            if sch.load():
                self.sheets[norm_path] = sch
                for child_path, child_name in sch.child_sheets:
                    if child_path not in visited:
                        queue.append((child_path, child_name))

        self.is_loaded = bool(self.sheets)
        return self.is_loaded

    def get_all_symbols(self, include_power: bool = False) -> List[SchematicSymbol]:
        """Return symbols across all loaded sheets, optionally filtering out power symbols."""
        all_syms = []
        seen_refs = set()

        for sch in self.sheets.values():
            for sym in sch.symbols:
                if not include_power and sym.is_power:
                    continue
                # For multi-unit symbols on the same sheet, we only need to represent the component once
                dedup_key = (sym.sheet_file, sym.reference)
                if dedup_key in seen_refs:
                    continue
                seen_refs.add(dedup_key)
                all_syms.append(sym)

        # Sort naturally by reference (R1, R2, R10, C1, etc.)
        def natural_sort_key(sym: SchematicSymbol):
            m = re.match(r"^([A-Za-z_]+)(\d+)?(.*)$", sym.reference)
            if m:
                prefix = m.group(1)
                num = int(m.group(2)) if m.group(2) else 0
                sfx = m.group(3)
                return (prefix, num, sfx, sym.sheet_name)
            return (sym.reference, 0, "", sym.sheet_name)

        all_syms.sort(key=natural_sort_key)
        return all_syms

    def apply_footprint_updates(
        self,
        updates_by_sheet_and_ref: Dict[Tuple[str, str], str],
        make_backup: bool = True,
    ) -> Tuple[bool, int, List[str]]:
        """Apply footprint modifications across all relevant sheets.

        updates_by_sheet_and_ref: dict mapping (sheet_file_path, reference) -> new_footprint
        """
        total_updated = 0
        errors = []

        # Group updates by sheet
        updates_per_sheet: Dict[str, Dict[str, str]] = {}
        for (sheet_path, ref), new_fp in updates_by_sheet_and_ref.items():
            updates_per_sheet.setdefault(sheet_path, {})[ref] = new_fp

        for sheet_path, ref_map in updates_per_sheet.items():
            if sheet_path in self.sheets:
                sch = self.sheets[sheet_path]
                ok, count, err = sch.update_footprints(
                    ref_map, make_backup=make_backup
                )
                if ok:
                    total_updated += count
                else:
                    errors.append(err)

        return len(errors) == 0, total_updated, errors
