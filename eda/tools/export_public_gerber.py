"""Write public Gerber layers from the sanitized EasyEDA Pro PCB FILL objects.

This converter emits artwork and profile geometry from the same public PCB
source. It is not a claim of GUI Gerber export or EasyEDA DRC.
"""
from pathlib import Path
import json, re, zipfile, hashlib, sys
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
PCB = ROOT / "eda/project/pcb/PCB1.epcb2"
OUT = ROOT / "gerber"
W, H, R = 85.6, 54.0, 3.18
LAYER_FILES = {
    1: "Gerber_TopLayer.GTL",
    2: "Gerber_BottomLayer.GBL",
    5: "Gerber_TopSolderMaskLayer.GTS",
    6: "Gerber_BottomSolderMaskLayer.GBS",
}


def qcoord(mm):
    return int(round(mm * 100000))


def parse_native():
    latest = {}
    for line in PCB.read_text(encoding="utf-8-sig").splitlines():
        if "||" not in line:
            continue
        head_raw, body_raw = line.rstrip("|").split("||", 1)
        head = json.loads(head_raw)
        key = head.get("id", head["type"])
        body = json.loads(body_raw) if body_raw else None
        if key not in latest or head.get("ticket", 0) >= latest[key][0].get("ticket", 0):
            latest[key] = (head, body)
    live = [(h, d) for h, d in latest.values() if d is not None]
    counts = Counter(h["type"] for h, _ in live)
    if counts["FILL"] != 880:
        raise RuntimeError(f"Expected 880 art fills, found {counts['FILL']}")
    for absent in ("PAD", "VIA", "HOLE", "COMPONENT", "TEXT", "IMAGE", "PICTURE", "TRACK", "SLOTREGION"):
        if counts[absent]:
            raise RuntimeError(f"Unexpected {absent} objects: {counts[absent]}")
    layers = {n: [] for n in LAYER_FILES}
    for head, data in live:
        if head["type"] != "FILL":
            continue
        layer = data["layerId"]
        if layer not in layers:
            raise RuntimeError(f"Unexpected art layer {layer}")
        flat = [v for v in data["path"][0] if isinstance(v, (int, float))]
        pts = [(qcoord(x * .0254) / 100000, qcoord(y * .0254) / 100000)
               for x, y in zip(flat[::2], flat[1::2])]
        clean = []
        for p in pts:
            if not clean or p != clean[-1]:
                clean.append(p)
        if len(clean) > 1 and clean[-1] == clean[0]:
            clean.pop()
        poly = Polygon(clean)
        if not poly.is_valid or poly.area <= 0:
            raise RuntimeError(f"Invalid rounded FILL geometry {head.get('id')}")
        layers[layer].append(poly)
    expected = {1: 230, 5: 230, 2: 210, 6: 210}
    if {k: len(v) for k, v in layers.items()} != expected:
        raise RuntimeError("Unexpected layer object counts")
    for copper, mask in ((1, 5), (2, 6)):
        if unary_union(layers[copper]).symmetric_difference(unary_union(layers[mask])).area > 1e-10:
            raise RuntimeError("Copper and solder-mask geometry differ")
    return layers


def fmt_xy(x, y):
    return f"X{qcoord(x)}Y{qcoord(y)}"


def layer_gerber(layer, polys):
    side = {1: "Top copper", 2: "Bottom copper", 5: "Top solder mask openings", 6: "Bottom solder mask openings"}[layer]
    out = [f"G04 {side}; generated from the sanitized native PCB FILL geometry*",
           "%FSLAX45Y45*%", "%MOMM*%", "%LPD*%", "G01*"]
    for poly in polys:
        ring = list(poly.exterior.coords)
        if ring[-1] == ring[0]:
            ring.pop()
        out.append("G36*")
        out.append(fmt_xy(*ring[0]) + "D02*")
        for x, y in ring[1:]:
            out.append(fmt_xy(x, y) + "D01*")
        out.append("G37*")
    out.append("M02*")
    return ("\n".join(out) + "\n").encode("ascii")


