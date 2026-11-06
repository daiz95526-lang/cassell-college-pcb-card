"""Expand the retained R1 SVG into closed polygonal geometry in millimetres.

This is artwork preparation, not a Gerber exporter. Original SVGs are read-only.
Requires fontTools and Shapely (local vendor directory is supported).
"""
from pathlib import Path
import sys, math, re, json, hashlib
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE/'vendor'))
from shapely.geometry import Polygon, MultiPolygon, GeometryCollection, LineString, Point
from shapely.ops import unary_union, polygonize, nearest_points
from shapely.affinity import affine_transform
from fontTools.pens.basePen import BasePen
from fontTools.svgLib.path import parse_path

ROOT=HERE.parents[1]
TOLERANCE_MM=0.001
ROUND_SEGMENTS=24
NS='http://www.w3.org/2000/svg'
I=(1.,0.,0.,1.,0.,0.)

def numbers(s):
    return [float(v) for v in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[Ee][-+]?\d+)?',s)]

def compose(a,b):
    return (a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],
            a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],
            a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5])

def transform_value(s):
    m=I
    for op,args in re.findall(r'([a-zA-Z]+)\s*\(([^)]*)\)',s or ''):
        v=numbers(args)
        if op=='translate':n=(1,0,0,1,v[0],v[1] if len(v)>1 else 0)
        elif op=='scale':n=(v[0],0,0,v[1] if len(v)>1 else v[0],0,0)
        elif op=='rotate':
            r=math.radians(v[0]);c=math.cos(r);sn=math.sin(r);n=(c,sn,-sn,c,0,0)
            if len(v)>1:n=compose(compose((1,0,0,1,v[1],v[2]),n),(1,0,0,1,-v[1],-v[2]))
        elif op=='matrix':n=tuple(v)
        elif op=='skewX':n=(1,0,math.tan(math.radians(v[0])),1,0,0)
        elif op=='skewY':n=(1,math.tan(math.radians(v[0])),0,1,0,0)
        else:raise ValueError('Unsupported SVG transform '+op)
        m=compose(m,n)
    return m

def to_world(g,m):
    return affine_transform(g,[m[0],m[2],m[1],m[3],m[4],m[5]])

def mid(a,b):return ((a[0]+b[0])/2,(a[1]+b[1])/2)
def chord_distance(p,a,b):
    dx=b[0]-a[0];dy=b[1]-a[1];l=math.hypot(dx,dy)
    return math.hypot(p[0]-a[0],p[1]-a[1]) if l<1e-15 else abs(dx*(a[1]-p[1])-(a[0]-p[0])*dy)/l

class FlatPen(BasePen):
    def __init__(self):
        super().__init__(None);self.parts=[];self.points=[];self.current=None
    def finish(self,closed=False):
        if self.points:
            if closed and self.points[0]!=self.points[-1]:self.points.append(self.points[0])
            self.parts.append((self.points,closed));self.points=[]
    def _moveTo(self,p):self.finish();self.points=[tuple(p)];self.current=tuple(p)
    def _lineTo(self,p):self.points.append(tuple(p));self.current=tuple(p)
    def _closePath(self):self.finish(True);self.current=None
    def _endPath(self):self.finish();self.current=None
    def _qCurveToOne(self,b,c):
        self.quad(self.current,tuple(b),tuple(c));self.current=tuple(c)
    def quad(self,a,b,c,depth=0):
        if depth>=24 or chord_distance(b,a,c)<=TOLERANCE_MM:
            self.points.append(c);return
        ab=mid(a,b);bc=mid(b,c);m=mid(ab,bc)
        self.quad(a,ab,m,depth+1);self.quad(m,bc,c,depth+1)
    def _curveToOne(self,b,c,d):
        self.cubic(self.current,tuple(b),tuple(c),tuple(d));self.current=tuple(d)
    def cubic(self,a,b,c,d,depth=0):
        if depth>=24 or max(chord_distance(b,a,d),chord_distance(c,a,d))<=TOLERANCE_MM:
            self.points.append(d);return
        ab=mid(a,b);bc=mid(b,c);cd=mid(c,d);abc=mid(ab,bc);bcd=mid(bc,cd);m=mid(abc,bcd)
        self.cubic(a,ab,abc,m,depth+1);self.cubic(m,bcd,cd,d,depth+1)

