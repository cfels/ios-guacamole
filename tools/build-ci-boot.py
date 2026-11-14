#!/usr/bin/env python3
"""Package the fork's verified CI kernel, matching shim and native-size ADT."""
import hashlib,json,struct,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent.parent
src=root/'out/ci-source'
sys.path.insert(0,str(src/'tools'))
import adt
kernel=root/'out/upstream-ci/42140063871/kernel.development.sweet'
expected=(root/'out/upstream-ci/42140063871/SHA256SUMS').read_text().split()[0]
assert hashlib.sha256(kernel.read_bytes()).hexdigest()==expected
assert subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip()=='68483019cf48baf0fee45120f814635779505eff'
out=root/'out/mox-corey-gl';out.mkdir(exist_ok=True)
subprocess.run([sys.executable,str(src/'tools/mkadt.py'),str(out/'guacamole.adt'),'--highmem','--guacamole'],check=True)
tree,end=adt.parse((out/'guacamole.adt').read_bytes())
def visit(n):
    if n.name=='disp0':
        n.props=[(k,f,struct.pack('<I',1440 if k=='canvas-width' else 3120) if k in ('canvas-width','canvas-height') else v) for k,f,v in n.props]
    for c in n.children: visit(c)
visit(tree)
(out/'guacamole.adt').write_bytes(adt.serialize(tree))
base=f'debug=0xc serial=3 cpus=8 keepsyms=1 -enable_kprintf_spam -noprogress sweettouch=1 sweetkeys=1 sweetusb=0 wdt=-1 sweettime={int(time.time())} rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 sweetfb_hz=60 sweetfb_native=1 sweetfb_noconsole=1 sweetlogdump=0 ufslogsecs=1 sweetmailbox=1 sweetboxpart=rawdump sweetboxroot=1'
manifest={'source_commit':'68483019cf48baf0fee45120f814635779505eff','workflow_run':42140063871,'kernel_sha256':expected,'images':{}}
for name,extra in [('boot-corey-gl-native','sweetgpu=11 sweetglwait=120'),('boot-corey-software-rescue','sweetgpu=0 sweetbbd=0 sweetgl=0')]:
    args=base+' '+extra
    assert len(args.encode())<608
    payload=out/(name+'.payload')
    subprocess.run([sys.executable,str(src/'tools/mkpayload.py'),str(kernel),str(out/'guacamole.adt'),str(payload),'--cmdline',args],check=True)
    image=out/(name+'.img')
    subprocess.run([sys.executable,str(src/'tools/mkguacboot.py'),str(root/'out/device/boot_a.img'),str(src/'shim/out/Image'),str(image),'--ramdisk',str(payload)],check=True)
    manifest['images'][image.name]={'bytes':image.stat().st_size,'sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'args':args}
(out/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
