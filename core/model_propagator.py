"""3D Model propagation, footprint matching, presets, and intelligent library search for KiCad 10."""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pcbnew

# Apply SwigPyIterator patch for Python 3.12+ / 3.14+ compatibility
try:
    for attr in dir(pcbnew):
        obj = getattr(pcbnew, attr, None)
        if isinstance(obj, type) and "SwigPyIterator" in attr:
            if hasattr(obj, "__next__") and not hasattr(obj, "next"):
                obj.next = lambda self: self.__next__()
except Exception:
    pass


def get_footprint_fpid(footprint) -> str:
    """Return the full library identifier string (e.g. 'Resistor_SMD:R_0805_2012Metric')."""
    try:
        fpid = footprint.GetFPID()
        return str(fpid.Format())
    except Exception:
        try:
            return str(footprint.GetFPIDAsString())
        except Exception:
            return ""


def get_footprint_name(footprint) -> str:
    """Return only the item name of the footprint without library prefix."""
    try:
        fpid = footprint.GetFPID()
        return str(fpid.GetLibItemName())
    except Exception:
        fpid_str = get_footprint_fpid(footprint)
        if ":" in fpid_str:
            return fpid_str.split(":", 1)[1]
        return fpid_str


def get_footprint_models(footprint) -> List[pcbnew.FP_3DMODEL]:
    """Safely return a list of 3D models assigned to a footprint."""
    try:
        return list(footprint.Models())
    except Exception:
        return []


def to_vector3d(val) -> pcbnew.VECTOR3D:
    """Convert a tuple or existing VECTOR3D to pcbnew.VECTOR3D safely."""
    if hasattr(val, "x") and hasattr(val, "y") and hasattr(val, "z"):
        return pcbnew.VECTOR3D(float(val.x), float(val.y), float(val.z))
    if isinstance(val, (list, tuple)) and len(val) >= 3:
        return pcbnew.VECTOR3D(float(val[0]), float(val[1]), float(val[2]))
    return pcbnew.VECTOR3D(0.0, 0.0, 0.0)


def get_model_transform(model: pcbnew.FP_3DMODEL) -> dict:
    """Return dictionary with numerical floats for offset, rotation, and scale."""
    if not model:
        return {
            "offset": (0.0, 0.0, 0.0),
            "rotation": (0.0, 0.0, 0.0),
            "scale": (1.0, 1.0, 1.0),
        }
    offset = getattr(model, "m_Offset", None)
    rot = getattr(model, "m_Rotation", None)
    scale = getattr(model, "m_Scale", None)

    ox = float(getattr(offset, "x", 0.0)) if offset else 0.0
    oy = float(getattr(offset, "y", 0.0)) if offset else 0.0
    oz = float(getattr(offset, "z", 0.0)) if offset else 0.0

    rx = float(getattr(rot, "x", 0.0)) if rot else 0.0
    ry = float(getattr(rot, "y", 0.0)) if rot else 0.0
    rz = float(getattr(rot, "z", 0.0)) if rot else 0.0

    sx = float(getattr(scale, "x", 1.0)) if scale else 1.0
    sy = float(getattr(scale, "y", 1.0)) if scale else 1.0
    sz = float(getattr(scale, "z", 1.0)) if scale else 1.0

    return {
        "offset": (ox, oy, oz),
        "rotation": (rx, ry, rz),
        "scale": (sx, sy, sz),
    }


def update_footprint_model_transform(
    footprint,
    model_idx: int,
    offset: Tuple[float, float, float],
    rotation: Tuple[float, float, float],
    scale: Tuple[float, float, float],
) -> bool:
    """Update transformation (offset, rotation, scale) of a model assigned to footprint."""
    try:
        vec_models = footprint.Models()
        if model_idx < 0 or model_idx >= len(vec_models):
            return False

        target_model = vec_models[model_idx]
        target_model.m_Offset = to_vector3d(offset)
        target_model.m_Rotation = to_vector3d(rotation)
        target_model.m_Scale = to_vector3d(scale)
        return True
    except Exception:
        return False