def winding(p,ring):
    x,y=p;wn=0
    for a,b in zip(ring,ring[1:]):
        cross=(b[0]-a[0])*(y-a[1])-(x-a[0])*(b[1]-a[1])
        if a[1]<=y<b[1] and cross>0:wn+=1
        elif b[1]<=y<a[1] and cross<0:wn-=1
    return wn

def fill_geometry(parts,rule):
    rings=[]
    for points,closed in parts:
        if len(points)<3:continue
        ring=points if points[0]==points[-1] else points+[points[0]]
        rings.append(ring)
    if not rings:return GeometryCollection()
    faces=list(polygonize(unary_union([LineString(r) for r in rings])))
    keep=[]
    for face in faces:
        rp=face.representative_point();wn=sum(winding((rp.x,rp.y),r) for r in rings)
        if (wn%2!=0) if rule=='evenodd' else wn!=0:keep.append(face)
    return unary_union(keep)

def ellipse(cx,cy,rx,ry):
    r=max(rx,ry)
    n=max(24,math.ceil(math.pi/math.acos(max(-1,min(1,1-TOLERANCE_MM/max(r,1e-12))))))
    p=[(cx+rx*math.cos(2*math.pi*i/n),cy+ry*math.sin(2*math.pi*i/n)) for i in range(n)]
    return [(p+[p[0]],True)]

def shape_parts(e):
    tag=e.tag.split('}')[-1]
    get=lambda k,d=0:float(e.get(k,d))
    if tag=='path':
        p=FlatPen();parse_path(e.get('d',''),p);p.finish();return p.parts
    if tag=='line':return [([(get('x1'),get('y1')),(get('x2'),get('y2'))],False)]
    if tag in ('polygon','polyline'):
        n=numbers(e.get('points',''));points=list(zip(n[0::2],n[1::2]));closed=tag=='polygon'
        if closed and points[0]!=points[-1]:points.append(points[0])
        return [(points,closed)]
    if tag in ('circle','ellipse'):
        rx=get('r') if tag=='circle' else get('rx');ry=rx if tag=='circle' else get('ry')
        return ellipse(get('cx'),get('cy'),rx,ry)
    if tag=='rect':
        x,y,w,h=get('x'),get('y'),get('width'),get('height');rx=min(get('rx',get('ry')),w/2);ry=min(get('ry',rx),h/2)
        if rx==0 or ry==0:return [([(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)],True)]
        pts=[];r=max(rx,ry);n=max(4,math.ceil(math.pi/2/math.acos(max(-1,min(1,1-TOLERANCE_MM/r)))))
        for cx,cy,base in [(x+w-rx,y+ry,-90),(x+w-rx,y+h-ry,0),(x+rx,y+h-ry,90),(x+rx,y+ry,180)]:
            for i in range(n+1):
                a=math.radians(base+90*i/n);pts.append((cx+rx*math.cos(a),cy+ry*math.sin(a)))
        return [(pts+[pts[0]],True)]
    raise ValueError('Unsupported visible SVG element '+tag)

def polygons(g):
    if isinstance(g,Polygon):return [g]
    if isinstance(g,(MultiPolygon,GeometryCollection)):
        return [p for x in g.geoms for p in polygons(x)]
    return []

def ring_json(r):return [[round(x,6),round(y,6)] for x,y in r.coords]
def geometry_json(g):
    return [{'outer':ring_json(p.exterior),'holes':[ring_json(r) for r in p.interiors],'area_mm2':p.area} for p in polygons(g)]

