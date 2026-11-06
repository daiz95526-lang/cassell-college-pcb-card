"""Prepare conservative local stage-two fixes while retaining all R1 sources.

Only the Latin motto tracking and sub-0.12 mm near contacts in non-text art
are changed. The JSON remains millimetres, outside-face view, no mirror.
"""
from pathlib import Path
import json, math, hashlib, copy
import xml.etree.ElementTree as ET
from build_artwork_geometry import (ROOT, NS, ROUND_SEGMENTS, load_artwork,
    polygons, geometry_json, svg_path, metrics, Point, LineString, Polygon,
    unary_union, nearest_points)
from shapely.affinity import translate

TARGET_GAP=.12
BRIDGE_WIDTH=.18
TRACKING_DELTA=.06
ART_GROUPS=('world-tree','dragon','architecture','frame')

def find_sources(point,components):
    p=Point(point)
    matches=[]
    for c in components:
        d=c['geometry'].distance(p)
        if d<.004:
            matches.append({'id':c['id'],'groups':c['groups'],'text':c['text'],'distance_mm':d})
    return sorted(matches,key=lambda x:x['distance_mm'])[:6]

def semantic_groups(matches):
    return {a for c in matches for a in c['groups'] if a in ART_GROUPS}

def holes(g):return sum(len(p.interiors) for p in polygons(g))

def glyph_probe(components):
    rows=[]
    for c in components:
        if 'glyph-' not in c['id']:continue
        g=c['geometry'];e=g.buffer(-.05,quad_segs=ROUND_SEGMENTS)
        opened=e.buffer(.05,quad_segs=ROUND_SEGMENTS)
        counters=[]
        for p in polygons(g):
            for h in p.interiors:
                hg=Polygon(h);counters.append({'area_mm2':hg.area,'survives_0_10_mm_diameter_probe':not hg.buffer(-.05,quad_segs=ROUND_SEGMENTS).is_empty})
        rows.append({'id':c['id'],'text':c['text'],'original_connected_parts':len(polygons(g)),
            'parts_after_inward_offset_0_05_mm':len(polygons(e)),
            'all_parts_survive':not e.is_empty and len(polygons(g))==len(polygons(e)),
            'opening_lost_area_mm2':g.difference(opened).area,
            'opening_lost_fraction':g.difference(opened).area/g.area,
            'counter_count':holes(g),'counters':counters})
    return {'diameter_mm':.10,'method':'Inward 0.05 mm offset connectivity/vanishing probe plus opening loss, and identical probe inside glyph counters.',
        'narrow_neck_or_entire_fragment_below_probe_detected':any(not r['all_parts_survive'] for r in rows),
        'counter_erased_by_probe_detected':any(not x['survives_0_10_mm_diameter_probe'] for r in rows for x in r['counters']),
        'caveat':'No sub-0.10 mm neck was detected by this probe. Sharp serif tips and rounded ends can still have local widths below 0.10 mm; this is not a medial-axis proof or EDA DRC.',
        'glyphs':rows}

def write_dfm_svg(side,cs):
    ET.register_namespace('',NS)
    root=ET.Element('{'+NS+'}svg',width='85.6mm',height='54mm',viewBox='0 0 85.6 54')
    ET.SubElement(root,'{'+NS+'}title').text=f'Cassell College R1 stage-two local manufacturing adjustments: {side}'
    ET.SubElement(root,'{'+NS+'}desc').text='R1 original retained; only motto tracking and short local bridges changed. Not a Gerber or PCB DRC verdict.'
    for c in cs:
        ET.SubElement(root,'{'+NS+'}path',id=c['id'],d=svg_path(c['geometry']),fill='#c8a65c',**{'fill-rule':'evenodd'})
    ET.ElementTree(root).write(ROOT/'eda/geometry'/f'{side}_dfm.svg',encoding='utf-8',xml_declaration=True)