def format_model_info(model: pcbnew.FP_3DMODEL) -> str:
    """Return a clean human-readable summary of a 3D model."""
    fn = getattr(model, "m_Filename", "")
    t = get_model_transform(model)
    ox, oy, oz = t["offset"]
    rx, ry, rz = t["rotation"]
    sx, sy, sz = t["scale"]

    off_str = f"({ox:.2f}, {oy:.2f}, {oz:.2f}) mm"
    rot_str = f"({rx:.1f}°, {ry:.1f}°, {rz:.1f}°)"
    scale_str = f"({sx:.2f}, {sy:.2f}, {sz:.2f})"

    return f"{fn}\n  └─ Offset: {off_str} | Rotación: {rot_str} | Escala: {scale_str}"


def clone_3d_model(source: pcbnew.FP_3DMODEL) -> pcbnew.FP_3DMODEL:
    """Create an exact copy of a 3D model object."""
    new_model = pcbnew.FP_3DMODEL()
    new_model.m_Filename = source.m_Filename
    new_model.m_Offset = to_vector3d(source.m_Offset)
    new_model.m_Scale = to_vector3d(source.m_Scale)
    new_model.m_Rotation = to_vector3d(source.m_Rotation)
    new_model.m_Opacity = float(getattr(source, "m_Opacity", 1.0))
    new_model.m_Show = bool(getattr(source, "m_Show", True))
    return new_model


def apply_3d_models_to_footprint(
    source_models: List[pcbnew.FP_3DMODEL],
    target_footprint,
    overwrite: bool = True,
) -> int:
    """Apply a list of 3D models to a target footprint."""
    if not source_models or not target_footprint:
        return 0

    if overwrite:
        try:
            target_footprint.Models().clear()
        except Exception:
            pass

    count = 0
    for src in source_models:
        cloned = clone_3d_model(src)
        try:
            target_footprint.Add3DModel(cloned)
            count += 1
        except Exception:
            try:
                target_footprint.Models().append(cloned)
                count += 1
            except Exception:
                pass

    return count


@dataclass
class FootprintCandidate:
    """Represents a candidate footprint found on the board."""
    footprint: any
    reference: str
    value: str
    fpid: str
    fp_name: str
    pos_x_mm: float
    pos_y_mm: float
    has_3d_model: bool
    model_count: int
    models_summary: str
    checked: bool = True


def find_candidate_footprints(
    board,
    reference_fp,
    match_by_name_only: bool = False,
    include_with_models: bool = False,
) -> List[FootprintCandidate]:
    """Find all footprints on the board matching the reference footprint."""
    if not board or not reference_fp:
        return []

    ref_fpid = get_footprint_fpid(reference_fp)
    ref_name = get_footprint_name(reference_fp)
    ref_id = id(reference_fp)
    ref_ref = reference_fp.GetReference()

    candidates: List[FootprintCandidate] = []

    for fp in board.GetFootprints():
        if id(fp) == ref_id or fp.GetReference() == ref_ref:
            continue

        cand_fpid = get_footprint_fpid(fp)
        cand_name = get_footprint_name(fp)

        if match_by_name_only:
            is_match = (cand_name == ref_name)
        else:
            is_match = (cand_fpid == ref_fpid)

        if not is_match:
            continue

        models = get_footprint_models(fp)
        has_model = len(models) > 0

        if has_model and not include_with_models:
            continue

        try:
            pt = fp.GetPosition()
            pos_x = pcbnew.ToMM(pt.x) if hasattr(pcbnew, "ToMM") else pt.x / 1e6
            pos_y = pcbnew.ToMM(pt.y) if hasattr(pcbnew, "ToMM") else pt.y / 1e6
        except Exception:
            pos_x, pos_y = 0.0, 0.0

        model_summaries = [os.path.basename(m.m_Filename) for m in models if m.m_Filename]
        summary_str = ", ".join(model_summaries) if model_summaries else "Ninguno"

        candidates.append(
            FootprintCandidate(
                footprint=fp,
                reference=fp.GetReference(),
                value=str(fp.GetValue()),
                fpid=cand_fpid,
                fp_name=cand_name,
                pos_x_mm=pos_x,
                pos_y_mm=pos_y,
                has_3d_model=has_model,
                model_count=len(models),
                models_summary=summary_str,
                checked=True,
            )
        )

    def natural_sort_key(c: FootprintCandidate):
        m = re.match(r"^([A-Za-z_]+)(\d+)?(.*)$", c.reference)
        if m:
            pfx = m.group(1)
            num = int(m.group(2)) if m.group(2) else 0
            sfx = m.group(3)
            return (pfx, num, sfx)
        return (c.reference, 0, "")

    candidates.sort(key=natural_sort_key)
    return candidates