def outline_gerber():
    # Closed 85.6 x 54.0 mm profile, R3.18 mm, matching the native BOARD/POLY.
    return ("G04 Public profile converted from native PCB BOARD dimensions*\n"
            "%FSLAX45Y45*%\n%MOMM*%\n%ADD10C,0.15*%\nG75*\nG54D10*\n"
            "G01X318000Y0D02*\nG01X8242000Y0D01*\n"
            "G02X8560000Y-318000I0J-318000D01*\n"
            "G01X8560000Y-5082000D01*\n"
            "G02X8242000Y-5400000I-318000J0D01*\n"
            "G01X318000Y-5400000D01*\n"
            "G02X0Y-5082000I0J318000D01*\n"
            "G01X0Y-318000D01*\n"
            "G02X318000Y0I318000J0D01*\nM02*\n").encode("ascii")


def parse_regions(raw):
    text = raw.decode("ascii")
    regions, current = [], None
    for line in text.splitlines():
        if line == "G36*":
            if current is not None:
                raise RuntimeError("Nested Gerber region")
            current = []
        elif line == "G37*":
            if current is None or len(current) < 3:
                raise RuntimeError("Malformed Gerber region")
            regions.append(Polygon(current))
            current = None
        elif current is not None:
            m = re.fullmatch(r"X(-?\d+)Y(-?\d+)D0([12])\*", line)
            if not m:
                raise RuntimeError(f"Unexpected Gerber region command {line}")
            current.append((int(m.group(1)) / 100000, int(m.group(2)) / 100000))
    if current is not None:
        raise RuntimeError("Unclosed Gerber region")
    return regions


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    layers = parse_native()
    members = {}
    for layer, filename in LAYER_FILES.items():
        members[filename] = layer_gerber(layer, layers[layer])
    members["Gerber_BoardOutlineLayer.GKO"] = outline_gerber()
    parsed = {layer: parse_regions(members[LAYER_FILES[layer]]) for layer in LAYER_FILES}
    checks = {}
    for copper, mask, side in ((1, 5, "front"), (2, 6, "back")):
        cu, ma = unary_union(parsed[copper]), unary_union(parsed[mask])
        if cu.symmetric_difference(ma).area != 0:
            raise RuntimeError(f"Gerber copper/mask mismatch on {side}")
        src = unary_union(layers[copper])
        if src.symmetric_difference(cu).area > .0001:
            raise RuntimeError(f"Quantized Gerber geometry differs from native on {side}")
        checks[side] = {
            "regions": len(parsed[copper]),
            "native_gerber_symmetric_difference_mm2": src.symmetric_difference(cu).area,
            "copper_mask_symmetric_difference_mm2": cu.symmetric_difference(ma).area,
            "exposed_area_mm2": cu.area,
        }
    for name, raw in members.items():
        (OUT / name).write_bytes(raw)
    archive = OUT / "Cassell_College_PCB_Card_Gerber.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in members.items():
            z.writestr(name, raw)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or set(z.namelist()) != set(members):
            raise RuntimeError("Gerber archive verification failed")
        for name, raw in members.items():
            if z.read(name) != raw:
                raise RuntimeError(f"Gerber archive changed {name}")
    report = {
        "status": "GEOMETRY_VALIDATED_GUI_DRC_AND_FACTORY_REVIEW_NOT_PERFORMED",
        "source": "eda/project/pcb/PCB1.epcb2",
        "board": {"width_mm": W, "height_mm": H, "corner_radius_mm": R, "layers": 2},
        "gerber_files": sorted(members),
        "drill_files": [],
        "checks": checks,
        "outline": {"closed": True, "profile": "one rounded rectangle, R3.18 mm", "no_holes": True},
        "gerber_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in members.items()},
        "zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "note": "Gerbers were written from the public native PCB FILL records. They are not a direct EasyEDA GUI export. Reopen and run EasyEDA DRC before treating this public revision as production-ready."
    }
    (OUT / "Gerber_Validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "zip_bytes": archive.stat().st_size, "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
