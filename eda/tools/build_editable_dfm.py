"""Preserve editable text and R1 object groups in a separate manufacturing-adapted source."""
from pathlib import Path
import json, copy, importlib.util, argparse, re, hashlib
import xml.etree.ElementTree as ET
from build_artwork_geometry import compose,transform_value

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('r1_builder',ROOT/'design/build_design.py')
R1=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(R1)
NS=R1.NS
DEFAULT_GEOMETRY=ROOT/'eda/artwork_geometry_dfm.json'

def polygon_path(p):
    d=[]
    for ring in [p['outer']]+p['holes']:
        d.append('M'+' L'.join(f'{x:.7f},{y:.7f}' for x,y in ring)+' Z')
    return ' '.join(d)

def build(geometry_path=None,tag='dfm'):
    """Create an independently named SVG family; original R1 stays read-only."""
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',tag):
        raise ValueError('Output tag must contain only letters, numbers, underscores or hyphens.')
    geometry=Path(geometry_path).resolve() if geometry_path is not None else DEFAULT_GEOMETRY
    raw=geometry.read_bytes();data=json.loads(raw)
    source_name=str(geometry.relative_to(ROOT)) if geometry.is_relative_to(ROOT) else str(geometry)
    output_dir=ROOT/'eda/geometry';output_dir.mkdir(parents=True,exist_ok=True)
    for side in ['front','back']:
        svg=ET.parse(ROOT/'design'/f'{side}_editable.svg').getroot()
        for title in svg.findall('{'+NS+'}title'):
            title.text=f'Cassell College {side} — R1 manufacturing adaptation {tag} — stage two review'
        for metadata in svg.findall('{'+NS+'}metadata'):
            metadata.text=json.dumps({'phase':2,'source_revision':'R1','status':'manufacturing adaptation source, not native PCB','physical_parameters_final':False,'geometry_source':source_name,'geometry_source_sha256':hashlib.sha256(raw).hexdigest(),'output_tag':tag})
        if side=='back':
            g=next(n for n in svg.iter() if n.get('id')=='latin-motto')
            origins=json.loads(g.get('data-x-origins'))
            # Retain the existing R1-to-DFM tracking adjustment. Non-space glyph
            # offsets are also retained verbatim if present in the input JSON.
            glyphs={int(c['id'].rsplit('-',1)[1]):c for c in data['sides'][side]['components'] if c['id'].startswith('latin-motto-glyph-')}
            delta=next((c.get('stage2_adjustment',{}).get('tracking_delta_mm') for c in glyphs.values() if c.get('stage2_adjustment',{}).get('tracking_delta_mm') is not None),.06)
            origins=[v+glyphs.get(i,{}).get('stage2_adjustment',{}).get('dx_mm',(i-(len(origins)-1)/2)*delta) for i,v in enumerate(origins)]
            g.set('data-x-origins',json.dumps(origins));g.set('data-tracking-mm',str(.28+delta))
            g.find('{'+NS+'}text').set('x',' '.join(f'{v:.7f}' for v in origins))
        # A v2 clearance setback is a subtraction, so it cannot be represented
        # by an additive gold patch. Replace only that source element with its
        # audited filled path in the same original semantic group. Convert the
        # world geometry back to the original parent's local coordinates, so
        # moving the dragon group also moves every repaired dragon segment.
        for c in data['sides'][side]['components']:
            if not c.get('editable_svg_world_path_replacement'):continue
            parent_map={child:parent for parent in svg.iter() for child in parent}
            original=next((n for n in svg.iter() if n.get('id')==c['id']),None)
            if original is None:raise ValueError('Source SVG replacement ID missing: '+c['id'])
            original_parent=parent_map[original]
            chain=[];ancestor=original_parent
            while True:
                chain.append(ancestor)
                if ancestor is svg:break
                ancestor=parent_map[ancestor]
            matrix=(1.,0.,0.,1.,0.,0.)
            for ancestor in reversed(chain):matrix=compose(matrix,transform_value(ancestor.get('transform')))
            a,b,cc,d,e,f=matrix;det=a*d-b*cc
            if abs(det)<1e-15:raise ValueError('Singular source SVG transform')
            inverse=(d/det,-b/det,-cc/det,a/det,(cc*f-d*e)/det,(b*e-a*f)/det)
            def local_ring(ring):
                return [[inverse[0]*x+inverse[2]*y+inverse[4],inverse[1]*x+inverse[3]*y+inverse[5]] for x,y in ring]
            original_parent.remove(original)
            replacement=R1.group(original_parent,c['id']+'-dfm-local-replacement',fill=R1.GOLD,
                stroke='none',data_source_id=c['id'],data_semantic_group=c['groups'][0],
                data_manufacturing_adjustment='local-subtractive-clearance')
            for index,p in enumerate(c['polygons']):
                local={'outer':local_ring(p['outer']),'holes':[local_ring(ring) for ring in p['holes']]}
                R1.el('path',replacement,id=c['id']+f'-dfm-part-{index}',d=polygon_path(local),fill_rule='evenodd')
        for c in data['sides'][side]['components']:
            if 'stage2' not in c['id']:continue
            parent=next((n for n in svg.iter() if n.get('id')==c['groups'][0]),svg)
            # Hole patches are reconstructed from JSON coordinates rounded to 1 nm.
            # A 2 nm overlap removes microscopic seams against the higher-precision
            # original curves, far below the 0.003 mm comparison tolerance.
            fills_hole=c.get('stage2_adjustment',{}).get('kind')=='fill_tiny_nontext_negative_hole'
            g=R1.group(parent,c['id'],fill=R1.GOLD,
                stroke=R1.GOLD if fills_hole else 'none',stroke_width=.000004 if fills_hole else 0,
                stroke_linejoin='round',data_manufacturing_adjustment='true')
            for p in c['polygons']:R1.el('path',g,d=polygon_path(p),fill_rule='evenodd')
        R1.write(svg,output_dir/f'{side}_editable_{tag}.svg')
        outlined=R1.outline_text(svg)
        R1.write(outlined,output_dir/f'{side}_outlined_{tag}.svg')
        art=copy.deepcopy(outlined)
        for node in list(art):
            if node.get('id')=='preview-green-substrate':art.remove(node)
        R1.write(art,output_dir/f'{side}_artwork_{tag}.svg')
    print(f'Created separate manufacturing-adapted SVG sources ({tag}); original R1 unchanged.')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--geometry',type=Path,help='Geometry JSON input; defaults to retained DFM geometry.')
    parser.add_argument('--tag',default='dfm',help='Output-family tag, for example dfm_v2.')
    args=parser.parse_args()
    build(args.geometry,args.tag)