# =============================================================================
# Fase 1: Auditoría y Propagación Global del PCB
# =============================================================================

@dataclass
class FamilyPropagationResult:
    """Detailed propagation result for a single footprint family."""
    family_key: str
    display_name: str
    total_footprints: int
    reference_ref: Optional[str]
    source_models_count: int
    updated_refs: List[str] = field(default_factory=list)
    already_had_model_refs: List[str] = field(default_factory=list)
    status: str = "Pendiente"


@dataclass
class BoardPropagationAudit:
    """Global board audit and propagation report."""
    total_footprints: int
    total_families: int
    families_completed: List[FamilyPropagationResult] = field(default_factory=list)
    families_skipped_no_model: List[FamilyPropagationResult] = field(default_factory=list)
    families_already_full: List[FamilyPropagationResult] = field(default_factory=list)
    total_models_added: int = 0
    total_fps_updated: int = 0


def audit_and_propagate_all_board(
    board,
    match_by_name_only: bool = False,
    overwrite: bool = False,
) -> BoardPropagationAudit:
    """Scan the entire PCB, group footprints into families, and propagate 3D models."""
    if not board:
        return BoardPropagationAudit(total_footprints=0, total_families=0)

    fps = list(board.GetFootprints())
    families: Dict[str, List[any]] = {}

    for fp in fps:
        key = get_footprint_name(fp) if match_by_name_only else get_footprint_fpid(fp)
        if not key:
            key = "(Sin identificador de huella)"
        if key not in families:
            families[key] = []
        families[key].append(fp)

    audit = BoardPropagationAudit(
        total_footprints=len(fps),
        total_families=len(families),
    )

    for family_key, family_fps in sorted(families.items(), key=lambda item: item[0]):
        with_3d = [f for f in family_fps if get_footprint_models(f)]
        without_3d = [f for f in family_fps if not get_footprint_models(f)]

        display_name = get_footprint_name(family_fps[0])

        if with_3d:
            ref_fp = with_3d[0]
            source_models = get_footprint_models(ref_fp)

            targets = family_fps if overwrite else without_3d
            targets_to_apply = [f for f in targets if id(f) != id(ref_fp)]

            updated_refs = []
            for target in targets_to_apply:
                added = apply_3d_models_to_footprint(source_models, target, overwrite=overwrite)
                if added > 0:
                    updated_refs.append(target.GetReference())
                    audit.total_models_added += added
                    audit.total_fps_updated += 1

            already_refs = [f.GetReference() for f in with_3d]

            if updated_refs:
                res = FamilyPropagationResult(
                    family_key=family_key,
                    display_name=display_name,
                    total_footprints=len(family_fps),
                    reference_ref=ref_fp.GetReference(),
                    source_models_count=len(source_models),
                    updated_refs=sorted(updated_refs),
                    already_had_model_refs=sorted(already_refs),
                    status="Completada con éxito",
                )
                audit.families_completed.append(res)
            else:
                res = FamilyPropagationResult(
                    family_key=family_key,
                    display_name=display_name,
                    total_footprints=len(family_fps),
                    reference_ref=ref_fp.GetReference(),
                    source_models_count=len(source_models),
                    updated_refs=[],
                    already_had_model_refs=sorted(already_refs),
                    status="Todos ya tenían modelo 3D",
                )
                audit.families_already_full.append(res)
        else:
            res = FamilyPropagationResult(
                family_key=family_key,
                display_name=display_name,
                total_footprints=len(family_fps),
                reference_ref=None,
                source_models_count=0,
                updated_refs=[],
                already_had_model_refs=[],
                status="Sin modelo 3D de referencia en la placa",
            )
            audit.families_skipped_no_model.append(res)

    return audit


# =============================================================================
# Fase 3: Guardar / Cargar Presets de Modelos 3D (JSON)
# =============================================================================

