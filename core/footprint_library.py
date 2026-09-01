"""KiCad Footprint Library discovery, indexing, and search manager."""

import glob
import os
import re
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set


@dataclass
class FootprintItem:
    """Represents an individual footprint from a KiCad library."""
    lib_name: str
    fp_name: str
    full_id: str
    file_path: str

    def __str__(self) -> str:
        return self.full_id


class FootprintLibraryManager:
    """Discovers, indexes, and queries KiCad footprint libraries (.pretty folders)."""

    def __init__(self, custom_search_dirs: Optional[List[str]] = None):
        self.search_dirs: List[str] = [
            "/usr/share/kicad/footprints",
            os.path.expanduser("~/.local/share/kicad/10.0/footprints"),
            os.path.expanduser("~/.local/share/kicad/9.0/footprints"),
            os.path.expanduser("~/.local/share/kicad/8.0/footprints"),
            os.path.expanduser("~/Documentos/My_KiCad/MyLibreriaKiCad"),
        ]
        if custom_search_dirs:
            self.search_dirs.extend(custom_search_dirs)

        self.libraries: Dict[str, str] = {}  # lib_name -> .pretty dir path
        self.footprints: List[FootprintItem] = []
        self.footprints_by_lib: Dict[str, List[FootprintItem]] = {}
        self.is_indexed = False
        self._indexing_lock = threading.Lock()

    def discover_and_index(self, on_progress: Optional[Callable[[int, int], None]] = None):
        """Scan directories and index all available .kicad_mod footprints."""
        with self._indexing_lock:
            self.libraries = {}
            self.footprints = []
            self.footprints_by_lib = {}

            pretty_dirs = []
            for base_dir in self.search_dirs:
                if not os.path.isdir(base_dir):
                    continue
                # Find all *.pretty directories directly or recursively
                found = glob.glob(os.path.join(base_dir, "**/*.pretty"), recursive=True)
                for p in found:
                    if os.path.isdir(p):
                        pretty_dirs.append(p)

            total_libs = len(pretty_dirs)
            for idx, pdir in enumerate(pretty_dirs, 1):
                lib_name = os.path.splitext(os.path.basename(pdir))[0]
                self.libraries[lib_name] = pdir
                lib_fps = []

                try:
                    for fname in os.listdir(pdir):
                        if fname.endswith(".kicad_mod"):
                            fp_name = fname[:-10]  # strip '.kicad_mod'
                            full_id = f"{lib_name}:{fp_name}"
                            item = FootprintItem(
                                lib_name=lib_name,
                                fp_name=fp_name,
                                full_id=full_id,
                                file_path=os.path.join(pdir, fname),
                            )
                            lib_fps.append(item)
                            self.footprints.append(item)
                except Exception:
                    pass

                self.footprints_by_lib[lib_name] = sorted(
                    lib_fps, key=lambda x: x.fp_name.lower()
                )

                if on_progress:
                    on_progress(idx, total_libs)

            self.footprints.sort(key=lambda x: x.full_id.lower())
            self.is_indexed = True

    def search(
        self, query: str, library_filter: str = "", limit: int = 150
    ) -> List[FootprintItem]:
        """Search footprints matching query tokens and optional library filter."""
        if not self.is_indexed:
            self.discover_and_index()

        q = query.strip().lower()
        tokens = [t for t in q.split() if t]

        candidates = (
            self.footprints_by_lib.get(library_filter, [])
            if library_filter and library_filter in self.footprints_by_lib
            else self.footprints
        )

        if not tokens:
            return candidates[:limit]

        results = []
        for fp in candidates:
            target_str = fp.full_id.lower()
            if all(tok in target_str for tok in tokens):
                results.append(fp)
                if len(results) >= limit:
                    break

        return results

    def get_library_names(self) -> List[str]:
        """Return sorted list of library names."""
        if not self.is_indexed:
            self.discover_and_index()
        return sorted(self.libraries.keys())
