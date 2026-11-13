#!/usr/bin/env python3
"""One final golden image hash check; never read file contents into output."""
import hashlib
import json
import os
from pathlib import Path
from disk_inventory import regular
os.umask(0o077)
d=Path.home()/'cm5-v8-lab/golden'
record=json.loads((d/'import.json').read_text())
with regular(d/'cm5-emmc-userarea.img').open('rb') as f:
    after=hashlib.file_digest(f,'sha256').hexdigest()
result={'before':record['image_sha256'],'after':after,
        'status':'PASS' if after==record['image_sha256'] else 'FAIL'}
(d/'audit-after.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['status']=='PASS' else 1)
