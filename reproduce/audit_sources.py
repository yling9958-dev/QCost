#!/usr/bin/env python3
"""Inventory an original research tree read-only and record a preservation snapshot."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

SOURCE_SUFFIXES = {'.py','.cpp','.cc','.c','.h','.hpp','.sh','.cmake','.toml','.yaml','.yml','.json','.ipynb'}
MODEL_SUFFIXES = {'.pt','.pth','.ckpt','.pkl','.pickle','.joblib','.onnx','.h5','.hdf5','.safetensors'}
OMIT = {'QCost-reproducible','.git','__pycache__','.pytest_cache','.mypy_cache','.ipynb_checkpoints'}
LIBRARY = {'texmf','latex_dependencies','node_modules','.venv','venv'}

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(4*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def collect(root):
    sizes, counts = Counter(), Counter()
    metadata, code, models, documents = {}, [], [], []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in OMIT]
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(root)
            if name in {'RELEASE_AUDIT.md','QCost-reproducible.zip','QCost-reproducible.zip.sha256','QCost-reproducible.files.txt'}:
                continue
            info = path.stat()
            metadata[relative.as_posix()] = [info.st_size, info.st_mtime_ns]
            key = relative.parts[0]
            counts[key] += 1
            sizes[key] += info.st_size
            in_library = any(part in LIBRARY for part in relative.parts)
            if not in_library and path.suffix.lower() in (SOURCE_SUFFIXES - {'.json'}) and info.st_size <= 2_000_000:
                # Hash source/config files, not multi-GB scalar logs or data payloads.
                row = dict(path=relative.as_posix(), bytes=info.st_size, sha256=digest(path))
                code.append(row)
            if not in_library and path.suffix.lower() in MODEL_SUFFIXES:
                models.append(dict(path=relative.as_posix(), bytes=info.st_size,
                                   sha256=digest(path) if info.st_size <= 32_000_000 else None))
            if not in_library and name.lower().startswith('readme'):
                documents.append(dict(path=relative.as_posix(), bytes=info.st_size, sha256=digest(path)))
    return metadata, dict(counted_files=len(metadata), logical_bytes=sum(v[0] for v in metadata.values()),
        scope='Recursive metadata inventory, excluding Git history, runtime caches and this new delivery; filesystem allocation is reported separately',
        directories={k: dict(files=counts[k],bytes=sizes[k]) for k in sorted(counts)},
        source_candidates=code, model_candidates=models, original_readme_documents=documents)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--snapshot', type=Path, required=True)
    p.add_argument('--verify', action='store_true')
    p.add_argument('--inventory', type=Path, default=Path(__file__).resolve().parents[1] / 'docs/source_inventory.json')
    a = p.parse_args()
    metadata, inventory = collect(a.source_root.resolve())
    if a.verify:
        previous = json.loads(a.snapshot.read_text())
        changed = [k for k in set(previous) | set(metadata) if previous.get(k) != metadata.get(k)]
        before_inventory = json.loads(a.inventory.read_text())
        keys = ['source_candidates','model_candidates','original_readme_documents']
        before = {r['path']:r['sha256'] for k in keys for r in before_inventory[k] if r['sha256'] is not None}
        after = {r['path']:r['sha256'] for k in keys for r in inventory[k] if r['sha256'] is not None}
        changed_hashes = [k for k in set(before) | set(after) if before.get(k) != after.get(k)]
        result = dict(status='PASS' if not changed and not changed_hashes else 'CHANGED',
                      checked_files=len(metadata), checked_content_hashes=len(before),
                      changed=sorted(changed), changed_hashes=sorted(changed_hashes))
        a.output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
        raise SystemExit(0 if not changed and not changed_hashes else 1)
    a.snapshot.write_text(json.dumps(metadata, sort_keys=True) + '\n')
    a.output.write_text(json.dumps(inventory, indent=2) + '\n')
    print(json.dumps(dict(files=inventory['counted_files'],bytes=inventory['logical_bytes'],
                         source_candidates=len(inventory['source_candidates']),models=len(inventory['model_candidates']),
                         readme_documents=len(inventory['original_readme_documents']))))

if __name__ == '__main__':
    main()
