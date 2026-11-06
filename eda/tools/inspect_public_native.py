from pathlib import Path
import json,collections
p=Path('eda/project/pcb/PCB1.epcb2'); latest={}
for line in p.read_text(encoding='utf-8-sig').splitlines():
    if '||' not in line: continue
    a,b=line.rstrip('|').split('||',1); h=json.loads(a); k=h.get('id',h['type']); d=json.loads(b) if b else None
    if k not in latest or h.get('ticket',0)>=latest[k][0].get('ticket',0): latest[k]=(h,d)
print(collections.Counter(h['type'] for h,d in latest.values() if d is not None))
for h,d in latest.values():
    if d is not None and h['type'] not in ('FILL','LAYER','CANVAS','LAYER_PHYS'):
        print(h['type'],h.get('id'),str(d)[:350])
