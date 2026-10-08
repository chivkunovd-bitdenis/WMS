#!/usr/bin/env python3
"""Default-main WMS-652 anchor: candidate trees/policies/artifacts are data only."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.ci_scope import is_generated_evidence_output, is_prose

POLICY_PATH = 'guards/PROCESS_CONTRACTS.json'
WORKFLOW_PATH = '.github/workflows/ci.yml'
REQUIRED_JOBS = {'baseline', 'backlog', 'scope', 'backend', 'frontend-build', 'охрана',
                 'print-regressions', 'printer-windows', 'wms686-mockup', 'process-proof'}
HEAVY_JOBS = REQUIRED_JOBS - {'baseline', 'backlog', 'scope', 'охрана', 'process-proof'}
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024
MAX_METADATA = 64 * 1024


def identity(repository, number):
    if (not isinstance(repository, str) or
            not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or
            type(number) is not int or number <= 0):
        raise ValueError('Invalid repository/PR identity')


def sha(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}', value):
        raise ValueError('Exact lowercase commit/blob SHA required')
    return value


def relative_path(value):
    if (not isinstance(value, str) or not value or '\\' in value or '\x00' in value or
            PurePosixPath(value).is_absolute() or '..' in PurePosixPath(value).parts or
            str(PurePosixPath(value)) != value):
        raise ValueError('Invalid relative path')
    return value


def json_object(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    data = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(data, dict):
        raise ValueError('JSON object required')  # noqa: TRY004 - fail-closed contract
    return data


def policy(get, root, ref):
    response = get(f'{root}/contents/{POLICY_PATH}?{urlencode({"ref": ref})}')
    if response['encoding'] != 'base64' or response['path'] != POLICY_PATH:
        raise ValueError('Trusted policy unavailable; never bootstrap automatically')
    raw = base64.b64decode(''.join(response['content'].split()), validate=True)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('Policy too large')
    data = json_object(raw)
    if set(data) != {'version', 'files', 'suites'} or type(data['version']) is not int or data['version'] != 1:
        raise ValueError('Unsupported policy schema')
    if not isinstance(data['files'], dict) or not data['files'] or not isinstance(data['suites'], dict) or not data['suites']:
        raise ValueError('Protected files and suites required')
    for name, digest in data['files'].items():
        relative_path(name)
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid protected digest')
    reports = set()
    for name, suite in data['suites'].items():
        if (not re.fullmatch('[a-z0-9_-]+', name) or not isinstance(suite, dict) or
                set(suite) != {'report', 'format', 'exact', 'cases'}):
            raise ValueError('Invalid execution suite schema')
        report = relative_path(suite['report'])
        if report in reports:
            raise ValueError('Duplicate execution report')
        reports.add(report)
        if suite['format'] not in {'junit', 'vitest', 'node-tap', 'browser-json'} or type(suite['exact']) is not bool:
            raise ValueError('Invalid suite execution format')
        cases = suite['cases']
        if (not isinstance(cases, list) or not cases or
                any(not isinstance(case, str) or not case.strip() for case in cases) or
                len(cases) != len(set(cases))):
            raise ValueError('Empty or duplicate protected cases')
    return data, raw


def tree(get, root, ref):
    commit = get(f'{root}/git/commits/{ref}')
    tree_sha = sha(commit['tree']['sha'])
    response = get(f'{root}/git/trees/{tree_sha}?recursive=1')
    if response.get('truncated') is not False:
        raise ValueError('Truncated or unverifiable Git tree')
    result = {}
    for row in response['tree']:
        name = relative_path(row['path'])
        if name in result:
            raise ValueError('Duplicate Git tree path')
        result[name] = row
    return result


def bootstrap_pin(data):
    if not isinstance(data, dict) or set(data) != {'base_sha', 'source_sha'}:
        raise ValueError('Bootstrap requires exactly owner-approved base/source SHAs')
    base, source = sha(data['base_sha']), sha(data['source_sha'])
    if base == source:
        raise ValueError('Bootstrap source must be a separate reviewed commit')
    return {'base_sha': base, 'source_sha': source}


def load_approved_bootstrap():
    # This sibling belongs to the trusted-main checkout. No event/candidate/env
    # input can select a config file or approve the source commit.
    path = Path(__file__).resolve().with_name('process_bootstrap.json')
    if path.is_symlink():
        raise ValueError('Trusted bootstrap config must not be a symlink')
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_METADATA + 1)
    except FileNotFoundError:
        return None
    if len(raw) > MAX_METADATA:
        raise ValueError('Trusted bootstrap config too large')
    return bootstrap_pin(json_object(raw))


def git_blob_oid(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def require_current_policy_blob(rows, raw):
    row = rows.get(POLICY_PATH)
    if row is None or row.get('type') != 'blob' or row.get('mode') not in {'100644', '100755'}:
        raise ValueError('Current process policy missing, non-blob or symlink')
    if sha(row.get('sha')) != git_blob_oid(raw):
        raise ValueError('Current process policy bytes do not match the Git tree')
    return row


def verified_policy_snapshot(get, root, ref, rows, cache):
    data, raw = policy(get, root, ref)
    require_current_policy_blob(rows, raw)
    for name, digest in data['files'].items():
        row = rows.get(name)
        if row is None or row['type'] != 'blob' or row['mode'] not in {'100644', '100755'}:
            raise ValueError('Protected source file missing, non-blob or symlink')
        # Legacy hashes describe the source that was first accepted. They are
        # retained for audit, but ordinary reviewed edits are not pin-gated.
        sha(row['sha'])
    return data


def baseline_policy(get, root, base, approved_bootstrap):
    baseline_tree = tree(get, root, base)
    if POLICY_PATH in baseline_tree:
        data, raw = policy(get, root, base)
        require_current_policy_blob(baseline_tree, raw)
        return data, baseline_tree, None
    if approved_bootstrap is None:
        raise ValueError('Trusted BASE has no process policy; bootstrap acceptance required')
    pin = bootstrap_pin(approved_bootstrap)
    if pin['base_sha'] != base:
        raise ValueError('Bootstrap is not approved for this exact PR base')
    source = pin['source_sha']
    source_tree = tree(get, root, source)
    row = source_tree.get(POLICY_PATH)
    if row is None or row['type'] != 'blob' or row['mode'] not in {'100644', '100755'}:
        raise ValueError('Baseline policy must exist as a regular Git blob')
    sha(row['sha'])
    data = verified_policy_snapshot(get, root, source, source_tree, {})
    return data, source_tree, source


def pages(get, path, key, query=None):
    rows, seen, expected = [], set(), None
    for page in range(1, 102):
        data = get(path + '?' + urlencode({**(query or {}), 'per_page': 100, 'page': page}))
        total = data['total_count']
        if type(total) is not int or total < 0 or (key == 'workflow_runs' and total >= 1000):
            raise ValueError('Unverifiable GitHub list size')
        if expected is None:
            expected = total
        if total != expected:
            raise ValueError('GitHub list changed while paging')
        batch = data[key]
        for row in batch:
            if row['id'] in seen:
                raise ValueError('Duplicate GitHub list entry')
            seen.add(row['id'])
            rows.append(row)
        if len(rows) == expected:
            return rows
        if not batch or len(rows) > expected:
            break
    raise ValueError('Incomplete GitHub list')


def pr_head(pr, repository, number):
    if (pr['number'] != number or pr['state'] != 'open' or pr['base']['ref'] != 'etalon' or
            pr['base']['repo']['full_name'] != repository or
            pr['head']['repo']['full_name'] != repository):
        raise ValueError('An open repository PR targeting etalon is required')
    return sha(pr['head']['sha'])


def pr_scope(pr, repository, number):
    return pr_head(pr, repository, number), sha(pr['base']['sha'])


def pr_identity(pr, repository, number):
    return (*pr_scope(pr, repository, number), sha(pr['merge_commit_sha']))


def is_prose_path(path):
    return is_prose(path) or is_generated_evidence_output(path)


def pull_request_docs_only(get, root, number, expected_count):
    if type(expected_count) is not int or expected_count <= 0 or expected_count > 3000:
        return False
    paths, seen = [], set()
    for page in range(1, 31):
        batch = get(f'{root}/pulls/{number}/files?{urlencode({"per_page": 100, "page": page})}')
        if not isinstance(batch, list) or not batch:
            break
        for row in batch:
            path = row.get('filename') if isinstance(row, dict) else None
            if not isinstance(path, str) or not path or path in seen:
                raise ValueError('Pull request changed-file list is malformed or duplicated')
            seen.add(path)
            paths.append(path)
        if len(paths) >= expected_count:
            break
    if len(paths) != expected_count:
        raise ValueError('Pull request changed-file list is incomplete')
    return all(is_prose_path(path) for path in paths)


def verify_pr(get, repository, number, *, download=None, approved_bootstrap=None):
    """Read-only metadata helper; evidence_complete=False cannot authorize a check.

    The optional callback retains the pre-code metadata contract while the CLI
    always uses verify_pr_evidence, which requires a bound artifact.
    """
    if download is not None:
        return verify_pr_evidence(get, download, repository, number, approved_bootstrap=approved_bootstrap)
    identity(repository, number)
    root = f'repos/{repository}'
    pr = get(f'{root}/pulls/{number}')
    head, base, merge = pr_identity(pr, repository, number)
    docs_only = pull_request_docs_only(get, root, number, pr.get('changed_files'))
    baseline, baseline_tree, source = baseline_policy(get, root, base, approved_bootstrap)
    candidate, candidate_raw = policy(get, root, head)
    merged, merged_raw = policy(get, root, merge)
    if candidate_raw != merged_raw or candidate != merged:
        raise ValueError('Merge policy differs from the candidate policy')
    # Candidate suites and required case names are current reviewable behavior
    # contracts. The CI report gate below checks every case the candidate lists;
    # independent diff review assesses intentional changes to that list.
    trees = [baseline_tree, tree(get, root, head), tree(get, root, merge)]
    for data, candidate_policy, raw_policy in zip(trees[1:], (candidate, merged),
                                                   (candidate_raw, merged_raw)):
        require_current_policy_blob(data, raw_policy)
        for name in candidate_policy['files']:
            row = data.get(name)
            if row is None or row['type'] != 'blob' or row['mode'] not in {'100644', '100755'}:
                raise ValueError('Protected source file missing, non-blob or symlink')
    workflow = get(f'{root}/actions/workflows/ci.yml')
    if workflow['path'] != WORKFLOW_PATH or workflow['state'] != 'active':
        raise ValueError('Required CI workflow absent or disabled')

    def latest():
        runs = pages(get, f"{root}/actions/workflows/{workflow['id']}/runs", 'workflow_runs',
                     {'head_sha': head, 'event': 'pull_request'})
        matching = [run for run in runs if
                    run['workflow_id'] == workflow['id'] and
                    run['path'].split('@')[0] == WORKFLOW_PATH and
                    run['repository']['full_name'] == repository and
                    run['head_repository']['full_name'] == repository and
                    run['head_sha'] == head and run['event'] == 'pull_request' and
                    any(pr['number'] == number for pr in run['pull_requests'])]
        if not matching:
            raise ValueError('No genuine pull_request CI for this exact head')
        return max(matching, key=lambda run: (run['run_number'], run['id']))

    run = latest()
    matching_prs = [pr for pr in run['pull_requests'] if pr['number'] == number]
    if (len(matching_prs) != 1 or matching_prs[0]['head']['sha'] != head or
            matching_prs[0]['base']['sha'] != base or
            run['status'] != 'completed' or run['conclusion'] != 'success' or
            type(run['run_attempt']) is not int or run['run_attempt'] < 1):
        raise ValueError('Latest CI is incomplete, failed or tested a different PR base')
    suite = get(f"{root}/check-suites/{run['check_suite_id']}")
    if suite['app'].get('id') != 15368 or suite['app'].get('slug') != 'github-actions':
        raise ValueError('CI was not produced by GitHub Actions')
    if suite['head_sha'] != head:
        raise ValueError('Check suite belongs to another head')
    jobs = pages(get, f"{root}/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs", 'jobs')
    for name in sorted(REQUIRED_JOBS):
        matches = [job for job in jobs if job['name'] == name]
        allowed = {'success', 'skipped'} if docs_only and name in HEAVY_JOBS else {'success'}
        if (len(matches) != 1 or any(matches[0].get(key) != value for key, value in {
                'run_id': run['id'], 'head_sha': head, 'status': 'completed'}.items()) or
                matches[0].get('conclusion') not in allowed):
            raise ValueError('Required current-attempt CI job did not succeed: ' + name)
    if pr_identity(get(f'{root}/pulls/{number}'), repository, number) != (head, base, merge):
        raise ValueError('PR changed during verification')
    current = latest()
    if any(current[key] != run[key] for key in ('id', 'run_attempt', 'status', 'conclusion', 'pull_requests')):
        raise ValueError('Latest CI changed during verification')
    return {**({'bootstrap_source_sha': source} if source else {}),
            'head_sha': head, 'base_sha': base, 'merge_sha': merge, 'run_id': run['id'],
            'run_attempt': run['run_attempt'], 'policy_sha256': hashlib.sha256(candidate_raw).hexdigest(),
            'docs_only': docs_only, 'evidence_complete': False}


def verify_pr_evidence(get, download, repository, number, *, approved_bootstrap=None):
    """Strict entrypoint: verify frozen pipeline plus exact current proof metadata."""
    try:
        result = verify_pr(get, repository, number, approved_bootstrap=approved_bootstrap)
        root = f'repos/{repository}'
        name = f"process-proof-{result['merge_sha']}-{result['run_id']}-{result['run_attempt']}"
        artifacts = pages(get, f"{root}/actions/runs/{result['run_id']}/artifacts", 'artifacts')
        matches = [artifact for artifact in artifacts if artifact['name'] == name]
        if len(matches) != 1:
            raise ValueError('Exact current-attempt process proof absent or ambiguous')
        artifact = matches[0]
        if (artifact['expired'] is not False or type(artifact['size_in_bytes']) is not int or
                not 0 < artifact['size_in_bytes'] <= MAX_ARCHIVE or
                artifact['workflow_run']['id'] != result['run_id'] or
                artifact['workflow_run']['head_sha'] != result['head_sha']):
            raise ValueError('Process proof artifact provenance or size invalid')
        raw = download(f"{root}/actions/artifacts/{artifact['id']}/zip")
        if not isinstance(raw, bytes) or len(raw) > MAX_ARCHIVE:
            raise ValueError('Process proof archive too large or unavailable')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (len(infos) > 512 or len(names) != len(set(names)) or
                    sum(info.file_size for info in infos) > MAX_EXPANDED):
                raise ValueError('Duplicate or excessive proof archive entries')
            for info in infos:
                relative_path(info.filename.rstrip('/'))
                if (info.external_attr >> 16) & 0o170000 == 0o120000 or info.flag_bits & 1:
                    raise ValueError('Symlink or encrypted proof archive')
            metadata_info = archive.getinfo('execution.json')
            if metadata_info.is_dir() or metadata_info.file_size > MAX_METADATA:
                raise ValueError('Invalid or oversized execution metadata')
            metadata = json_object(archive.read(metadata_info))
            expected = {'version': 1, 'sha': result['merge_sha'], 'head_sha': result['head_sha'],
                        'base_sha': result['base_sha'], 'run_id': result['run_id'],
                        'run_attempt': result['run_attempt'], 'policy_sha256': result['policy_sha256'],
                        'docs_only': result['docs_only']}
            if any(type(metadata.get(key)) is not type(value) or metadata.get(key) != value for key, value in expected.items()):
                raise ValueError('Proof does not belong to this exact merge/head/base/run/attempt/policy')
            if not result['docs_only']:
                from scripts.ci.process_contracts import verify_reports
                current_policy, _ = policy(get, root, result['head_sha'])
                with tempfile.TemporaryDirectory(prefix='wms-process-proof-') as folder:
                    report_root = Path(folder)
                    for suite in current_policy['suites'].values():
                        report = suite['report']
                        info = archive.getinfo(report)
                        if info.is_dir() or info.file_size > MAX_EXPANDED:
                            raise ValueError('Invalid or oversized required execution report')
                        target = report_root.joinpath(*PurePosixPath(report).parts)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.read(info))
                    verify_reports(current_policy, report_root, sha=result['merge_sha'])
        if verify_pr(get, repository, number, approved_bootstrap=approved_bootstrap) != result:
            raise ValueError('PR or latest CI changed during artifact verification')
        return {**result, 'artifact_id': artifact['id'], 'evidence_complete': True}
    except ValueError:
        raise
    except (KeyError, TypeError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ValueError('Process proof unavailable or malformed') from exc


def api_get(path):
    try:
        response = subprocess.run(['gh', 'api', '--method', 'GET', '--hostname', 'github.com', path],
                                  capture_output=True, text=True, check=True, timeout=45)
        return json_object(response.stdout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('GitHub metadata unavailable') from exc


def download_artifact(path):
    try:
        response = subprocess.run(['gh', 'api', '--method', 'GET', '--hostname', 'github.com', path],
                                  capture_output=True, check=True, timeout=90)
        if len(response.stdout) > MAX_ARCHIVE:
            raise ValueError('GitHub artifact exceeds archive limit')
        return response.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('GitHub proof artifact unavailable') from exc


def publish(repository, head, conclusion, result):
    # Structured stdin is never interpreted as a shell command or human message.
    body = {'name': 'process-integrity', 'head_sha': head, 'status': 'completed', 'conclusion': conclusion,
            'output': {'title': 'Process integrity: ' + conclusion,
                       'summary': json.dumps(result, ensure_ascii=True, sort_keys=True)}}
    subprocess.run(['gh', 'api', '--hostname', 'github.com', '--method', 'POST',
                    f'repos/{repository}/check-runs', '--input', '-'],
                   input=json.dumps(body), text=True, capture_output=True, check=True, timeout=45)


def event_prs(event):
    if os.environ.get('GITHUB_EVENT_NAME') == 'pull_request_target':
        return [event['pull_request']['number']]
    if os.environ.get('GITHUB_EVENT_NAME') == 'workflow_run' and event['workflow_run']['status'] == 'completed':
        return sorted({pr['number'] for pr in event['workflow_run']['pull_requests']})
    raise ValueError('Unsupported trusted workflow event')


def failure_event_head(event, repository, number):
    """Trusted event fallback can withdraw success; it never authorizes success."""
    try:
        if event['repository']['full_name'] != repository:
            return None
        if os.environ.get('GITHUB_EVENT_NAME') == 'pull_request_target':
            return pr_head(event['pull_request'], repository, number)
        if os.environ.get('GITHUB_EVENT_NAME') != 'workflow_run':
            return None
        run = event['workflow_run']
        if (run['status'] != 'completed' or run['event'] != 'pull_request' or
                run['path'].split('@')[0] != WORKFLOW_PATH or
                run['repository']['full_name'] != repository or
                run['head_repository']['full_name'] != repository):
            return None
        matches = [pr for pr in run['pull_requests'] if pr['number'] == number]
        if (len(matches) != 1 or matches[0]['base']['ref'] != 'etalon' or
                matches[0]['head']['sha'] != run['head_sha']):
            return None
        return sha(run['head_sha'])
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--pr', type=int)
    parser.add_argument('--event')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.publish and (os.environ.get('GITHUB_ACTIONS') != 'true' or not args.event or args.pr is not None):
        parser.error('Publishing is only allowed by the installed trusted workflow event')
    try:
        event = None
        if args.event:
            with open(args.event, encoding='utf-8') as stream:
                event = json_object(stream.read())
                numbers = event_prs(event)
        elif args.pr is not None:
            numbers = [args.pr]
        else:
            raise ValueError('An exact PR number or trusted event is required')
        failed = False
        for number in numbers:
            identity(args.repository, number)
            head = None
            try:
                head = pr_scope(api_get(f'repos/{args.repository}/pulls/{number}'), args.repository, number)[0]
                result = verify_pr_evidence(api_get, download_artifact, args.repository, number,
                                            approved_bootstrap=load_approved_bootstrap())
                if result['evidence_complete'] is not True or result['head_sha'] != head:
                    raise ValueError('Exact strict proof required before publishing')
                if args.publish:
                    publish(args.repository, head, 'success', result)
                print(json.dumps(result, sort_keys=True))
            except (ValueError, KeyError, TypeError):
                failed = True
                if args.publish and head is None:
                    head = failure_event_head(event, args.repository, number)
                result = {'pr': number, 'head_sha': head, 'evidence_complete': False,
                          'reason': 'Exact trusted process proof is missing, failed or stale'}
                if args.publish and head:
                    publish(args.repository, head, 'failure', result)
                print(json.dumps(result, sort_keys=True))
        return 2 if failed else 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        print('Trusted process verification unavailable', file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
