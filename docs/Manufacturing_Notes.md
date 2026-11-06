# Manufacturing and validation notes

## Intended board

- 2-layer FR-4 decorative PCB
- 85.6 × 54.0 mm outline, R3.18 mm corners
- 1.0 mm board thickness and 1 oz outer copper as targets
- Black solder mask and ENIG on both sides as targets
- No components, circuit nets, vias, drilled holes, slots, or silk artwork

These finish and material choices must be selected and confirmed with the board manufacturer. Gerbers only define layer geometry and profile.

## Public geometry

The public copy uses the same layout and design language, with the private name and student number changed to **RILEY MORGAN** and **CC-0001**. SVG, geometry JSON, native PCB, Gerber, and flat gallery previews were regenerated from that public data. The EasyEDA project, PCB document, and DFM polygon source are packaged together in `eda/project/EasyEDA_Editable_Source.zip`; run `scripts/restore_easyeda_source.ps1` after cloning to restore their editable working paths. The original local design and actual-production files were not edited.

The generated EasyEDA Pro PCB source (inside the source archive) has 880 solid-fill artwork records: 230 front copper, 230 matching top-mask openings, 210 back copper, and 210 matching bottom-mask openings. The profile is one closed rounded rectangle. The board has no drill features, and no drill file is included.

## Gerber validation performed

The included converter reads the public native PCB fill records and writes the four artwork layers. The exported regions were parsed back from the generated Gerber files and compared with the same native geometry:

| Face | Regions | Native/Gerber geometry difference | Copper/mask difference |
|---|---:|---:|---:|
| Front | 230 | 0 mm² after 0.00001 mm coordinate quantization | 0 mm² |
| Back | 210 | 0 mm² after 0.00001 mm coordinate quantization | 0 mm² |

The GKO profile is an 85.6 × 54.0 mm closed outline with R3.18 mm corners. The ZIP was reopened and each member compared byte-for-byte with the generated layer files. There are no unsupported supplementary silk, drill, or image layers in the package.

## Checks not completed for the public revision

This public PCB has not been reopened in the EasyEDA Pro GUI for a fresh DRC or GUI export. The prior private board's historical DRC result does not apply to this sanitized revision. The custom geometric checks are not a substitute for EasyEDA DRC or manufacturer review.

Before production, run `scripts/restore_easyeda_source.ps1`, then open `eda/project/Cassell_College_PCB_Card_Public.eprj3` in EasyEDA Pro, inspect both faces and run DRC. Then check the exported production files and confirm profile recognition, black mask, ENIG, thickness, and copper weight in the manufacturer's ordering flow. No factory DFM review or order has been made for this public revision.

## Rebuild dependencies

Use Python 3.13 or a compatible recent Python and install `requirements.txt`. SVG font outlines use Georgia, Cambria, and Calibri fonts available on Windows; they are not embedded. The outlined SVG variants preserve their appearance if those fonts are unavailable.