def load_artwork(side,source_path=None):
    source=Path(source_path) if source_path is not None else ROOT/'design'/f'{side}_artwork.svg'
    root=ET.parse(source).getroot();comps=[]
    def visit(e,style,m,groups,text):
        tag=e.tag.split('}')[-1]
        if tag in ('title','desc','metadata','defs'):return
        style=dict(style)
        for k in ['fill','stroke','stroke-width','stroke-linejoin','stroke-linecap','fill-rule','stroke-miterlimit','display','visibility','opacity']:
            if e.get(k) is not None:style[k]=e.get(k)
        for part in e.get('style','').split(';'):
            if ':' in part:
                k,v=part.split(':',1);style[k.strip()]=v.strip()
        if style.get('display')=='none' or style.get('visibility')=='hidden' or float(style.get('opacity',1))==0:return
        m=compose(m,transform_value(e.get('transform')))
        if tag in ('svg','g'):
            groups=groups+([e.get('id')] if e.get('id') else [])
            text=e.get('data-text',text)
            for child in e:visit(child,style,m,groups,text)
            return
        parts=shape_parts(e);pieces=[]
        if style.get('fill','black')!='none':pieces.append(fill_geometry(parts,style.get('fill-rule','nonzero')))
        width=float(style.get('stroke-width',1))
        if style.get('stroke','none')!='none' and width>0:
            cap={'round':1,'butt':2,'square':3}.get(style.get('stroke-linecap','butt'),2)
            join={'round':1,'miter':2,'bevel':3}.get(style.get('stroke-linejoin','miter'),2)
            for points,closed in parts:
                if len(points)>=2:
                    pieces.append(LineString(points).buffer(width/2,quad_segs=ROUND_SEGMENTS,cap_style=cap,join_style=join,mitre_limit=float(style.get('stroke-miterlimit',4))))
        g=to_world(unary_union(pieces),m)
        if not g.is_empty:
            if not g.is_valid:raise ValueError('Invalid geometry '+str(e.get('id')))
            comps.append({'id':e.get('id') or f'{side}-primitive-{len(comps)+1:04d}', 'tag':tag,'groups':groups,'text':text,'source_stroke_mm':width if style.get('stroke','none')!='none' else None,'geometry':g,'fill_contours':sum(1 for p,c in parts if len(p)>=3)})
    visit(root,{'fill':'black','stroke':'none'},I,[],None)
    combined=unary_union([c['geometry'] for c in comps])
    return source,comps,combined

def svg_path(g):
    def ring(r):
        pts=list(r.coords);return 'M'+' L'.join(f'{x:.6f},{y:.6f}' for x,y in pts)+' Z'
    return ' '.join(ring(p.exterior)+' '+' '.join(ring(r) for r in p.interiors) for p in polygons(g))

def write_svg(side,components):
    ET.register_namespace('',NS)
    root=ET.Element('{'+NS+'}svg',width='85.6mm',height='54mm',viewBox='0 0 85.6 54')
    ET.SubElement(root,'{'+NS+'}title').text='R1 '+side+' polygonal artwork geometry, preparation only'
    for c in components:
        ET.SubElement(root,'{'+NS+'}path',id=c['id'],d=svg_path(c['geometry']),fill='#c8a65c',**{'fill-rule':'evenodd'})
    dest=ROOT/'eda/geometry'/f'{side}_geometry.svg';dest.parent.mkdir(parents=True,exist_ok=True)
    ET.ElementTree(root).write(dest,encoding='utf-8',xml_declaration=True)

