"""Build source-text and outlined review SVGs; no PCB/Gerber is created.
Run from any folder: python design/build_design.py
Requires fonttools; uses the existing Windows Georgia and Calibri fonts.
"""
from pathlib import Path
import json, math, copy, hashlib
import xml.etree.ElementTree as ET
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT/'design/card_data.json').read_text(encoding='utf-8'))
NS='http://www.w3.org/2000/svg'
INK='http://www.inkscape.org/namespaces/inkscape'
ET.register_namespace('',NS)
ET.register_namespace('inkscape','http://www.inkscape.org/namespaces/inkscape')
GOLD=DATA['palette']['gold']; GREEN=DATA['palette']['mask']
FONT_PATHS={'serif':'C:/Windows/Fonts/georgia.ttf','data':'C:/Windows/Fonts/cambria.ttc','sans':'C:/Windows/Fonts/calibrib.ttf'}
FONTS={k:TTFont(v,fontNumber=0) if v.endswith('.ttc') else TTFont(v) for k,v in FONT_PATHS.items()}
FAMILY={'serif':'Georgia','data':'Cambria','sans':'Calibri'}
TEXT_METRICS=[]

def el(tag, parent=None, **attrs):
    e=ET.Element('{'+NS+'}'+tag, {k.replace('_','-'):str(v) for k,v in attrs.items()})
    if parent is not None: parent.append(e)
    return e
def group(parent,id,**attrs): return el('g',parent,id=id,**attrs)
def path(parent,d,w=.24,fill='none',**attrs):
    return el('path',parent,d=d,fill=fill,stroke=GOLD,stroke_width=w,stroke_linecap='round',stroke_linejoin='round',**attrs)
def line(parent,x1,y1,x2,y2,w=.24):
    return el('line',parent,x1=x1,y1=y1,x2=x2,y2=y2,stroke=GOLD,stroke_width=w,stroke_linecap='round')
def new_svg(side):
    s=el('svg',width='85.6mm',height='54mm',viewBox='0 0 85.6 54',version='1.1')
    el('title',s).text=f'Cassell College — {side} — R1 review draft'
    el('desc',s).text='Independent editable vector artwork. Proposed dimensions 85.6 × 54 mm. Not a PCB engineering or fabrication file. Physical values are unapproved proposals.'
    el('metadata',s).text=json.dumps({'revision':'R1','phase':1,'side':side,'physical_parameters_confirmed':False})
    return s

def frame(s):
    g=group(s,'frame')
    inset=DATA['border_inset_mm_proposed']
    el('rect',g,x=inset,y=inset,width=85.6-2*inset,height=54-2*inset,rx=max(.6,DATA['corner_radius_mm_proposed']-inset),fill='none',stroke=GOLD,stroke_width=.26)
    # A single structural corner accent on each corner, with generous clearances.
    for x,y,sx,sy in [(3,3,1,1),(82.6,3,-1,1),(3,51,1,-1),(82.6,51,-1,-1)]:
        path(g,f'M{x},{y+2*sy} L{x},{y} L{x+2*sx},{y}',.22)
    return g

def eight_star(p,cx,cy,r=1.9):
    pts=[]
    for i in range(16):
        a=-math.pi/2+i*math.pi/8
        rr=(r if i%4==0 else r*.66 if i%2==0 else r*.21)
        pts.append(f'{cx+rr*math.cos(a):.4f},{cy+rr*math.sin(a):.4f}')
    el('polygon',p,points=' '.join(pts),fill=GOLD)

def layout_text(s,id,text,x,y,size,font='serif',tracking=0,center=False,weight_expand=.035,record=True):
    f=FONTS[font]; gs=f.getGlyphSet(); cmap=f.getBestCmap(); upm=f['head'].unitsPerEm
    scale=size/upm
    advances=[f['hmtx'].metrics[cmap[ord(c)]][0]*scale for c in text]
    width=sum(advances)+max(0,len(text)-1)*tracking
    if center: x-=width/2
    g=group(s,id,fill=GOLD,stroke=GOLD,stroke_width=weight_expand,stroke_linejoin='round',data_text=text)
    # Editable text and outlined text share explicit character origins.
    cursor=x; boxes=[]; xpos=[]
    for char,adv in zip(text,advances):
        xpos.append(cursor)
        glyph=gs[cmap[ord(char)]]
        bp=BoundsPen(gs); glyph.draw(bp)
        if bp.bounds:
            a,b,c,d=bp.bounds
            boxes.append([cursor+a*scale-weight_expand/2,y-d*scale-weight_expand/2,cursor+c*scale+weight_expand/2,y-b*scale+weight_expand/2])
        cursor+=adv+tracking
    if boxes:
        bbox=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
    else: bbox=[x,y,x,y]
    if record: TEXT_METRICS.append({'id':id,'text':text,'font':font,'font_size_mm':size,'letter_spacing_mm':tracking,'advance_width_mm':width,'bounds_mm':bbox,'glyph_bounds_mm':boxes})
    # Source text object retained in the editable SVG. Font-free paths are generated later.
    t=el('text',g,x=' '.join(f'{v:.5f}' for v in xpos),y=y,font_family=FAMILY[font],font_weight='bold' if font=='sans' else 'normal',font_size=size,**{'xml:space':'preserve'})
    t.text=text
    g.set('data-font-key',font);g.set('data-size-mm',str(size));g.set('data-baseline',str(y));g.set('data-x-origins',json.dumps(xpos))
    return g

