#!/usr/bin/env python3
"""Select successful process-proof reports from this exact workflow run."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request


# wms686-mockup is optional (runs only when its own directory changes), so its
# skipped execution must not be required here; a failing run still fails CI itself.
PRODUCERS = {
    'backend': 'backend-executed-contracts',
    'frontend-build': 'frontend-executed-contracts',
    'printer-windows': 'printer-windows-contracts',
    'print-regressions': 'release-print',
    'охрана': 'guard-executed-contracts',
}


class SelectionError(ValueError):
    pass


def _timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (AttributeError, TypeError, ValueError) as exc:
        raise SelectionError('Invalid GitHub job/artifact timestamp') from exc


def _actual_job_attempt(job_attempts: list[dict], job_name: str, *, run_id: int,
                        candidate_sha: str) -> tuple[int, dict]:
    """Return latest distinct execution; attempt API repeats unchanged jobs."""
    latest = None
    prior_signature = None
    for attempt, jobs in enumerate(job_attempts, start=1):
        matches = [job for job in jobs if job.get('name') == job_name]
        if len(matches) != 1:
            raise SelectionError(f'Missing or ambiguous producer job: {job_name}')
        job = matches[0]
        if (job.get('run_id') != run_id or job.get('head_sha') != candidate_sha or
                job.get('run_attempt') != attempt):
            raise SelectionError(f'Producer job identity mismatch: {job_name}')
        if attempt == len(job_attempts) and (
                job.get('status') != 'completed' or job.get('conclusion') != 'success'):
            raise SelectionError(f'Latest producer execution did not succeed: {job_name}')
        signature = (job.get('started_at'), job.get('completed_at'),
                     job.get('status'), job.get('conclusion'))
        if not all(isinstance(value, str) and value for value in signature):
            # An earlier attempt can be cancelled or skipped before a runner
            # starts. A later successful execution is authoritative.
            if attempt == len(job_attempts):
                raise SelectionError(f'Latest producer execution has no completion time: {job_name}')
            continue
        if signature != prior_signature:
            latest = (attempt, job)
            prior_signature = signature
    if latest is None:
        raise SelectionError(f'Producer job has no execution: {job_name}')
    attempt, job = latest
    if job.get('status') != 'completed' or job.get('conclusion') != 'success':
        raise SelectionError(f'Latest producer execution did not succeed: {job_name}')
    return attempt, job


def select_artifacts(*, run_id: int, current_attempt: int, tested_sha: str,
                     candidate_sha: str, run: dict, job_attempts: list[list[dict]],
                     artifacts: list[dict]) -> dict[str, str]:
    """Bind each named report to the latest successful producer in this run."""
    if (run.get('id') != run_id or run.get('head_sha') != candidate_sha or
            len(job_attempts) != current_attempt or current_attempt < 1 or
            not re.fullmatch(r'[0-9a-f]{40}', tested_sha) or
            not re.fullmatch(r'[0-9a-f]{40}', candidate_sha)):
        raise SelectionError('Workflow run, source SHA, or attempt identity mismatch')
    selected = {}
    for job_name, prefix in PRODUCERS.items():
        attempt, job = _actual_job_attempt(job_attempts, job_name, run_id=run_id,
                                           candidate_sha=candidate_sha)
        started = _timestamp(job['started_at']) - timedelta(minutes=1)
        completed = _timestamp(job['completed_at']) + timedelta(minutes=1)
        expected_name = f'{prefix}-{tested_sha}-{run_id}-{attempt}'
        matches = [artifact for artifact in artifacts if artifact.get('name') == expected_name]
        if len(matches) != 1:
            raise SelectionError(f'Missing or ambiguous report for {job_name} attempt {attempt}')
        artifact = matches[0]
        workflow_run = artifact.get('workflow_run') or {}
        created = _timestamp(artifact.get('created_at'))
        if (artifact.get('expired') is not False or workflow_run.get('id') != run_id or
                workflow_run.get('head_sha') != candidate_sha or
                not started <= created <= completed):
            raise SelectionError(f'Report does not belong to the successful {job_name} execution')
        selected[job_name] = expected_name
    return selected


def api_json(path: str) -> dict:
    api_url = os.environ.get('GITHUB_API_URL', 'https://api.github.com').rstrip('/')
    token = os.environ.get('GH_TOKEN')
    if not token:
        raise SelectionError('GH_TOKEN is unavailable for read-only report lookup')
    request = urllib.request.Request(
        f'{api_url}/{path}', headers={'Accept': 'application/vnd.github+json',
                                      'Authorization': f'Bearer {token}',
                                      'X-GitHub-Api-Version': '2022-11-28'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise SelectionError(f'GitHub report API returned HTTP {exc.code}') from exc
    except urllib.error.URLError as exc:
        raise SelectionError(
            f'GitHub report API transport failed ({type(exc.reason).__name__})') from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise SelectionError('Could not verify this run reports through the GitHub API') from exc


def api_pages(path: str, key: str) -> list[dict]:
    rows = []
    page = 1
    while True:
        data = api_json(f'{path}?per_page=100&page={page}')
        current = data.get(key)
        if not isinstance(current, list):
            raise SelectionError(f'Invalid GitHub API response for {key}')
        rows.extend(current)
        if len(current) < 100:
            return rows
        page += 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repository = os.environ['GITHUB_REPOSITORY']
    run_id = int(os.environ['GITHUB_RUN_ID'])
    current_attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    tested_sha = os.environ['GITHUB_SHA']
    candidate_sha = os.environ['CANDIDATE_HEAD_SHA']
    root = f'repos/{repository}/actions/runs/{run_id}'
    run = api_json(root)
    job_attempts = [api_pages(f'{root}/attempts/{attempt}/jobs', 'jobs')
                    for attempt in range(1, current_attempt + 1)]
    artifacts = api_pages(f'{root}/artifacts', 'artifacts')
    selected = select_artifacts(
        run_id=run_id, current_attempt=current_attempt, tested_sha=tested_sha,
        candidate_sha=candidate_sha, run=run, job_attempts=job_attempts,
        artifacts=artifacts)
    with args.output.open('a', encoding='utf-8') as stream:
        for job_name, artifact in selected.items():
            key = {'охрана': 'guards'}.get(job_name, job_name.replace('-', '_'))
            stream.write(f'{key}={artifact}\n')
    print(json.dumps(selected, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (KeyError, ValueError, OSError, SelectionError) as exc:
        raise SystemExit(f'Process report selection failed closed: {exc}')