def metrics(side,components,g):
    ps=polygons(g);areas=sorted(p.area for p in ps);holes=sum(len(p.interiors) for p in ps)
    # Opening is a diagnostic: endpoint caps and sharp decorative tips naturally lose tiny areas.
    erosion={}
    for width in [.10,.127,.15,.20,.22,.25]:
        opened=g.buffer(-width/2,quad_segs=ROUND_SEGMENTS).buffer(width/2,quad_segs=ROUND_SEGMENTS)
        lost=g.difference(opened)
        erosion[str(width)]={'lost_area_mm2':lost.area,'fraction_of_artwork':lost.area/g.area,'note':'Morphological diagnostic, not an exact local-minimum-width DRC. Rounded ends and sharp tips contribute.'}
    # Distances between physically disjoint islands, excluding intended joined branch/letter strokes.
    near=[];min_gap=math.inf
    for i,a in enumerate(ps):
        for j in range(i+1,len(ps)):
            b=ps[j];d=a.distance(b)
            if d<min_gap:min_gap=d
            if d<.25:
                pa,pb=nearest_points(a,b)
                near.append({'islands':[i,j],'gap_mm':d,'points_mm':[[pa.x,pa.y],[pb.x,pb.y]],'areas_mm2':[a.area,b.area]})
    near.sort(key=lambda x:x['gap_mm'])
    glyphs=[]
    for c in components:
        if 'glyph-' in c['id']:
            glyphs.append({'id':c['id'],'source_text':c['text'],'polygon_count':len(polygons(c['geometry'])),'hole_count':sum(len(p.interiors) for p in polygons(c['geometry'])),'area_mm2':c['geometry'].area})
    return {'side':side,'area_mm2':g.area,'area_cm2':g.area/100,'single_board_rectangle_area_mm2':85.6*54,'coverage_of_single_rectangular_face_percent':100*g.area/(85.6*54),'bounds_mm':list(g.bounds),'is_valid':g.is_valid,'primitive_count':len(components),'island_count':len(ps),'hole_count':holes,'smallest_island_area_mm2':areas[0],'islands_below_0_01_mm2':sum(a<.01 for a in areas),'islands_below_0_05_mm2':sum(a<.05 for a in areas),'minimum_disjoint_island_gap_mm':min_gap if math.isfinite(min_gap) else None,'disjoint_island_gaps_below_0_25_mm':near,'morphological_width_diagnostics':erosion,'glyph_counter_audit':glyphs}

def main():
    out={'units':'mm','view':'Each face read from its own outside; no bottom mirror has been applied here.','source_revision':'R1 retained artwork','flattening_tolerance_mm':TOLERANCE_MM,'round_buffer_quadrant_segments':ROUND_SEGMENTS,'sides':{}}
    report={'scope':'Vector geometry preparation and R1 measurement, not EDA DRC or Gerber DFM. No source artwork altered.','flattening_tolerance_mm':TOLERANCE_MM,'limitations':['Curve approximation is <=0.001 mm in local R1 coordinates; buffer rounding adds less than 0.001 mm at these widths.','Width erosion is a diagnostic and does not prove a minimum feature rule.','Disjoint-island distance does not test every internal slot or same-island gap.','Areas are current artwork unions; final exposed copper is copper intersected with verified EDA mask openings.','No Gerber was created.'],'sides':{}}
    for side in ['front','back']:
        source,components,g=load_artwork(side)
        write_svg(side,components)
        stats=metrics(side,components,g)
        out['sides'][side]={'source':str(source.relative_to(ROOT)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'union_polygons':geometry_json(g),'components':[{k:v for k,v in c.items() if k!='geometry'}|{'polygons':geometry_json(c['geometry'])} for c in components]}
        report['sides'][side]=stats
        print(side, {k:stats[k] for k in ['area_mm2','coverage_of_single_rectangular_face_percent','primitive_count','island_count','hole_count','smallest_island_area_mm2','minimum_disjoint_island_gap_mm']})
    a=report['sides']['front']['area_mm2'];b=report['sides']['back']['area_mm2'];board=85.6*54-(4-math.pi)*3.18**2
    report['area_summary']={'rounded_board_area_mm2':board,'front_artwork_mm2':a,'back_artwork_mm2':b,'two_faces_artwork_sum_mm2':a+b,'front_over_rounded_board_percent':a/board*100,'back_over_rounded_board_percent':b/board*100,'sum_over_one_rounded_board_percent':(a+b)/board*100,'sum_over_two_rounded_faces_percent':(a+b)/(2*board)*100}
    (ROOT/'eda/artwork_geometry.json').write_text(json.dumps(out,separators=(',',':'),ensure_ascii=False),encoding='utf-8')
    (ROOT/'reports/stage2_geometry.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')

if __name__=='__main__':main()