def export_3d_presets(
    board,
    file_path: str,
    match_by_name_only: bool = False,
    preset_name: str = "KiCad_3D_Preset",
) -> int:
    """Export footprint-to-3D-model mappings from board to a JSON preset file."""
    if not board or not file_path:
        return 0

    fps = list(board.GetFootprints())
    mappings: Dict[str, List[Dict[str, Any]]] = {}

    for fp in fps:
        models = get_footprint_models(fp)
        if not models:
            continue

        key = get_footprint_name(fp) if match_by_name_only else get_footprint_fpid(fp)
        if not key or key in mappings:
            continue

        model_entries = []
        for m in models:
            t = get_model_transform(m)
            model_entries.append({
                "filename": m.m_Filename,
                "offset": list(t["offset"]),
                "rotation": list(t["rotation"]),
                "scale": list(t["scale"]),
                "opacity": float(getattr(m, "m_Opacity", 1.0)),
                "show": bool(getattr(m, "m_Show", True)),
            })

        mappings[key] = model_entries

    data = {
        "preset_name": preset_name,
        "format_version": 1,
        "exported_at": datetime.now().isoformat(),
        "match_by_name_only": match_by_name_only,
        "mapping_count": len(mappings),
        "mappings": mappings,
    }

    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return len(mappings)


