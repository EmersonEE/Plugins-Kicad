# Block Aligner

KiCad PCB Editor action plugin that copies relative footprint positions and
orientations from one selected reference block to one or more destination blocks.

## Features

- **Component Matching**: Matches components by value, library footprint, pad count, and internal block connectivity. Net names and net codes are ignored, so equivalent blocks can use different nets. Equivalent components are paired as part of the complete block geometry, preserving relationships such as `R1-D1`, `R2-D2`, etc.
- **Auto-Discovery**: One-click **Auto-detectar** scans the entire board to automatically identify all matching multi-channel blocks (via hierarchical sheets or connectivity graphs). Candidates are constrained to the physical area implied by the reference block and are not completed with unrelated distant footprints.
- **Error Inspector**: Detailed breakdown of validation mismatches (**Detalles error**), listing missing, extra, locked, or mismatched components.
- **Anchor Point Selection**: Choose between aligning using the **geometric centroid** (default) or a **specific key footprint** (e.g. `U1` $\rightarrow$ `U2`) as the fixed placement origin.
- **Rigid Block Rotation**: Supports **0° (default)**, **90°**, **180°**, and **270°** rotation per destination block, rotating both the relative block geometry and individual footprint orientations in lockstep.
- **Tracks & Vias Replication**: Automatically clones, rotates, and places copper tracks (`PCB_TRACK`, `PCB_ARC`) and vias (`PCB_VIA`) from the reference block into all destination blocks, seamlessly remapping internal nets to the destination pins.
- **Native Grouping (PCB_GROUP)**: Option to automatically bundle aligned footprints, tracks, and vias into native KiCad groups upon applying.
- **Interactive "Ver en PCB"**: Highlight and select reference or destination footprints directly in KiCad PCB Editor with a button or by double-clicking a table row.
- **Safe Transactional Preview**: The **Vista previa** button temporarily renders the footprints and replicated tracks/vias in their calculated positions on the PCB and lets you confirm or cancel (reverting cleanly to original positions and removing preview tracks).

The auto-detection intentionally uses deterministic PCB connectivity and geometry instead of a local AI model. This makes each decision reproducible and avoids introducing a probabilistic component into layout changes.

The matching logic has been tested with repeated blocks containing both 2 and 8 footprints, including multiple equivalent component types and blocks with different physical spacing.

## Usage

1. Select all footprints in the reference block within KiCad PCB Editor.
2. Run **Block Aligner** from the PCB Editor toolbar or Tools menu.
3. Click **Capturar referencia**.
4. *(Optional)* Select an **Anchor component** from the dropdown if you want to align relative to a specific part instead of the block's centroid.
5. Click **Auto-detectar** to find all repeated blocks on the PCB automatically, or select a block in PCB Editor and click **Añadir selección**.
6. *(Optional)* Select a destination row in the table and adjust its **Rotación** (`0°`, `90°`, `180°`, `270°`). If any block has errors, click **Detalles error** to inspect the cause.
7. Click **Vista previa**, inspect the temporary positions in KiCad, and confirm to apply or cancel to restore.

## Installation

Create a symbolic link (recommended for live development) or copy this directory to:

```text
~/.local/share/kicad/10.0/3rdparty/plugins/Block_Aligner
```

Restart KiCad PCB Editor after installation.
