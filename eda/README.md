# EasyEDA Pro project

The editable EasyEDA Pro folder project is packaged in `project/EasyEDA_Editable_Source.zip`. From the repository root, run `scripts/restore_easyeda_source.ps1` to extract `project/Cassell_College_PCB_Card_Public.eprj3`, `project/pcb/PCB1.epcb2`, and `artwork_geometry_dfm_v2.json` into the expected folders. Then open the `.eprj3` file in EasyEDA Pro.

The project contains a PCB document only: no schematic, panel, or electrical circuit. The PCB was rebuilt from the sanitized DFM v2 polygons and structurally checked, but this public release was not reopened in the EasyEDA GUI or run through a fresh DRC. See `../docs/Manufacturing_Notes.md` before fabrication.