def outline_text(s):
    s=copy.deepcopy(s)
    for g in s.iter('{'+NS+'}g'):
        if 'data-font-key' not in g.attrib: continue
        font=g.get('data-font-key'); f=FONTS[font]; gs=f.getGlyphSet(); cmap=f.getBestCmap()
        scale=float(g.get('data-size-mm'))/f['head'].unitsPerEm; y=float(g.get('data-baseline'))
        xpos=json.loads(g.get('data-x-origins'));text=g.get('data-text')
        for child in list(g): g.remove(child)
        for n,(char,x) in enumerate(zip(text,xpos)):
            if char==' ': continue
            pen=SVGPathPen(gs); tp=TransformPen(pen,(scale,0,0,-scale,x,y)); gs[cmap[ord(char)]].draw(tp)
            el('path',g,d=pen.getCommands(),id=f"{g.get('id')}-glyph-{n}")
    return s

def tree_asset():
    s=new_svg('world-tree asset'); g=group(s,'world-tree')
    for r in [15.5,14.77]: el('circle',g,cx=23.7,cy=33.2,r=r,fill='none',stroke=GOLD,stroke_width=.24)
    t=group(g,'tree-trunk-and-primary-limbs')
    # Deliberately asymmetrical trunk, drawn anew rather than tracing pixels.
    path(t,'M23.0 38.4 C24.7 35.9 24.6 32.9 23.7 30.8 C22.8 28.7 23.0 26.0 23.8 22.0 C24.4 25.8 24.4 28.0 25.3 30.0 C26.7 33.0 25.6 36.7 25.3 38.4 C25.8 40.2 28.3 41.9 30.6 43.3 C27.4 42.4 25.2 41.1 24.3 39.7 C23.0 41.4 20.4 42.8 17.5 43.4 C19.7 41.9 22.2 40.2 23.0 38.4 Z',.18,fill=GOLD)
    branches=[
      ('M24.3 33.6 C22.3 30.8 19.8 30.0 16.1 29.9 C13.8 29.9 12.0 29.3 10.8 28.2',.60),
      ('M23.6 31.0 C21.2 28.6 19.0 27.7 15.9 27.3 C14.1 27.0 13.4 26.4 12.5 25.3',.45),
      ('M23.9 28.5 C21.5 27.0 20.9 24.5 19.6 22.4',.48),
      ('M23.7 25.8 C22.4 24.1 22.4 22.8 22.6 21.1',.32),
      ('M24.5 30.1 C26.6 27.7 28.4 26.4 32.1 25.7 C33.8 25.4 34.4 24.8 35.0 24.1',.50),
      ('M25.5 33.1 C28.2 30.2 30.8 29.9 34.1 29.5 C35.6 29.3 36.3 28.7 36.9 27.9',.58),
      ('M24.3 27.6 C26.8 25.7 26.9 23.6 27.9 21.8',.40),
      ('M21.4 29.2 C20.2 27.0 18.7 25.2 16.0 24.1',.30),
      ('M18.8 30.0 C16.7 28.6 15.5 28.6 13.6 28.6',.27),
      ('M16.0 29.9 C14.7 31.2 12.8 31.9 11.4 31.4',.28),
      ('M21.2 31.2 C18.8 32.6 16.0 33.8 12.5 33.3',.32),
      ('M17.1 27.5 C17.0 25.3 16.2 23.9 14.9 23.0',.27),
      ('M20.4 23.8 C19.3 23.2 18.8 22.5 18.5 21.5',.26),
      ('M25.8 26.1 C25.6 24.3 25.9 22.3 25.7 20.7',.27),
      ('M27.9 28.0 C29.1 26.1 29.2 24.5 29.2 23.3',.29),
      ('M31.3 25.9 C31.6 24.4 32.4 23.4 33.1 22.9',.26),
      ('M30.3 30.1 C31.6 28.5 31.8 27.9 32.3 27.0',.29),
      ('M32.9 29.7 C34.5 30.9 35.5 31.2 36.4 31.1',.27),
      ('M28.2 31.1 C29.6 32.9 32.2 33.6 34.8 33.4',.32),
      ('M20.0 32.0 C18.5 31.7 17.8 31.8 16.6 32.1',.24),
      ('M14.4 27.0 C14.0 25.6 13.6 24.7 13.0 24.3',.24),
      ('M34.5 29.3 C35.3 28.0 35.5 27.2 35.8 26.6',.24),
    ]
    for d,w in branches:path(t,d,w)
    twigs=group(g,'tree-secondary-twigs')
    for d in [
      'M14.7 29.8 Q14.1 29.0 13.9 28.1',
      'M17.5 29.9 Q17.1 28.8 17.4 28.0',
      'M18.0 27.8 Q18.5 26.8 18.2 25.7',
      'M20.8 28.5 Q20.7 26.7 20.2 25.8',
      'M21.8 26.1 Q21.6 25.0 20.8 24.2',
      'M23.2 25.1 Q24.0 23.9 23.9 22.4',
      'M25.9 25.9 Q27.6 25.2 28.2 24.5',
      'M28.9 25.4 Q30.2 24.6 30.4 23.7',
      'M29.6 26.6 Q31.0 26.9 32.3 26.5',
      'M32.1 25.7 Q33.8 26.1 34.4 25.7',
      'M34.2 29.4 Q34.5 28.3 34.2 27.6',
      'M31.5 30.0 Q32.4 30.9 33.2 31.1',
      'M29.4 32.2 Q30.7 32.0 31.3 32.5',
      'M18.5 32.7 Q17.8 33.8 16.5 34.0',
      'M16.8 33.3 Q15.8 32.8 15.1 32.8',
      'M13.9 31.0 Q13.2 30.6 12.8 30.0',
      'M20.9 40.0 Q19.8 39.4 19.6 38.6',
      'M26.3 39.4 Q27.6 38.7 28.5 38.8',
      'M24.7 43.5 Q25.6 44.4 25.4 45.2',
      'M21.6 43.5 Q21.3 44.9 21.6 45.5',
      'M30.1 42.5 Q30.9 43.6 31.7 43.9',
      'M17.7 42.7 Q16.4 42.7 15.9 43.1',
    ]: path(twigs,d,.23)
    roots=group(g,'tree-roots')
    for d,w in [
      ('M24 38.8 C22.7 39.5 21.3 39.9 19.2 40.0 C16.7 40.1 14.6 40.6 12.7 41.8',.43),
      ('M24 39.0 C23.0 41.0 23.6 43.4 23.2 45.7',.43),
      ('M24.3 39.5 C25.0 41.6 25.0 43.6 26.5 45.2',.38),
      ('M25 39.0 C27.6 39.7 30.3 39.7 33.7 41.1',.43),
      ('M22 40.9 C19.9 41.3 17.8 42.9 15.4 43.8',.34),
      ('M24 42.0 C22.0 42.8 21.3 44.1 20.4 45.1',.29),
      ('M26.6 41.5 C29.2 41.6 31.8 43.1 32.6 43.8',.31),
      ('M29.6 40.0 C31.2 39.4 33.1 39.4 34.7 39.8',.28),
      ('M18.6 40.0 C17.6 39.3 16.5 39.1 14.8 39.4',.28),
      ('M19.8 41.8 C19.0 43.1 18.7 44.0 18.0 44.5',.26),
      ('M27.3 43.0 C28.5 43.7 29.2 44.4 29.6 44.9',.26),
      ('M16.2 40.5 C15.5 41.6 15.0 42.0 14.4 42.3',.26),
      ('M31.7 40.4 C32.2 41.5 33.4 42.1 34.0 42.3',.26),
    ]:path(roots,d,w)
    # Small solid leaf shapes have real, deliberately broad copper areas.
    leaves=group(g,'tree-leaves',fill=GOLD,stroke='none')
    placements=[(11.7,27.6,-35),(13.1,25.0,-20),(14.7,22.9,-40),(16.0,24.0,-18),(18.4,21.3,-24),(19.5,22.4,5),(22.6,21.0,4),(25.7,20.6,-8),(28.0,21.7,25),(29.2,23.1,5),(32.5,23.3,28),(34.2,24.5,32),(35.3,26.7,15),(36.2,28.2,30),(36.0,31.1,65),(34.6,33.4,105),(12.3,33.2,-85),(11.4,31.4,-66),(13.7,28.5,-70),(16.5,32.1,-45),(17.7,25.9,-30),(20.0,25.0,-24),(27.0,24.2,22),(30.7,27.9,50),(33.7,31.8,80),(13.9,28.1,-20),(17.4,28.0,5),(18.2,25.7,12),(20.2,25.8,-15),(20.8,24.2,-35),(23.9,22.4,12),(28.2,24.5,55),(30.4,23.7,15),(32.3,26.5,65),(34.4,25.7,65),(34.2,27.6,-10),(33.2,31.1,65),(31.3,32.5,105),(16.5,34.0,-100),(15.1,32.8,-75),(12.8,30.0,-40)]
    for i,(x,y,a) in enumerate(placements):
        el('path',leaves,id=f'leaf-{i}',d='M0 0 C-.35 -.45 -.36 -1.0 0 -1.55 C.36 -1.0 .35 -.45 0 0 Z',transform=f'translate({x} {y}) rotate({a})')
    return s

