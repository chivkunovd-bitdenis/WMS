#!/usr/bin/env python3
"""Verify exact etalon CI AND actual mandatory cases before allowing deployment."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.process_contracts import POLICY_PATH, relative_path, verify_reports
from scripts.ci.verify_ci import GateError, api_get, pages, verify

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024


def download_artifact(path: str) -> bytes:
    try:
        result = subprocess.run(['gh', 'api', '--method', 'GET', '--hostname', 'github.com', path],
                                check=True, capture_output=True, timeout=90)
        if len(result.stdout) > MAX_ARCHIVE:
            raise GateError('Отчёт исполнения превышает допустимый размер')
        return result.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise GateError('Не удалось получить обязательный отчёт исполнения', 3) from exc


def verify_execution(get, download, repository: str, sha: str, policy_bytes: bytes) -> dict:
    """No external mutations. Missing proof always refuses, including API errors."""
    run = verify(get, repository, sha)
    root = f'repos/{repository}'
    try:
        jobs = pages(get, f"{root}/actions/runs/{run['run_id']}/attempts/{run['run_attempt']}/jobs", 'jobs')
        proof = [job for job in jobs if job['name'] == 'process-proof']
        if len(proof) != 1 or any(proof[0].get(key) != value for key, value in {
            'head_sha': sha, 'run_id': run['run_id'], 'status': 'completed', 'conclusion': 'success'
        }.items()):
            raise GateError('Обязательная проверка process-proof не подтвердила исполнение сценариев')
        name = f"process-proof-{sha}-{run['run_id']}-{run['run_attempt']}"
        artifacts = pages(get, f"{root}/actions/runs/{run['run_id']}/artifacts", 'artifacts')
        matches = [artifact for artifact in artifacts if artifact['name'] == name]
        if len(matches) != 1:
            raise GateError('Отчёт исполнения отсутствует или неоднозначен')
        artifact = matches[0]
        if (artifact['expired'] or artifact['size_in_bytes'] > MAX_ARCHIVE or
                artifact['workflow_run']['id'] != run['run_id'] or
                artifact['workflow_run']['head_sha'] != sha):
            raise GateError('Отчёт не принадлежит проверенной версии/запуску либо недоступен')
        raw = download(f"{root}/actions/artifacts/{artifact['id']}/zip")
        if len(raw) > MAX_ARCHIVE:
            raise GateError('Слишком большой архив исполнения')
        policy = json.loads(policy_bytes)
        docs_only = run.get('docs_only') is True
        required_files = {'execution.json'} if docs_only else {
            'execution.json', *(suite['report'] for suite in policy['suites'].values())}
        with zipfile.ZipFile(io.BytesIO(raw)) as archive, tempfile.TemporaryDirectory(prefix='wms-ci-proof-') as tmp:
            infos = archive.infolist()
            names = [info.filename for info in infos if not info.is_dir()]
            if len(names) != len(set(names)) or len(infos) > 512:
                raise GateError('Повторяющиеся или избыточные файлы отчёта')
            if sum(info.file_size for info in infos) > MAX_EXPANDED:
                raise GateError('Распакованный отчёт превышает допустимый размер')
            for info in infos:
                relative_path(info.filename.rstrip('/'))
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise GateError('Ссылки в архиве исполнения запрещены')
            if not required_files.issubset(names):
                raise GateError('В архиве отсутствует обязательный отчёт сценария')
            metadata = json.loads(archive.read('execution.json'))
            expected = dict(version=1, sha=sha, head_sha=sha, run_id=run['run_id'],
                            run_attempt=run['run_attempt'], policy_sha256=hashlib.sha256(policy_bytes).hexdigest())
            expected['docs_only'] = docs_only
            if any(metadata.get(key) != value for key, value in expected.items()):
                raise GateError('Отчёт относится к другой версии, попытке или набору обязательных сценариев')
            baseline = metadata.get('base_sha')
            if (not isinstance(baseline, str) or not re.fullmatch('[0-9a-f]{40}', baseline)
                    or baseline in {'0'*40, sha}):
                raise GateError('В отчёте отсутствует допустимый отдельный SHA базы сравнения')
            if docs_only:
                cases = {}
            else:
                report_root = Path(tmp)
                for name in required_files - {'execution.json'}:
                    path = report_root / relative_path(name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.read(name))
                cases = verify_reports(policy, report_root, sha=sha)
        # A rerun/new run during artifact download invalidates even a complete report.
        if verify(get, repository, sha) != run:
            raise GateError('CI изменился во время чтения отчёта; нужна повторная проверка', 4)
        return {**run, 'suites': sorted(cases), 'executed_cases': sum(map(len, cases.values()))}
    except GateError:
        raise
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError) as exc:
        raise GateError(f'Обязательные сценарии не подтверждены ({type(exc).__name__})', 3) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--sha', required=True)
    args = parser.parse_args()
    try:
        # Identity validation precedes all content requests; no symbolic refs accepted.
        verify(api_get, args.repository, args.sha)
        data = api_get(f'repos/{args.repository}/contents/{POLICY_PATH}?ref={args.sha}')
        if data['encoding'] != 'base64' or data['path'] != POLICY_PATH:
            raise GateError('Нет проверяемого контракта обязательных сценариев')
        policy = base64.b64decode(data['content'])
        result = verify_execution(api_get, download_artifact, args.repository, args.sha, policy)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except GateError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    except (KeyError, ValueError, TypeError) as exc:
        print(f'Не удалось прочитать контракт сценариев ({type(exc).__name__})', file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