def import_3d_presets(
    board,
    file_path: str,
    match_by_name_only: bool = False,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Load a JSON preset and apply 3D models to matching footprints on the board."""
    if not board or not file_path or not os.path.exists(file_path):
        return {
            "success": False,
            "error": "Archivo de preset no encontrado o placa no válida.",
            "total_updated": 0,
            "matched_families": 0,
        }

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return {
            "success": False,
            "error": f"Error al leer el archivo JSON: {exc}",
            "total_updated": 0,
            "matched_families": 0,
        }

    mappings = data.get("mappings", {})
    if not mappings:
        return {
            "success": False,
            "error": "El archivo de preset no contiene asignaciones de modelos 3D válidas.",
            "total_updated": 0,
            "matched_families": 0,
        }

    preset_name_only = data.get("match_by_name_only", False) or match_by_name_only
    fps = list(board.GetFootprints())

    total_updated = 0
    matched_families_set = set()
    updated_refs = []

    for fp in fps:
        key = get_footprint_name(fp) if preset_name_only else get_footprint_fpid(fp)
        
        entries = None
        if key in mappings:
            entries = mappings[key]
        elif not preset_name_only:
            fp_name = get_footprint_name(fp)
            if fp_name in mappings:
                entries = mappings[fp_name]

        if not entries:
            continue

        existing_models = get_footprint_models(fp)
        if existing_models and not overwrite:
            continue

        source_models: List[pcbnew.FP_3DMODEL] = []
        for entry in entries:
            m = pcbnew.FP_3DMODEL()
            m.m_Filename = entry.get("filename", "")
            m.m_Offset = to_vector3d(entry.get("offset", (0.0, 0.0, 0.0)))
            m.m_Rotation = to_vector3d(entry.get("rotation", (0.0, 0.0, 0.0)))
            m.m_Scale = to_vector3d(entry.get("scale", (1.0, 1.0, 1.0)))
            m.m_Opacity = float(entry.get("opacity", 1.0))
            m.m_Show = bool(entry.get("show", True))
            source_models.append(m)

        added = apply_3d_models_to_footprint(source_models, fp, overwrite=overwrite)
        if added > 0:
            total_updated += 1
            matched_families_set.add(key)
            updated_refs.append(fp.GetReference())

    return {
        "success": True,
        "preset_name": data.get("preset_name", "Preset"),
        "total_preset_mappings": len(mappings),
        "matched_families": len(matched_families_set),
        "total_updated": total_updated,
        "updated_refs": updated_refs,
    }


# =============================================================================
# Fase 4: Búsqueda Automática Inteligente en Bibliotecas de KiCad
# =============================================================================

@dataclass
class ModelSearchCandidate:
    """Represents a 3D model candidate found in KiCad libraries."""
    filename: str
    kicad_path: str
    full_path: str
    library_folder: str
    file_type: str
    size_kb: float
    confidence_label: str
    score: int


def get_3d_model_search_roots() -> List[Tuple[str, str]]:
    """Return list of (env_var_name, directory_path) for 3D model libraries."""
    roots: List[Tuple[str, str]] = []
    seen_paths = set()

    for var in [
        "KICAD10_3DMODEL_DIR",
        "KICAD8_3DMODEL_DIR",
        "KICAD7_3DMODEL_DIR",
        "KICAD6_3DMODEL_DIR",
        "KISYS3DMOD",
    ]:
        val = os.environ.get(var)
        if val and os.path.isdir(val) and val not in seen_paths:
            roots.append((var, os.path.abspath(val)))
            seen_paths.add(os.path.abspath(val))

    # Standard system and user fallback paths
    fallbacks = [
        ("KICAD8_3DMODEL_DIR", "/usr/share/kicad/3dmodels"),
        ("KICAD8_3DMODEL_DIR", "/usr/local/share/kicad/3dmodels"),
        ("KICAD8_3DMODEL_DIR", "/app/share/kicad/3dmodels"),
        ("KICAD10_3RD_PARTY", os.path.expanduser("~/.local/share/kicad/10.0/3rdparty/3dmodels")),
        ("KICAD10_USER_3D", os.path.expanduser("~/.local/share/kicad/10.0/3dmodels")),
        ("KICAD8_3RD_PARTY", os.path.expanduser("~/.local/share/kicad/8.0/3rdparty/3dmodels")),
    ]

    for default_var, path in fallbacks:
        if os.path.isdir(path) and os.path.abspath(path) not in seen_paths:
            roots.append((default_var, os.path.abspath(path)))
            seen_paths.add(os.path.abspath(path))

    return roots


def find_matching_3d_models(
    footprint,
    custom_query: Optional[str] = None,
    max_results: int = 30,
) -> List[ModelSearchCandidate]:
    """Search for 3D models matching footprint name in KiCad system 3D directories."""
    if not footprint and not custom_query:
        return []

    fpid = get_footprint_fpid(footprint) if footprint else ""
    item_name = get_footprint_name(footprint) if footprint else ""

    lib_hint = ""
    if ":" in fpid:
        lib_hint = fpid.split(":", 1)[0]

    query = (custom_query.strip() if custom_query else item_name).strip()
    if not query:
        return []

    roots = get_3d_model_search_roots()
    if not roots:
        return []

    query_lower = query.lower()
    # Normalize query for fuzzy matching (e.g. replace underscores/dashes)
    tokens = [t for t in re.split(r"[-_.\s]+", query_lower) if len(t) >= 2]

    results: List[ModelSearchCandidate] = []
    seen_files = set()

    for var_name, root_dir in roots:
        try:
            entries = os.listdir(root_dir)
        except Exception:
            continue

        # Sort folders so that hint library comes first
        folder_list = []
        for ent in entries:
            full_ent = os.path.join(root_dir, ent)
            if os.path.isdir(full_ent) and ent.endswith(".3dshapes"):
                if lib_hint and ent.lower().startswith(lib_hint.lower()):
                    folder_list.insert(0, ent)
                else:
                    folder_list.append(ent)

        for folder in folder_list:
            folder_path = os.path.join(root_dir, folder)
            is_matching_lib = bool(lib_hint and folder.lower().startswith(lib_hint.lower()))

            try:
                files = os.listdir(folder_path)
            except Exception:
                continue

            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in [".step", ".stp", ".wrl"]:
                    continue

                full_path = os.path.join(folder_path, fname)
                if full_path in seen_files:
                    continue

                base_name_no_ext = os.path.splitext(fname)[0]
                base_lower = base_name_no_ext.lower()

                score = 0
                confidence = "Sugerido"

                # 1. Exact match
                if base_lower == query_lower:
                    if is_matching_lib:
                        score = 100
                        confidence = "★★★★★ Coincidencia Exacta"
                    else:
                        score = 85
                        confidence = "★★★★ Exacto en otra librería"
                # 2. Prefix / Starts with match
                elif base_lower.startswith(query_lower) or query_lower.startswith(base_lower):
                    score = 75 if is_matching_lib else 60
                    confidence = "★★★ Alta Similitud"
                # 3. Substring match
                elif query_lower in base_lower:
                    score = 65 if is_matching_lib else 50
                    confidence = "★★ Coincidencia Parcial"
                # 4. Multi-token match
                elif tokens and all(tok in base_lower for tok in tokens):
                    score = 55 if is_matching_lib else 40
                    confidence = "★ Coincidencia de Tokens"
                else:
                    continue

                seen_files.add(full_path)
                try:
                    sz_kb = os.path.getsize(full_path) / 1024.0
                except Exception:
                    sz_kb = 0.0

                kicad_path = f"${{{var_name}}}/{folder}/{fname}"

                results.append(
                    ModelSearchCandidate(
                        filename=fname,
                        kicad_path=kicad_path,
                        full_path=full_path,
                        library_folder=folder,
                        file_type="STEP" if "step" in ext or "stp" in ext else "VRML",
                        size_kb=round(sz_kb, 1),
                        confidence_label=confidence,
                        score=score,
                    )
                )

    # Sort results by score (descending) then by file_type (STEP preferred over WRL) then filename
    results.sort(key=lambda r: (-r.score, 0 if r.file_type == "STEP" else 1, r.filename.lower()))
    return results[:max_results]

# =============================================================================
# Fase 5: Filtros y Búsqueda Rápida en la Tabla de Candidatos
# =============================================================================

def filter_candidate_footprints(
    candidates: List[FootprintCandidate],
    query: Optional[str] = None,
    status_filter: str = "all",  # "all", "no_3d", "has_3d"
) -> List[FootprintCandidate]:
    """Filter a list of candidate footprints by search query and 3D status."""
    import fnmatch

    if not candidates:
        return []

    q = query.strip().lower() if query else ""
    filtered = []

    for c in candidates:
        # Status filter
        if status_filter == "no_3d" and c.has_3d_model:
            continue
        elif status_filter == "has_3d" and not c.has_3d_model:
            continue

        # Query filter
        if q:
            ref_l = c.reference.lower()
            val_l = c.value.lower()
            fpid_l = c.fpid.lower()
            name_l = c.fp_name.lower()

            match = (
                q in ref_l
                or q in val_l
                or q in fpid_l
                or q in name_l
                or fnmatch.fnmatch(ref_l, q)
                or fnmatch.fnmatch(val_l, q)
                or fnmatch.fnmatch(fpid_l, q)
                or fnmatch.fnmatch(name_l, q)
            )
            if not match:
                continue

        filtered.append(c)

    return filtered

# =============================================================================
# Fase 6: Función para Limpiar / Revertir Modelos 3D
# =============================================================================

def clear_3d_models_from_footprint(footprint) -> int:
    """Remove all 3D models assigned to a single footprint. Returns count of models removed."""
    if not footprint:
        return 0
    models = get_footprint_models(footprint)
    count = len(models)
    if count > 0:
        try:
            footprint.Models().clear()
        except Exception:
            pass
    return count


def clear_3d_models_from_candidates(candidates: List[FootprintCandidate]) -> Tuple[int, int]:
    """Remove 3D models from a list of candidate footprints.

    Returns (fps_cleared_count, total_models_removed).
    """
    if not candidates:
        return (0, 0)

    fps_cleared = 0
    total_models = 0

    for cand in candidates:
        removed = clear_3d_models_from_footprint(cand.footprint)
        if removed > 0:
            fps_cleared += 1
            total_models += removed

    return (fps_cleared, total_models)


def clear_3d_models_for_entire_family(
    board,
    family_key: str,
    match_by_name_only: bool = False,
) -> Tuple[int, int, List[str]]:
    """Remove 3D models from all footprints belonging to a specific family on the board.

    Returns (fps_cleared_count, total_models_removed, list_of_references).
    """
    if not board or not family_key:
        return (0, 0, [])

    fps_cleared = 0
    total_models = 0
    cleaned_refs = []

    for fp in board.GetFootprints():
        key = get_footprint_name(fp) if match_by_name_only else get_footprint_fpid(fp)
        if key == family_key:
            removed = clear_3d_models_from_footprint(fp)
            if removed > 0:
                fps_cleared += 1
                total_models += removed
                cleaned_refs.append(fp.GetReference())

    return (fps_cleared, total_models, sorted(cleaned_refs))
