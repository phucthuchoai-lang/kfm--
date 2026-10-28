"""Build a portable source archive without credentials, runtime data or weights."""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
target = ROOT.parent / '拾物客服咪_v2_源码交付.zip'
folders = ['src','scripts','tests','docs','assets','data/ner/raw']
files = ['README.md','run.py','启动平台.bat','requirements.txt','requirements-integrations.txt','.env.example','.gitignore']
entries = [ROOT/f for f in files]
for folder in folders:
    entries.extend(p for p in (ROOT/folder).rglob('*') if p.is_file())
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(set(entries)):
        relative = path.relative_to(ROOT)
        if any(part in {'__pycache__','.git','checkpoints','runtime'} for part in relative.parts) or path.suffix in {'.pyc','.bak','.log','.db','.safetensors','.pt','.pth'} or path.name=='.env':
            continue
        archive.write(path,Path('shiwu-platform')/relative)
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    assert not any(Path(n).name=='.env' or '/runtime/' in n or '/checkpoints/' in n for n in archive.namelist())
print(f'Archive ready: {target.name}; {target.stat().st_size:,} bytes')