def main():
    out={'units':'mm','view':'Each face read from its outside; bottom mirror not applied.','source_revision':'R1 + minimal stage-two geometry adjustments','target_disjoint_island_gap_mm':TARGET_GAP,'sides':{}}
    manifest={'scope':'Local manufacturing preparation, not a redesign or EDA DRC. Original R1 SVG and original geometry files remain unchanged.',
        'gap_target_mm':TARGET_GAP,'bridge_width_mm':BRIDGE_WIDTH,'motto_tracking_before_mm':.28,'motto_tracking_after_mm':.34,
        'sides':{}}
    for side in ['front','back']:
        source,cs,original=load_artwork(side);changes=[];near_before=[]
        # Keep component provenance. Each non-space glyph has the original string index in its ID.
        for c in cs:
            if c['id'].startswith('latin-motto-glyph-'):
                idx=int(c['id'].rsplit('-',1)[1]);dx=TRACKING_DELTA*(idx-(len(c['text'])-1)/2)
                c['geometry']=translate(c['geometry'],xoff=dx)
                c['stage2_adjustment']={'kind':'tracking','dx_mm':dx,'tracking_delta_mm':TRACKING_DELTA}
        if side=='back':
            changes.append({'kind':'motto_tracking','text':'PER ASPERA AD ASTRA','old_mm':.28,'new_mm':.34,'glyph_shape_changed':False,'recentered':True,'max_glyph_displacement_mm':TRACKING_DELTA*(len('PER ASPERA AD ASTRA')-1)/2})
        # Join only almost-touching pieces within the same non-text artistic group.
        # Connections are explicit short capsules, avoiding the hairline necks a generic closing can create.
        for iteration in range(20):
            union=unary_union([c['geometry'] for c in cs]);ps=polygons(union);bridges=[]
            for i,a in enumerate(ps):
                for j in range(i+1,len(ps)):
                    b=ps[j];gap=a.distance(b)
                    if gap>=TARGET_GAP-1e-8:continue
                    pa,pb=nearest_points(a,b);aa=(pa.x,pa.y);bb=(pb.x,pb.y)
                    ma=find_sources(aa,cs);mb=find_sources(bb,cs)
                    shared=semantic_groups(ma)&semantic_groups(mb)
                    if not shared:
                        near_before.append({'gap_mm':gap,'points_mm':[aa,bb],'a':ma,'b':mb,'reason':'No common allowed non-text group; not bridged.'})
                        continue
                    group=next(g for g in ART_GROUPS if g in shared)
                    bridge=LineString([aa,bb]).buffer(BRIDGE_WIDTH/2,quad_segs=ROUND_SEGMENTS,cap_style=1)
                    bid=f'{side}-stage2-bridge-{sum(x.get("kind")=="short_bridge" for x in changes)+len(bridges)+1:03d}'
                    bridges.append({'id':bid,'tag':'path','groups':[group,'stage2-local-bridges'],'text':None,'source_stroke_mm':None,'fill_contours':1,'geometry':bridge,
                        'stage2_adjustment':{'kind':'short_bridge','old_gap_mm':gap,'width_mm':BRIDGE_WIDTH,'points_mm':[aa,bb],'sources_a':ma,'sources_b':mb}})
            if not bridges:break
            for c in bridges:
                cs.append(c);changes.append(c['stage2_adjustment']|{'id':c['id'],'bounds_mm':list(c['geometry'].bounds)})
        union=unary_union([c['geometry'] for c in cs]);tiny_holes=[]
        for island in polygons(union):
            for ring in island.interiors:
                hole=Polygon(ring)
                if not hole.buffer(-.05,quad_segs=ROUND_SEGMENTS).is_empty:continue
                touching=[c for c in cs if hole.boundary.distance(c['geometry'])<.002]
                # Text counters must survive untouched; the independent glyph probe tests them.
                if any(c['text'] is not None for c in touching):
                    raise ValueError('Refusing to fill a negative hole touching a text glyph')
                shared={g for c in touching for g in c['groups'] if g in ART_GROUPS}
                if not shared:raise ValueError('Tiny negative hole has no non-text artistic provenance')
                group=next(g for g in ART_GROUPS if g in shared)
                hid=f'{side}-stage2-filled-negative-hole-{len(tiny_holes)+1:03d}'
                change={'kind':'fill_tiny_nontext_negative_hole','id':hid,'group':group,
                    'hole_area_mm2':hole.area,'bounds_mm':list(hole.bounds),
                    'probe_diameter_mm':.10,'source_ids':[c['id'] for c in touching]}
                tiny_holes.append({'id':hid,'tag':'path','groups':[group,'stage2-filled-negative-holes'],
                    'text':None,'source_stroke_mm':None,'fill_contours':1,'geometry':hole,'stage2_adjustment':change})
        for c in tiny_holes:cs.append(c);changes.append(c['stage2_adjustment'])
        final=unary_union([c['geometry'] for c in cs]);stats=metrics(side,cs,final)
        delta=original.symmetric_difference(final);added=final.difference(original);removed=original.difference(final)
        # Assert letter shapes/counters have survived untouched; only motto translations are allowed.
        counters_before={c['id']:holes(c['geometry']) for c in load_artwork(side)[1] if 'glyph-' in c['id']}
        counters_after={c['id']:holes(c['geometry']) for c in cs if 'glyph-' in c['id']}
        assert counters_before==counters_after, 'A glyph counter changed'
        assert stats['minimum_disjoint_island_gap_mm']>=TARGET_GAP-1e-6,stats['minimum_disjoint_island_gap_mm']
        write_dfm_svg(side,cs)
        out['sides'][side]={'source':str(source.relative_to(ROOT)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'union_polygons':geometry_json(final),
            'components':[{k:v for k,v in c.items() if k!='geometry'}|{'polygons':geometry_json(c['geometry'])} for c in cs]}
        manifest['sides'][side]={'changes':changes,'unresolved_near_contacts':near_before,'glyph_counter_counts_unchanged':True,
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'original_area_mm2':original.area,'final_area_mm2':final.area,'added_area_mm2':added.area,'removed_area_mm2':removed.area,
            'symmetric_difference_area_mm2':delta.area,'symmetric_difference_over_original_percent':100*delta.area/original.area,
            'difference_bounds_mm':list(delta.bounds) if not delta.is_empty else None,
            'original_bounds_mm':list(original.bounds),'final_bounds_mm':list(final.bounds),
            'glyph_0_10_mm_probe':glyph_probe(cs),'post_repair_metrics':stats}
        print(side,'changes',len(changes),'area',final.area,'min disjoint gap',stats['minimum_disjoint_island_gap_mm'],'xor area',delta.area)
    a=manifest['sides']['front']['final_area_mm2'];b=manifest['sides']['back']['final_area_mm2'];board=85.6*54-(4-math.pi)*3.18**2
    manifest['area_summary']={'rounded_board_area_mm2':board,'front_mm2':a,'back_mm2':b,'sum_mm2':a+b,'front_percent':a/board*100,'back_percent':b/board*100,'sum_over_single_board_percent':(a+b)/board*100,'sum_over_two_faces_percent':(a+b)/(2*board)*100,'note':'Artwork geometry estimates, before native EDA mask/copper validation; not Gerber-derived.'}
    for dest,value,pretty in [(ROOT/'eda/artwork_geometry_dfm.json',out,False),(ROOT/'reports/stage2_local_repair_manifest.json',manifest,True)]:
        temp=dest.with_suffix(dest.suffix+'.tmp')
        temp.write_text(json.dumps(value,indent=2 if pretty else None,separators=None if pretty else (',',':'),ensure_ascii=False),encoding='utf-8')
        temp.replace(dest)

if __name__=='__main__':main()
