#!/usr/bin/env python3
"""WMS-652 direct server gate: public GET metadata only, no token or gh dependency.

Raw execution reports are verified by the frozen process-proof CI pipeline and
DeployProduction verifier; this gate independently verifies their provenance.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.verify_ci import GateError, pages, verify

# Verified origin URL: https://github.com/chivkunovd-bitdenis/WMS.git.
# A shell environment override must never choose an easier repository's green CI.
REPOSITORY = 'chivkunovd-bitdenis/WMS'
EXTRA_JOBS = {'print-regressions', 'printer-windows', 'process-proof'}
MAX_JSON = 8 * 1024 * 1024
MAX_ARTIFACT = 64 * 1024 * 1024


def public_api_get(path):
    if not isinstance(path, str) or not path.startswith('repos/') or '#' in path or '\\' in path:
        raise GateError('Некорректный путь публичной проверки GitHub', 3)
    request = Request('https://api.github.com/' + path, method='GET', headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': 'wms-server-process-gate',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read(MAX_JSON + 1)
        if len(raw) > MAX_JSON:
            raise GateError('Публичный ответ GitHub превышает допустимый размер', 3)
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise GateError('Публичный GitHub не вернул объект метаданных', 3)
        return data
    except (URLError, OSError, ValueError) as exc:
        # No response bodies, credentials or raw CLI/network errors in deployment logs.
        raise GateError('Публичные метаданные CI GitHub недоступны; выпуск остановлен', 3) from exc


def verify_server_ci(get, repository, sha):
    """Server verifies for itself; no verified=1 flag or caller-supplied success."""
    try:
        run = verify(get, repository, sha)
        root = f'repos/{repository}'
        jobs = pages(get, f"{root}/actions/runs/{run['run_id']}/attempts/{run['run_attempt']}/jobs", 'jobs')
        for name in sorted(EXTRA_JOBS):
            matches = [job for job in jobs if job['name'] == name]
            allowed = {'success', 'skipped'} if run['docs_only'] and name in {
                'print-regressions', 'printer-windows'
            } else {'success'}
            if (len(matches) != 1 or any(matches[0].get(key) != value for key, value in {
                    'head_sha': sha, 'run_id': run['run_id'], 'status': 'completed'}.items()) or
                    matches[0].get('conclusion') not in allowed):
                raise GateError('Сервер не подтвердил обязательную задачу CI: ' + name)
        name = f"process-proof-{sha}-{run['run_id']}-{run['run_attempt']}"
        artifacts = pages(get, f"{root}/actions/runs/{run['run_id']}/artifacts", 'artifacts')
        matches = [artifact for artifact in artifacts if artifact['name'] == name]
        if len(matches) != 1:
            raise GateError('Сервер не нашёл единственный отчёт текущей попытки CI')
        artifact = matches[0]
        if (artifact['expired'] is not False or type(artifact['size_in_bytes']) is not int or
                not 0 < artifact['size_in_bytes'] <= MAX_ARTIFACT or
                artifact['workflow_run']['id'] != run['run_id'] or
                artifact['workflow_run']['head_sha'] != sha):
            raise GateError('Отчёт CI просрочен, недоступен или принадлежит другой версии')
        if verify(get, repository, sha) != run:
            raise GateError('CI изменился во время серверной проверки; выпуск остановлен', 4)
        return {**run, 'artifact_id': artifact['id'], 'proof': 'frozen-ci-validated-artifact-metadata'}
    except GateError:
        raise
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise GateError('Сервер не смог подтвердить метаданные обязательных процессов', 3) from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sha', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify_server_ci(public_api_get, REPOSITORY, args.sha), sort_keys=True))
        return 0
    except GateError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == '__main__':
    sys.exit(main())
