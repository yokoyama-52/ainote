"""Explicit installer; normal application startup never downloads models."""
from pathlib import Path
import hashlib
import json
import subprocess

root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'models/manifest.json').read_text())
for name in ('small0','small1'):
    spec=manifest[name]
    destination=root/'models'/f'beat-this-{name}.ckpt'
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest()==spec['sha256']:
        print(name,'verified');continue
    expected_url=f'https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/{name}.ckpt'
    if spec['source'] != expected_url:raise ValueError('Unrecognized model URL')
    temporary=destination.with_suffix('.download')
    subprocess.run(['curl','--fail','--location','--show-error','--retry','2',expected_url,'-o',str(temporary)],check=True)
    if hashlib.sha256(temporary.read_bytes()).hexdigest()!=spec['sha256']:
        temporary.unlink(missing_ok=True)
        raise ValueError('Downloaded model checksum mismatch')
    temporary.replace(destination)
    print(name,'downloaded and verified')
