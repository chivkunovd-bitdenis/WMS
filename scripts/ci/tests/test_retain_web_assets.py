"""Old browser tabs retain assets while candidate bytes remain immutable."""
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('retain_web_assets', ROOT / 'scripts/deploy/retain-web-assets.py')
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_preserves_old_root_and_seller_assets_and_every_new_byte(tmp_path):
    old, new, delta = (tmp_path / name for name in ('old', 'new', 'delta'))
    write(old, 'assets/screen-old123.js', b'old browser chunk')
    write(old, 'seller/assets/seller-old123.js', b'old seller chunk')
    write(old, 'assets/shared-hash12.css', b'shared')
    write(old, 'index.html', b'old index must never be retained')
    write(new, 'assets/shared-hash12.css', b'shared')
    write(new, 'assets/screen-new123.js', b'new browser chunk')
    write(new, 'index.html', b'candidate index')
    before = assets.asset_files(new)
    manifest = tmp_path / 'manifest.json'
    assert assets.prepare(old, new, delta, manifest) == 2
    assert assets.asset_files(new) == before
    assert not (delta / 'index.html').exists()
    assert not (delta / 'assets/shared-hash12.css').exists()
    shutil.copytree(delta, new, dirs_exist_ok=True)
    assets.verify(new, manifest)
    assert (new / 'index.html').read_bytes() == b'candidate index'
    assert all(assets.asset_files(new)[name] == digest for name, digest in before.items())


def test_collision_fails_before_any_delta_write(tmp_path):
    old, new, delta = (tmp_path / name for name in ('old', 'new', 'delta'))
    write(old, 'assets/collision-hash12.js', b'old')
    write(old, 'assets/other-old123.js', b'old other')
    write(new, 'assets/collision-hash12.js', b'new')
    with pytest.raises(ValueError, match='different bytes'):
        assets.prepare(old, new, delta, tmp_path / 'manifest.json')
    assert not delta.exists()
    assert (new / 'assets/collision-hash12.js').read_bytes() == b'new'


@pytest.mark.parametrize('failure', ['missing', 'corrupted', 'extra'])
def test_readback_fails_closed_for_missing_corrupt_or_unexpected_asset(tmp_path, failure):
    old, new, delta = (tmp_path / name for name in ('old', 'new', 'delta'))
    write(old, 'assets/old-hash12.js', b'old')
    write(new, 'assets/new-hash12.js', b'new')
    manifest = tmp_path / 'manifest.json'
    assets.prepare(old, new, delta, manifest)
    shutil.copytree(delta, new, dirs_exist_ok=True)
    if failure == 'missing':
        (new / 'assets/old-hash12.js').unlink()
    else:
        write(new, 'assets/new-hash12.js' if failure == 'corrupted' else 'assets/extra-hash12.js', b'wrong')
    with pytest.raises(ValueError, match='checksums differ'):
        assets.verify(new, manifest)


