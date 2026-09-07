"""Remove non-runtime material only from the explicitly named training delivery."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path


def excluded(path: Path) -> bool:
    parts = path.parts
    return (any(p.startswith('.env') or p in {'tests', 'tests-e2e', '__tests__', 'docs', '__pycache__', '.git'} for p in parts)
            or path.suffix.lower() in {'.md', '.pdf', '.docx', '.xlsx', '.pyc'}
            or bool(re.search(r'\.(test|spec)\.[^.]+$', path.name))
            or path.name in {'vitest.config.ts', 'playwright.config.ts', 'tokens.json'}
            or 'content/knowledge/images/' in path.as_posix())


def sanitized(path: Path, data: bytes) -> bytes:
    name = path.as_posix()
    if name.endswith('app/services/seller_shop_service.py'):
        text = data.decode()
        if '_SHOP_MANAGER_EMAIL_MARKERS: tuple[str, ...] = ()' in text:
            return data
        text, count = re.subn(r'_SHOP_MANAGER_EMAIL_MARKERS = \(.*?\n\)',
                             '_SHOP_MANAGER_EMAIL_MARKERS: tuple[str, ...] = ()', text, flags=re.S)
        if count != 1:
            raise ValueError('Unexpected shop-manager source; review before exporting')
        return text.encode()
    if name.endswith('billing-report/stub.ts'):
        return data.replace(b'Denmarcs', b'Training seller')
    if 'knowledge/scenes/' in name and path.suffix == '.tsx':
        return data.replace(b'@korob-vms.ru', b'@example.com')
    if name.endswith('frontend/package.json'):
        value = json.loads(data)
        value['scripts'].pop('test:unit', None)
        return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if root != Path('/opt/wms-training') or not (root / 'compose.yaml').is_file():
        raise SystemExit('Only /opt/wms-training on the destination host is permitted')
    removed, changed = [], []
    for path in sorted((root / 'src').rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(root / 'src')
        if excluded(relative):
            path.unlink()
            removed.append(str(relative))
        else:
            before = path.read_bytes()
            after = sanitized(relative, before)
            if before != after:
                path.write_bytes(after)
                changed.append(str(relative))
    for path in (root / 'src').rglob('*'):
        if path.is_file() and excluded(path.relative_to(root / 'src')):
            raise RuntimeError(f'Excluded file remains: {path}')
    print(json.dumps({'removed_files': removed, 'sanitized_files': changed}, indent=2))


if __name__ == '__main__':
    main()
