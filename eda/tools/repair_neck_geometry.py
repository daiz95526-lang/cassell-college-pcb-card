"""Independent DFM v2: ten local necks and black-mask clearance margin.

R1, DFM1 and the live GUI project remain read-only. Both color comparisons
must use this same geometry if it is later applied through the EDA GUI.
"""
from pathlib import Path
from datetime import datetime
import sys, json, hashlib, copy, math
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_artwork_geometry import (ROOT, NS, ROUND_SEGMENTS, polygons, geometry_json,
    svg_path, metrics, Point, LineString, Polygon, unary_union, nearest_points)
from shapely.affinity import translate
from shapely import maximum_inscribed_circle
import xml.etree.ElementTree as ET

SOURCE=ROOT/'eda/artwork_geometry_dfm.json'
OUT=ROOT/'eda/artwork_geometry_dfm_v2.json'
R=.05

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def geom(rows): return unary_union([Polygon(p['outer'],p.get('holes',[])) for p in rows])
def nholes(g): return sum(len(p.interiors) for p in polygons(g))
def holes_probe(g,radius=R):
    return [{'area_mm2':Polygon(r).area,'bounds_mm':list(Polygon(r).bounds)}
            for p in polygons(g) for r in p.interiors
            if Polygon(r).buffer(-radius,quad_segs=ROUND_SEGMENTS).is_empty]
def feature_probe(g):
    splits=[];vanished=[];islands=polygons(g)
    for i,p in enumerate(islands):
        e=polygons(p.buffer(-R,quad_segs=ROUND_SEGMENTS))
        if not e:vanished.append({'island':i,'area_mm2':p.area,'bounds_mm':list(p.bounds)})
        if len(e)>1:splits.append({'island':i,'area_mm2':p.area,'bounds_mm':list(p.bounds),'parts_after_erosion':len(e)})
    opening=g.buffer(-R,quad_segs=ROUND_SEGMENTS).buffer(R,quad_segs=ROUND_SEGMENTS)
    closing=g.buffer(R,quad_segs=ROUND_SEGMENTS).buffer(-R,quad_segs=ROUND_SEGMENTS)
    smallest=sorted(islands,key=lambda p:p.area)[:5]
    return {'probe_diameter_mm':.1,'islands':len(islands),'holes':nholes(g),
        'split_islands':splits,'entirely_vanished_islands':vanished,
        'opening_loss_mm2':g.difference(opening).area,
        'closing_added_negative_space_mm2':closing.difference(g).area,
        'negative_holes_unable_to_hold_0_10_mm_probe':holes_probe(g),
        'negative_holes_unable_to_hold_0_13_mm_probe':holes_probe(g,.065),
        'negative_holes_unable_to_hold_0_15_mm_probe':holes_probe(g,.075),
        'smallest_islands':[{'area_mm2':p.area,'bounds_mm':list(p.bounds),'bounding_box_dimensions_mm':[p.bounds[2]-p.bounds[0],p.bounds[3]-p.bounds[1]]} for p in smallest]}

def critical_neck(p,satellite,major):
    lo,hi=0.0,.05
    for _ in range(15):
        mid=(lo+hi)/2
        connected=any(q.intersects(satellite) and q.intersects(major)
                      for q in polygons(p.buffer(-mid,quad_segs=ROUND_SEGMENTS)))
        if connected:lo=mid
        else:hi=mid
    return {'estimated_critical_full_width_mm':2*hi,'binary_search_width_resolution_mm':.1/(2**15),
        'method':'Largest erosion radius retaining a path between surviving satellite and main-body cores; diagnostic rather than exact medial-axis width.'}

