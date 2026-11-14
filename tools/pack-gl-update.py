#!/usr/bin/env python3
"""Create a minimal GPU mailbox update and a launchd rollback from the live backup."""
import copy,hashlib,json,plistlib,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
out=root/'out/mox-corey-gl';libs=root/'out/gl-userland'
original=root/'out/device/launchd.plist.original'
old=plistlib.loads(original.read_bytes()); new=copy.deepcopy(old)
jobs=new['LaunchDaemons']
keys=[k for k,j in jobs.items() if j.get('Label')=='com.apple.backboardd']
assert len(keys)==1
job=jobs[keys[0]]
assert job['ProgramArguments']==['/usr/libexec/backboardd']
assert 'Program' not in job
job['ProgramArguments']=['/usr/libexec/sweet-bbd']
autorun='/System/Library/LaunchDaemons/com.sweet.autorun.plist'
assert autorun not in jobs
jobs[autorun]={'Label':'com.sweet.autorun','ProgramArguments':['/usr/libexec/sweet-autorun'],'RunAtLoad':True,'POSIXSpawnType':'Interactive'}
updated=out/'launchd.plist.gpu'
updated.write_bytes(plistlib.dumps(new,fmt=plistlib.FMT_BINARY))
# Prove only the two intended jobs changed.
control=copy.deepcopy(new)
control['LaunchDaemons'].pop(autorun)
control['LaunchDaemons'][keys[0]]=copy.deepcopy(old['LaunchDaemons'][keys[0]])
assert control==old
script=out/'autorun.sh'
script.write_text("""# GPU self-tests; each test writes its result to the persistent console ring.
echo COREY GPU MIGRATION: hardware readback
/private/var/tmp/redwood-gpu-test
echo COREY GPU MIGRATION: Mesa reference render
export OSMESA_SOFTWARE=1
/private/var/tmp/osmesa-triangle
echo COREY GPU MIGRATION: Adreno render
export OSMESA_SOFTWARE=0
/private/var/tmp/osmesa-triangle
echo COREY GPU MIGRATION: tests complete
""")
pairs=[
 ('ROOT/System/Library/xpc/launchd.plist.pre-corey-gl',original),
 ('ROOT/usr/lib/libOSMesa.8.dylib',libs/'libOSMesa.8.dylib'),
 ('ROOT/usr/lib/libsweet-gl.dylib',libs/'libsweet-gl.dylib'),
 ('ROOT/usr/lib/libsweet-bbd.dylib',libs/'libsweet-bbd.dylib'),
 ('ROOT/usr/libexec/sweet-bbd',libs/'sweet-bbd'),
 ('ROOT/usr/libexec/sweet-autorun',libs/'sweet-autorun'),
 ('redwood-gpu-test',libs/'redwood-gpu-test'),
 ('osmesa-triangle',libs/'osmesa-triangle'),
 ('libOSMesa.8.dylib',libs/'libOSMesa.8.dylib'),
 ('autorun.sh',script),
 ('ROOT/System/Library/xpc/launchd.plist',updated)]
packer=root/'out/ci-source/tools/sweet-mailbox.py'
subprocess.run([sys.executable,str(packer),'pack',str(out/'corey-gl-install.box')]+[str(x) for p in pairs for x in p],check=True)
subprocess.run([sys.executable,str(packer),'pack',str(out/'corey-gl-rollback.box'),'ROOT/System/Library/xpc/launchd.plist',str(original)],check=True)
manifest={'launchd_original_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
          'entries':[{'path':n,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for n,p in pairs]}
(out/'install-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