def insert_asset(s,name):
    a=ET.parse(ROOT/'assets'/f'{name}.svg').getroot()
    for child in a:
        if child.tag.endswith('}g'): s.append(copy.deepcopy(child))

def write(svg,p):
    ET.indent(svg,space='  '); ET.ElementTree(svg).write(p,encoding='utf-8',xml_declaration=True)

def add_background(s):
    bg=el('rect',x=0,y=0,width=85.6,height=54,rx=DATA['corner_radius_mm_proposed'],fill=GREEN,id='preview-green-substrate')
    s.insert(3,bg)

def main():
    if DATA['width_mm']!=85.6 or DATA['height_mm']!=54:
        raise ValueError('R1 layout grid is 85.6 x 54 mm. A size change requires a deliberate layout revision; dimensions are not silently stretched.')
    write(tree_asset(),ROOT/'assets/world_tree.svg')
    front=new_svg('front');frame(front)
    layout_text(front,'college-name',DATA['title'],6.0,9.4,5.45,tracking=.45,weight_expand=.065)
    layout_text(front,'college-values',DATA['subtitle'],6.3,13.0,1.42,font='sans',tracking=.28,weight_expand=.035)
    eight_star(group(front,'eight-point-star'),78.1,8.5,2.05)
    line(group(front,'header-rule'),6.0,15.55,79.6,15.55,.24)
    insert_asset(front,'world_tree')
    line(group(front,'information-divider'),44.6,19.1,44.6,48.8,.25)
    for i,f in enumerate(DATA['fields']):
        label_y=21.15+i*6.1
        layout_text(front,f['id']+'-label',f['label']+':',48.2,label_y,1.52,font='sans',tracking=.14,weight_expand=.025)
        layout_text(front,f['id']+'-value',f['value'],48.2,label_y+2.75,2.85 if i==0 else 2.72,font='data',tracking=.14,weight_expand=.065)
    back=new_svg('back');frame(back)
    insert_asset(back,'dragon');insert_asset(back,'architecture')
    layout_text(back,'latin-motto',DATA['motto'],42.8,28.95,3.25,tracking=.28,center=True,weight_expand=.07)
    for side,s in [('front',front),('back',back)]:
        add_background(s)
        write(s,ROOT/'design'/f'{side}_editable.svg')
        o=outline_text(s);write(o,ROOT/'design'/f'{side}_outlined.svg')
        art=copy.deepcopy(o)
        for n in list(art):
            if n.get('id')=='preview-green-substrate': art.remove(n)
        write(art,ROOT/'design'/f'{side}_artwork.svg')
    (ROOT/'reports/text_metrics.json').write_text(json.dumps(TEXT_METRICS,indent=2),encoding='utf-8')
    fonts={k:{'path':v,'sha256':hashlib.sha256(Path(v).read_bytes()).hexdigest(),'embedded':False} for k,v in FONT_PATHS.items()}
    (ROOT/'design/font_manifest.json').write_text(json.dumps(fonts,indent=2),encoding='utf-8')
    print('Built editable / outlined / artwork SVG pairs and independent tree asset.')
    print('\n'.join(f"{m['id']}: {m['bounds_mm']}" for m in TEXT_METRICS))

if __name__=='__main__': main()
