#!/usr/bin/env python3
"""Read one HFS+ file from a recovery block device without mounting or writing.
Handles inline extent records only; refuses overflow extents. Paths use exact case on HFS+ and HFSX.
"""
import argparse, struct, subprocess
from pathlib import Path
U16=lambda b,o: struct.unpack_from('>H',b,o)[0]
U32=lambda b,o: struct.unpack_from('>I',b,o)[0]
U64=lambda b,o: struct.unpack_from('>Q',b,o)[0]
class Volume:
    def __init__(self, adb, device):
        if device != '/dev/block/bootdevice/by-name/userdata':
            raise ValueError('Only the explicitly selected userdata source is supported')
        self.adb,self.device=adb,device
        h=self.read(1024,512)
        if h[:2] not in (b'H+', b'HX'): raise ValueError('Not an HFS+/HFSX volume')
        self.bs=U32(h,40)
        if self.bs<512 or self.bs>1048576 or self.bs&(self.bs-1): raise ValueError('Invalid block size')
        self.cat=self.fork(h[272:352],512*1024*1024)
        self.ns=U16(self.cat,32)
        if self.ns<512 or self.ns>32768 or self.ns&(self.ns-1): raise ValueError('Invalid catalog node size')
        self.first=U32(self.cat,24)
    def read(self,offset,size):
        block=4096; start=offset//block; delta=offset%block; count=(delta+size+block-1)//block
        cmd=f'dd if={self.device} bs={block} skip={start} count={count} 2>/dev/null'
        data=subprocess.run([self.adb,'exec-out',cmd],check=True,stdout=subprocess.PIPE).stdout
        if len(data)<delta+size: raise ValueError('Short block read')
        return data[delta:delta+size]
    def fork(self,f,limit):
        size=U64(f,0)
        if size>limit: raise ValueError('Fork exceeds read limit')
        pieces=[]; have=0
        for i in range(8):
            start,count=struct.unpack_from('>II',f,16+i*8)
            n=min(count*self.bs,size-have)
            if n: pieces.append(self.read(start*self.bs,n)); have+=n
            if have==size: return b''.join(pieces)
        raise ValueError('Overflow extents require a full HFS implementation')
    def entries(self):
        n=self.first; seen=set()
        while n:
            if n in seen: raise ValueError('Catalog leaf loop')
            seen.add(n)
            b=self.cat[n*self.ns:(n+1)*self.ns]
            if len(b)!=self.ns or b[8]!=255: raise ValueError('Invalid catalog leaf')
            for i in range(U16(b,10)):
                o=U16(b,self.ns-2*(i+1)); end=U16(b,self.ns-2*(i+2))
                if not 14<=o<end<=self.ns: raise ValueError('Bad record bounds')
                kl=U16(b,o); parent=U32(b,o+2); nl=U16(b,o+6)
                if 6+nl*2>kl: raise ValueError('Bad key length')
                name=b[o+8:o+8+nl*2].decode('utf-16-be')
                record=b[o+2+kl:end]
                if len(record)>=12: yield parent,name,record
            n=U32(b,0)
    def catfile(self,path):
        entries=list(self.entries()); parent=2
        parts=Path(path).parts
        parts=[p for p in parts if p!='/']
        for i,name in enumerate(parts):
            found=[r for p,n,r in entries if p==parent and n==name and U16(r,0) in (1,2)]
            if len(found)!=1: raise ValueError(f'Cannot resolve {name!r}')
            r=found[0]; typ=U16(r,0)
            if i+1==len(parts):
                if typ!=2: raise ValueError('Not a regular file')
                return self.fork(r[88:168],64*1024*1024)
            if typ!=1: raise ValueError('Not a directory')
            parent=U32(r,8)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--adb',required=True)
    ap.add_argument('path'); ap.add_argument('output')
    a=ap.parse_args()
    target=Path(a.output)
    if target.exists(): raise SystemExit('Refusing to replace an existing backup')
    data=Volume(a.adb,'/dev/block/bootdevice/by-name/userdata').catfile(a.path)
    target.write_bytes(data)
    print(f'Read {len(data)} bytes from {a.path} to {target}')
if __name__=='__main__': main()
