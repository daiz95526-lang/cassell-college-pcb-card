# Design and validation utilities

- `build_artwork_geometry.py` converts the editable SVG design into millimetre-based polygon geometry.
- `repair_artwork_geometry.py`, `repair_neck_geometry.py`, and `build_editable_dfm.py` apply the documented local DFM adjustments.
- `export_public_gerber.py` writes copper, solder-mask, and board-outline Gerber layers from the sanitized EasyEDA Pro native PCB geometry.
- `render_public_previews.py` creates the flat front/back gallery images from the generated Gerber regions.

The Gerber converter is a transparent helper, not EasyEDA's GUI exporter and not a DRC tool. The supplied native project is editable in EasyEDA Pro, but this public copy was not reopened in the GUI during release preparation. Run EasyEDA DRC and review the factory preview before fabrication.
