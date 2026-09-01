# Block Aligner

KiCad PCB Editor action plugin that copies relative footprint positions and
orientations from one selected reference block to one or more destination blocks.

## Features

- **Component Matching**: Matches components by value, library footprint, pad count, and internal block connectivity. Net names and net codes are ignored, so equivalent blocks can use different nets. Equivalent components are paired as part of the complete block geometry, preserving relationships such as `R1-D1`, `R2-D2`, etc. Large groups (more than 8 equivalent parts) use the Hungarian algorithm for an optimal assignment instead of a greedy nearest-neighbour.
- **Auto-Discovery**: One-click **Auto-detectar** scans the entire board to automatically identify all matching multi-channel blocks (via hierarchical sheets, reference-designator suffixes, or connectivity graphs). Candidates are constrained to the physical area implied by the reference block and are not completed with unrelated distant footprints. Power nets are detected via net class and a configurable name list.
- **Schematic Sync Guard**: Before auto-discovery, `kicad-cli` compares saved schematic pin nets with matching PCB footprints. If the PCB is stale, detection stops and asks the user to save the schematic and update the PCB with **F8**, preventing channels from being mixed by incomplete connectivity.
- **Schematic-first discovery**: Once synchronization is confirmed, repeated blocks are formed using the saved schematic connectivity as the primary graph instead of relying only on current PCB proximity.
- **Mapping inspector**: Every destination records its detection method and confidence, and **Correspondencias** shows each reference-to-destination pair. Ambiguous mappings block application.
- **Manual mapping editor**: A selected pair can be reassigned to another equivalent destination. Occupied destinations are swapped automatically to preserve a one-to-one mapping, and automatic matching can be restored at any time.
- **Pair highlighting**: Double-clicking a correspondence selects both its reference and destination footprints in PCB Editor for immediate visual confirmation.
- **Error Inspector**: Detailed breakdown of validation mismatches (**Detalles error**), listing missing, extra, locked, or mismatched components, plus deterministic, actionable suggestions.
- **Anchor Point Selection**: Choose between aligning using the **geometric centroid** (default) or a **specific key footprint** (e.g. `U1` → `U2`) as the fixed placement origin.
- **Free Rotation + Mirror**: Rotate each destination by any angle (with ±90° quick buttons) and optionally mirror the block layout about its vertical axis (**Espejo X**), rotating/mirroring both the relative block geometry and individual footprint orientations in lockstep.
- **Copper Replication**: Clones, rotates, and places copper tracks (`PCB_TRACK`, `PCB_ARC`), vias (`PCB_VIA`), zones (`PCB_ZONE`), and graphic shapes (`PCB_SHAPE`) from the reference block into all destination blocks, remapping internal nets to the destination pins. Items whose net has no valid destination mapping are skipped and reported.
- **Safe preview**: preview cancellation and application errors roll back temporary changes before the result is committed.
- **Overlap Warning**: Warns before applying when two planned destination blocks would end up overlapping spatially.
- **Courtyard collision check**: Preview validation uses `F.CrtYd`/`B.CrtYd` bounds when available and checks both destination-to-destination and destination-to-fixed-footprint collisions. Footprint geometry is used as a documented fallback when a courtyard is missing.
- **Native Grouping (PCB_GROUP)**: Option to automatically bundle aligned footprints and copper into native KiCad groups.
- **Interactive "Ver en PCB"**: Highlight and select reference or destination footprints directly in KiCad PCB Editor with a button or by double-clicking a table row.
- **Temporary Preview**: The **Vista previa** button renders the footprints and replicated copper in their calculated positions on the PCB and lets you confirm or cancel (reverting cleanly to original positions and removing preview copper).
- **Persistent Preview**: Preview remains active while the user inspects PCB Editor, with explicit **Aplicar** and **Cancelar vista previa** actions. Plugin-level undo is intentionally unavailable because removing already-adopted native `pcbnew` objects through SWIG can crash KiCad; cancel the preview before applying if the result is not correct.
- **Matrix Placement**: Destination origins can be distributed into a configurable row/column grid using millimetre spacing.
- **Copper Modes**: Choose footprints only, tracks/vias, or complete copper including zones and graphics.

The auto-detection intentionally uses deterministic PCB connectivity and geometry instead of a local AI model. This makes each decision reproducible and avoids introducing a probabilistic component into layout changes.

## Usage

1. Select all footprints in the reference block within KiCad PCB Editor.
2. Run **Block Aligner** from the PCB Editor toolbar or Tools menu.
3. Click **Capturar referencia**.
4. *(Optional)* Select an **Anchor component** from the dropdown if you want to align relative to a specific part instead of the block's centroid.
5. Click **Auto-detectar** to find all repeated blocks on the PCB automatically, or select a block in PCB Editor and click **Añadir selección**.
6. *(Optional)* Select a destination row and adjust its **Rotación** or **Espejo X**. If any block has errors, click **Detalles error** to inspect the cause.
7. Click **Vista previa**, inspect the temporary positions in KiCad, and choose **Aplicar** or **Cancelar vista previa**. Once applied, verify and save the PCB; Block Aligner does not retain native objects for a later plugin-level undo.

## Configuration

Optional JSON file that overrides built-in defaults (only known keys are read):

```text
<plugin_dir>/config.json
~/.config/Block_Aligner/config.json
```

Example `config.json`:

```json
{
  "track_collect_margin_nm": 2000000,
  "block_area_margin_nm": 3000000,
  "global_net_min_pads": 4,
  "power_net_names": ["GND", "VCC", "VDD", "+5V"],
  "replicate_tracks_default": false,
  "create_groups_default": true,
  "log_dir": "~/Block_Aligner"
}
```

See `config.py` for the full list of keys and their defaults.

## Project layout

```text
__init__.py    Plugin entry point (registers the action)
plugin.py      Facade + pcbnew.ActionPlugin
config.py      Defaults + JSON config loading
core.py        Pure deterministic geometry/matching (unit-testable, no pcbnew/wx)
discovery.py   Automatic repeated-block discovery
tracks.py      pcbnew integrations (positions, orientation, copper cloning, groups)
ui.py          wxPython dialogs
tests/         Unit tests for the pure logic (run with `python3 -m unittest discover -s tests`)
```

## Installation

Create a symbolic link (recommended for live development) or copy this directory to:

```text
~/.local/share/kicad/10.0/3rdparty/plugins/Block_Aligner
```

Restart KiCad PCB Editor after installation.

## Tests

The pure logic is covered by unit tests that do not require KiCad:

```bash
python3 -m unittest discover -s tests
```
