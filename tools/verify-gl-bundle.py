#!/usr/bin/env python3
"""Verify signed binaries, every mailbox entry and embedded boot payload."""
import hashlib,json,struct,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent;out=root/'out/mox-corey-gl';src=root/'out/ci-source'
sys.path.insert(0,str(src/'tools'))
import adt,mkguacboot,mkpayload
def signed(p):
 b=p.read_bytes()
 assert struct.unpack_from('<II',b)==(0xfeedfacf,0x100000c),p
 n=struct.unpack_from('<I',b,16)[0];o=32;sig=None
 for _ in range(n):
  cmd,sz=struct.unpack_from('<II',b,o)
  if cmd==0x1d: sig=struct.unpack_from('<II',b,o+8)
  if cmd==0x32:
   platform,minimum=struct.unpack_from('<II',b,o+8)
   assert platform==2 and minimum<=0x100710,(p,platform,minimum)
  o+=sz
 assert sig,p
 sb=b[sig[0]:sig[0]+sig[1]];magic,length,count=struct.unpack_from('>III',sb)
 assert magic==0xfade0cc0 and length<=len(sb),p
 checked=0
 for i in range(count):
  typ,off=struct.unpack_from('>II',sb,12+8*i)
  if typ!=0 and not 0x1000<=typ<0x1005: continue
  cd=sb[off:];m,ln,ver,flags,ho,ident,special,slots,limit=struct.unpack_from('>9I',cd)
  hs,ht,platform,ps=struct.unpack_from('4B',cd,36)
  assert m==0xfade0c02 and limit<=sig[0]
  page=1<<ps;assert slots==(limit+page-1)//page
  algo={1:'sha1',2:'sha256',3:'sha256',4:'sha384'}[ht]
  for j in range(slots):
   h=hashlib.new(algo,b[j*page:min((j+1)*page,limit)]).digest()[:hs]
   assert h==cd[ho+j*hs:ho+(j+1)*hs],(p,j)
  checked+=1
 assert checked,p
for p in (root/'out/gl-userland').iterdir():
 if p.read_bytes()[:4]==b'\xcf\xfa\xed\xfe': signed(p)
manifest=json.loads((out/'install-manifest.json').read_text())
box=(out/'corey-gl-install.box').read_bytes()
assert box[:8]==b'SWEETBOX' and len(box)<64*1024*1024
n=struct.unpack_from('<I',box,8)[0];assert n==len(manifest['entries']);o=12
for entry in manifest['entries']:
 ns=struct.unpack_from('<H',box,o)[0];o+=2;name=box[o:o+ns].decode();o+=ns
 size=struct.unpack_from('<I',box,o)[0];o+=4;data=box[o:o+size];o+=size
 assert name==entry['path'] and size==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256']
assert not any(box[o:])
tree,_=adt.parse((out/'guacamole.adt').read_bytes())
nodes={}
def visit(n,path=''):
 path=path+'/'+n.name;nodes[path]=n
 for c in n.children:visit(c,path)
visit(tree)
gpu=next(n for n in nodes.values() if n.name=='sweet-gpu')
for prop,name in [('gmu-firmware','a640_gmu.bin'),('sqe-firmware','a630_sqe.fw'),('zap-metadata','a640_zap.mdt'),('zap-b00','a640_zap.b00'),('zap-b01','a640_zap.b01'),('zap-b02','a640_zap.b02')]:
 assert gpu.prop(prop)==(src/'research/gpu/fw'/name).read_bytes(),prop
display=next(n for n in nodes.values() if n.name=='disp0')
assert struct.unpack('<I',display.prop('canvas-width'))==(1440,)
assert struct.unpack('<I',display.prop('canvas-height'))==(3120,)
kernel=bytearray((root/'out/upstream-ci/42140063871/kernel.development.sweet').read_bytes())
km=mkpayload.parse_macho(kernel);mkpayload.apply_chained_fixups(kernel,km)
bm=json.loads((out/'build-manifest.json').read_text())
for name,info in bm['images'].items():
 b=(out/name).read_bytes()
 assert hashlib.sha256(b).hexdigest()==info['sha256']
 st=mkguacboot.parse_v2(b);ks,ka,rs=struct.unpack_from('<III',b,8);page=st['page']
 ro=page+((ks+page-1)//page)*page
 payload=b[ro:ro+rs]
 assert payload==(out/(name[:-4]+'.payload')).read_bytes()
 assert b[page:page+ks]==(src/'shim/out/Image').read_bytes()
 assert payload[:8]==b'SWEETXNU'
 assert payload[0x48:0x2a8].split(b'\0')[0].decode()==info['args']
 ao,asz=struct.unpack_from('<QQ',payload,0x20)
 assert payload[ao:ao+asz]==(out/'guacamole.adt').read_bytes()
 count=struct.unpack_from('<I',payload,12)[0]
 for i in range(count):
  va,vsz,fo,fsz=struct.unpack_from('<QQQQ',payload,0x2a8+32*i)
  source=next(s for s in km['segs'] if s['vmaddr']==va and s['vmsize']==vsz)
  assert payload[fo:fo+fsz]==kernel[source['fileoff']:source['fileoff']+fsz]
 h=hashlib.sha1()
 for part in (b[page:page+ks],payload,b'',b'',st['dtb']):
  h.update(part);h.update(struct.pack('<I',len(part)))
 assert b[576:596]==h.digest()
print('PASS: all Mach-O code pages signed; mailbox contents match; both boot headers, kernels, firmware and native ADT verified.')