def main():
    protected=[p for folder in ['design','assets'] for p in (ROOT/folder).rglob('*') if p.is_file()]
    protected += [SOURCE]
    if (ROOT/'eda/Cassell_R1_2L.native.epcb2').exists(): protected.append(ROOT/'eda/Cassell_R1_2L.native.epcb2')
    original_hashes={str(p.relative_to(ROOT)):sha(p) for p in protected}
    data=json.loads(SOURCE.read_text(encoding='utf8'));out=copy.deepcopy(data)
    manifest={'recorded_at':datetime.now().astimezone().isoformat(),'source':str(SOURCE.relative_to(ROOT)),
        'source_sha256':sha(SOURCE),'scope':'Independent DFM v2; six leaf necks, four stone joints, motto tracking and one tiny local dragon setback only. No R1 redesign, no GUI edit, no Gerber.',
        'bridge_width_mm':.18,'minimum_disjoint_island_gap_target_mm':.15,
        'black_mask_reason':'Current official black 1oz mask spacing >=0.13 mm; 0.15 mm design target leaves nominal margin. Production Gerber width semantics remain to be verified.',
        'sides':{},'protected_source_hashes':original_hashes}
    probes={'scope':'0.10 mm morphological diagnostics on DFM1 and independent v2. No live-project or Gerber DRC claim.','sides':{}}
    for side,s in data['sides'].items():
        baseline=geom(s['union_polygons']);cs=copy.deepcopy(s['components'])
        source_cs=[(c,geom(c['polygons'])) for c in cs];patches=[];changes=[]
        before=feature_probe(baseline)
        for island in polygons(baseline):
            eroded=sorted(polygons(island.buffer(-R,quad_segs=ROUND_SEGMENTS)),key=lambda p:p.area,reverse=True)
            for sat in eroded[1:]:
                major=eroded[0]
                aa,bb=nearest_points(sat.buffer(-.02,quad_segs=ROUND_SEGMENTS),major.buffer(-.02,quad_segs=ROUND_SEGMENTS))
                patch=LineString([aa,bb]).buffer(.09,quad_segs=ROUND_SEGMENTS)
                matching=sorted([(sat.intersection(g).area,c) for c,g in source_cs],key=lambda row:row[0],reverse=True)
                c=matching[0][1];group='world-tree' if side=='front' else 'architecture'
                assert group in c['groups'] and c.get('text') is None
                cid=f'{side}-stage2-v2-neck-bridge-{len(patches)+1:03d}'
                change={'kind':'neck_bridge','id':cid,'group':group,'source_id':c['id'],
                    'bridge_width_mm':.18,'bridge_axis_length_mm':aa.distance(bb),
                    'axis_points_mm':[[aa.x,aa.y],[bb.x,bb.y]],'bounds_mm':list(patch.bounds),
                    'added_area_mm2':patch.difference(baseline).area,**critical_neck(island,sat,major)}
                patches.append(patch);changes.append(change)
                cs.append({'id':cid,'tag':'path','groups':[group,'stage2-v2-neck-bridges'],'text':None,'source_stroke_mm':None,'fill_contours':1,
                    'stage2_adjustment':change,'polygons':geometry_json(patch)})
        assert len(patches)==(6 if side=='front' else 4)
        neck_only=unary_union([baseline]+patches)
        assert not feature_probe(neck_only)['split_islands']
        final=neck_only
        if side=='back':
            old_motto=unary_union([g for c,g in source_cs if c['id'].startswith('latin-motto-glyph-')])
            motto_region=old_motto.envelope.buffer(.01)
            assert all(g.intersection(motto_region).is_empty for c,g in source_cs if not c['id'].startswith('latin-motto-glyph-'))
            # Retain every glyph shape; only add 0.02 mm tracking, re-centered.
            for c in cs:
                if not c['id'].startswith('latin-motto-glyph-'):continue
                idx=int(c['id'].rsplit('-',1)[1]);dx=.02*(idx-(len(c['text'])-1)/2)
                c['polygons']=geometry_json(translate(geom(c['polygons']),xoff=dx))
                old=c.get('stage2_adjustment',{})
                c['stage2_adjustment']=old|{'kind':'tracking','dx_mm':old.get('dx_mm',0)+dx,'tracking_delta_mm':.08,
                    'v2_additional_dx_mm':dx,'v2_tracking_before_mm':.34,'v2_tracking_after_mm':.36}
            changes.append({'kind':'motto_tracking','before_mm':.34,'after_mm':.36,'max_additional_glyph_displacement_mm':.18,
                'text':'PER ASPERA AD ASTRA','all_glyph_shapes_unchanged':True,'reason':'Two former 0.136699 mm letter gaps need nominal margin above black-mask 0.13 mm minimum.'})
            # Only the tiny closest portion of one dragon stroke is set back.
            a=next(c for c in cs if c['id']=='dragon-neck-silhouette-03')
            b=next(c for c in cs if c['id']=='dragon-neck-silhouette-02')
            ga,gb=geom(a['polygons']),geom(b['polygons']);pa,pb=nearest_points(ga,gb)
            cut=gb.buffer(.16,quad_segs=ROUND_SEGMENTS).intersection(pa.buffer(.30,quad_segs=ROUND_SEGMENTS))
            adjusted=ga.difference(cut);removed=ga.difference(adjusted)
            assert adjusted.is_valid and len(polygons(adjusted))==len(polygons(ga)) and nholes(adjusted)==nholes(ga)
            change={'kind':'local_subtractive_clearance','id':a['id'],'other_source_id':b['id'],
                'gap_before_mm':ga.distance(gb),'gap_after_mm':adjusted.distance(gb),
                'locality_circle_radius_mm':.30,'locality_center_mm':[pa.x,pa.y],
                'removed_area_mm2':removed.area,'difference_bounds_mm':list(removed.bounds),
                'method':'Subtract only the intersection of the other stroke 0.16 mm clearance buffer and a local 0.30 mm radius disk. Preserve the rest of this stroke.'}
            a['polygons']=geometry_json(adjusted);a['stage2_adjustment']=change
            a['editable_svg_world_path_replacement']=True
            changes.append(change)
            new_motto=unary_union([geom(c['polygons']) for c in cs if c['id'].startswith('latin-motto-glyph-')])
            final=unary_union([neck_only.difference(motto_region),new_motto]).difference(removed)
            # One long, thin negative lens survives a 0.10 mm probe but cannot
            # hold 0.13 mm black mask. Keep it a hole and widen only one local
            # bone-line edge enough to hold a 0.15 mm disk; never fill the lens.
            lens_candidates=[Polygon(r) for p in polygons(final) for r in p.interiors
                if Polygon(r).buffer(-.065,quad_segs=ROUND_SEGMENTS).is_empty]
            assert len(lens_candidates)==1
            lens=lens_candidates[0]
            c3=next(c for c in cs if c['id']=='dragon-swept-wing-bones-03')
            c4=next(c for c in cs if c['id']=='dragon-swept-wing-bones-04')
            g3,g4=geom(c3['polygons']),geom(c4['polygons'])
            mic=maximum_inscribed_circle(lens,tolerance=.000001)
            center=Point(mic.coords[0]);edge=nearest_points(center,g4)[1]
            dx,dy=center.x-edge.x,center.y-edge.y;length=math.hypot(dx,dy)
            shift=max(0,.077-center.distance(g4))
            center=Point(center.x+dx/length*shift,center.y+dy/length*shift)
            for _ in range(20):
                if center.distance(g4)>=.07699:break
                center=Point(center.x+dx/length*.001,center.y+dy/length*.001)
            disk=center.buffer(.077,quad_segs=ROUND_SEGMENTS)
            assert disk.intersection(g4).area<1e-10
            adjusted3=g3.difference(disk);removed3=g3.difference(adjusted3)
            assert adjusted3.is_valid and len(polygons(adjusted3))==len(polygons(g3)) and nholes(adjusted3)==nholes(g3)
            change={'kind':'local_subtractive_mask_island_clearance','id':c3['id'],'other_source_id':c4['id'],
                'original_negative_hole_area_mm2':lens.area,'original_negative_hole_bounds_mm':list(lens.bounds),
                'maximum_inscribed_diameter_before_mm':mic.length*2,
                'clearance_disk_center_mm':[center.x,center.y],'clearance_disk_radius_mm':.077,
                'removed_area_mm2':removed3.area,'difference_bounds_mm':list(removed3.bounds),
                'method':'Move disk center away from the unchanged fourth wing bone, then subtract one 0.077 mm radius disk only from the third bone edge. Long lens hole and both main strokes remain.'}
            c3['polygons']=geometry_json(adjusted3);c3['stage2_adjustment']=change;c3['editable_svg_world_path_replacement']=True
            changes.append(change);final=final.difference(removed3)
        # Compose the exact final polygons and round through the serialized geometry.
        # The retained union is authoritative. Re-unioning separately rounded
        # DFM1 patch components can produce sub-nanometre seam holes at the old
        # filled-hole boundaries; it must not change the retained topology.
        serialized=geometry_json(final)
        final=geom(serialized);after=feature_probe(final)
        stats=metrics(side,[{k:v for k,v in c.items() if k!='polygons'}|{'geometry':geom(c['polygons'])} for c in cs],final)
        assert final.is_valid and len(polygons(final))==len(polygons(baseline))
        assert nholes(final)==nholes(baseline),(side,nholes(final),nholes(baseline))
        assert not after['split_islands'] and not after['entirely_vanished_islands']
        assert stats['minimum_disjoint_island_gap_mm']>=.15-1e-6
        assert not after['negative_holes_unable_to_hold_0_10_mm_probe']
        assert not after['negative_holes_unable_to_hold_0_13_mm_probe']
        before_glyphs={c['id']:geom(c['polygons']) for c in s['components'] if 'glyph-' in c['id']}
        for c in cs:
            if c['id'] not in before_glyphs:continue
            original=before_glyphs[c['id']];changed=geom(c['polygons'])
            dx=c.get('stage2_adjustment',{}).get('v2_additional_dx_mm',0)
            assert original.symmetric_difference(translate(changed,xoff=-dx)).area<1e-5
            assert nholes(original)==nholes(changed)
        out['sides'][side]['components']=cs;out['sides'][side]['union_polygons']=serialized
        added=final.difference(baseline);removed=baseline.difference(final)
        manifest['sides'][side]={'changes':changes,'before_area_mm2':baseline.area,'after_area_mm2':final.area,
            'added_area_mm2':added.area,'removed_area_mm2':removed.area,'symmetric_difference_mm2':final.symmetric_difference(baseline).area,
            'before_holes':nholes(baseline),'after_holes':nholes(final),'before_islands':len(polygons(baseline)),'after_islands':len(polygons(final)),
            'text_shapes_and_counters_unchanged':True,'stats':stats}
        probes['sides'][side]={'before':before,'after':after}
        ET.register_namespace('',NS)
        svg=ET.Element('{'+NS+'}svg',width='85.6mm',height='54mm',viewBox='0 0 85.6 54')
        ET.SubElement(svg,'{'+NS+'}title').text=f'Cassell College {side}: independent DFM v2 geometry'
        for c in cs:ET.SubElement(svg,'{'+NS+'}path',id=c['id'],d=svg_path(geom(c['polygons'])),fill='#c8a65c',**{'fill-rule':'evenodd'})
        ET.ElementTree(svg).write(ROOT/'eda/geometry'/f'{side}_dfm_v2.svg',encoding='utf8',xml_declaration=True)
        print(side,'patches',len(patches),'area',final.area,'min gap',stats['minimum_disjoint_island_gap_mm'],'probes',len(after['split_islands']),len(after['entirely_vanished_islands']))
    out['source_revision']='R1 retained + DFM1 + ten local neck reinforcements and conservative black-mask clearance margin'
    out['target_disjoint_island_gap_mm']=.15
    out['v2_input_sha256']=sha(SOURCE)
    OUT.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    manifest['output']=str(OUT.relative_to(ROOT));manifest['output_sha256']=sha(OUT)
    manifest['all_protected_sources_unchanged']=all(sha(ROOT/p)==h for p,h in original_hashes.items())
    assert manifest['all_protected_sources_unchanged']
    manifest['glyph_count']=143;manifest['glyph_counters_unchanged']=49
    manifest['outputs_applied_to_gui']=False
    (ROOT/'reports/stage2_dfm_v2_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
    (ROOT/'reports/stage2_feature_probe.json').write_text(json.dumps(probes,indent=2,ensure_ascii=False),encoding='utf8')
    rows=[]
    for side,m in manifest['sides'].items():
        rows.append(f"| {side} | {m['before_area_mm2']:.6f} → {m['after_area_mm2']:.6f} | {m['after_holes']} / {m['after_islands']} | {m['stats']['minimum_disjoint_island_gap_mm']:.6f} |")
    md='''# 独立DFM v2局部制造修复\n\n日期：2026-10-28。R1、DFM1与正式EDA工程没有覆盖；这是一份待父任务应用并核验的原生工程候选来源。\n\n本次仅补强6处世界树叶与枝的窄连接、4处建筑装饰石缝与墙线的近切连接，胶囊桥宽0.18mm，轴长约0.106–0.152mm；没有重画文字、世界树、龙或建筑。原窄颈的形态探针估算约0.050–0.095mm，10处在0.10mm尺度内缩后均会断开，修复后不再断开。\n\n为黑色阻焊保留至少0.15mm名义裕量，两对拉丁字间距从约0.136699增至0.156699mm（tracking 0.34→0.36mm，居中，最大追加位移0.18mm）；另对龙翼一处最小0.134019mm间隙仅作局部收边到约0.160mm。局部减法同步为独立SVG替换路径，不能只在PCB中修而让源稿失配。\n\n| 面 | 面积mm²：DFM1→v2 | 孔洞 / 连通块 | 最小不相连岛间距mm |\n|---|---:|---:|---:|\n'''+ '\n'.join(rows)+'''\n\n143个字形与49个字腔保持形状和拓扑。所有几何孔洞均能保留0.10mm直径探针，没有小孤铜整体消失；全图0.05mm内缩没有任何连通块断裂。尖端、衬线与槽的渐尖末端仍会有低于0.10mm的局部横截面，蚀刻会圆钝；形态探针不是全图严格最小宽度数学证明。\n\n`stage2_dfm_v2_manifest.json`保留每处坐标、源ID、差分及源哈希；`stage2_feature_probe.json`给出前后诊断与最小孤铜面积和尺寸。两种阻焊颜色必须共用此套图层才可比较。当前没有GUI DRC或Gerber通过结论。\n'''
    (ROOT/'reports/stage2_dfm_v2_manifest.md').write_text(md,encoding='utf8')
    probe_md='''# 细枝、锐角与小孤铜探针\n\n日期：2026-10-28。诊断对象为保存工程匹配的DFM1与独立DFM v2，使用0.05mm半径内偏移（即0.10mm尺度）。\n\nDFM1世界树一大块分裂为7块，建筑墙线一大块分裂为5块；未有独立铜岛整体消失。文字和龙纹没有此类内缩分裂。v2用10个极短0.18mm桥修复这些连接，前后所有几何孔洞数与连通块数不变；0.10mm尺度不再产生断裂或整岛消失。\n\n另用0.05mm外扩再回缩诊断内部开放负空间，增加面积主要来自尖角与槽端圆钝，不能把它全部标成违规。该方法也不证明所有渐尖末端都达到0.10mm。个别端部趋近零宽属设计几何事实，生产会圆钝。\n\n小孤铜诊断的完整最小5岛面积和包围盒见JSON；这些是面积与存活性筛查，不是嘉立创统一最小孤铜接单标准。\n\n详见[独立v2修复清单](stage2_dfm_v2_manifest.md)。正式工程仍需在GUI应用之后重新DRC、核实铜/开窗及镜像；不得把本报告当作已导入或生产验收。\n'''
    (ROOT/'reports/stage2_feature_probe.md').write_text(probe_md,encoding='utf8')

if __name__=='__main__':main()