def test_symlinks_are_rejected_and_empty_previous_is_supported(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    write(new, 'assets/new-hash12.js', b'new')
    manifest = tmp_path / 'manifest.json'
    assert assets.prepare(old, new, tmp_path / 'delta', manifest) == 0
    assets.verify(new, manifest)
    (new / 'assets/link.js').symlink_to(new / 'assets/new-hash12.js')
    with pytest.raises(ValueError, match='Symlink'):
        assets.asset_files(new)
    assert json.loads(manifest.read_text())['added'] == []


@pytest.mark.parametrize('fail_commit', [False, True])
def test_deploy_stages_before_traffic_and_cleans_temporary_container(tmp_path, fail_commit):
    import os
    import subprocess

    write(tmp_path / 'previous', 'assets/old-hash12.js', b'old')
    write(tmp_path / 'candidate', 'assets/new-hash12.js', b'new')
    write(tmp_path / 'candidate', 'index.html', b'candidate index')
    executable = tmp_path / 'bin/docker'
    executable.parent.mkdir()
    executable.write_text('''#!/usr/bin/env python3
import os,sys,shutil,json
from pathlib import Path
root=Path(os.environ['ASSET_TEST_ROOT']); args=sys.argv[1:]
with (root/'docker.log').open('a') as log: log.write(' '.join(args)+'\\n')
if args[:3]==['compose','ps','-q']: print('previous-web')
elif args[:2]==['compose','build']: pass
elif args[:3]==['compose','config','--images']: print('postgres:16\\nredis:7-alpine\\nintended-web:latest')
elif args[:3]==['compose','config','--format']: print(json.dumps({'name':'example','services':{'web':{'image':'intended-web:latest'}}}))
elif args[0]=='inspect': raise SystemExit('Old container tag must never select the new image')
elif args[:2]==['image','inspect']:
 assert args[-1]=='intended-web:latest'; print('candidate-image')
elif args[0]=='create':
 shutil.copytree(root/'candidate',root/'staged'); print('staged-web')
elif args[0]=='cp':
 source,target=args[1:]
 if ':' in source:
  container=source.split(':')[0]
  shutil.copytree(root/('previous' if container=='previous-web' else 'staged'),target,dirs_exist_ok=True)
 else: shutil.copytree(source,root/'staged',dirs_exist_ok=True)
elif args[0]=='commit':
 assert args[-1]=='intended-web:latest'
 if os.environ['FAIL_ASSET_COMMIT']=='1': sys.exit(33)
 shutil.copytree(root/'staged',root/'published'); print('retained-image')
elif args[0]=='rm': shutil.rmtree(root/'staged')
else: raise SystemExit('Unexpected Docker call: '+str(args))
''')
    executable.chmod(0o755)
    script = (ROOT / 'scripts/deploy/prod-update.sh').read_text()
    # Exercise the actual retained-assets segment, including its EXIT trap, while
    # replacing only Docker's filesystem boundary. No service or image is real.
    segment = script.split('# Keep assets referenced by already-open operator tabs.', 1)[1].split('\n', 1)[1]
    segment = segment.split('echo "==> start infrastructure"', 1)[0]
    result = subprocess.run(['bash', '-c', 'set -euo pipefail\nCOMPOSE=(docker compose)\n' + segment],
                            cwd=ROOT, capture_output=True, text=True,
                            env={**os.environ, 'PATH': str(executable.parent) + ':' + os.environ['PATH'],
                                 'TMPDIR': str(tmp_path), 'ASSET_TEST_ROOT': str(tmp_path),
                                 'FAIL_ASSET_COMMIT': str(int(fail_commit))})
    assert result.returncode == (33 if fail_commit else 0), result.stderr
    assert not (tmp_path / 'staged').exists()
    assert not list(tmp_path.glob('wms-web-assets.*'))
    calls = (tmp_path / 'docker.log').read_text().splitlines()
    assert calls[-1] == 'rm staged-web'
    assert not any(call.startswith(('start ', 'run ', 'compose up', 'compose stop')) for call in calls)
    if fail_commit:
        assert not (tmp_path / 'published').exists()
    else:
        assert (tmp_path / 'published/assets/old-hash12.js').read_bytes() == b'old'
        assert (tmp_path / 'published/assets/new-hash12.js').read_bytes() == b'new'
        assert (tmp_path / 'published/index.html').read_bytes() == b'candidate index'


def test_dangling_directory_and_symlinked_seller_parent_fail_closed(tmp_path):
    (tmp_path / 'assets').symlink_to(tmp_path / 'absent')
    with pytest.raises(ValueError, match='Symlink'):
        assets.asset_files(tmp_path)
    (tmp_path / 'assets').unlink()
    write(tmp_path / 'outside', 'assets/old-hash12.js', b'outside')
    (tmp_path / 'seller').symlink_to(tmp_path / 'outside')
    with pytest.raises(ValueError, match='Symlink'):
        assets.asset_files(tmp_path)


@pytest.mark.parametrize('explicit,project,images,expected', [
    ('declared:new', 'production', ['postgres:16', 'redis:7-alpine', 'declared:new'], 'declared:new'),
    (None, 'production', ['production-api', 'production-web'], 'production-web'),
    (None, 'production', ['production_api', 'production_web'], 'production_web'),
])
def test_image_selection_uses_current_compose_service_not_previous_container(explicit, project, images, expected):
    assert assets.resolve_image_tag({'name': project, 'services': {'web': {'image': explicit}}}, images) == expected


@pytest.mark.parametrize('images', [['production-api'], ['production-web', 'production_web']])
def test_image_selection_refuses_missing_or_ambiguous_build_target(images):
    with pytest.raises(ValueError, match='exactly one'):
        assets.resolve_image_tag({'name': 'production', 'services': {'web': {}}}, images)
