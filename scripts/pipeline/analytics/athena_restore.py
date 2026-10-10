"""Explicit, bounded GitHub artifact restoration. Data only; no AWS client.

The caller supplies the approved source identity and hashes. GitHub metadata is
reconciled independently before copying the exact plan/journal into the executor.
No latest-artifact lookup, arbitrary download URL or reconstructed-byte fallback.
"""
import argparse
from dataclasses import dataclass, asdict
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import threading
import zipfile
import zlib

from scripts.pipeline.analytics import athena_poc as a, poc
from scripts.pipeline.analytics.ingestion_types import IngestionError, check, hash_id
from scripts.pipeline.analytics.spdx import canonical, document, read_local, sha256

REPOSITORY = 'alric-corp/alric-containers-image-base'
WORKFLOW = '.github/workflows/sbom-analytics-athena-lab-poc.yml'
REPOSITORY_ID = 1360616627
ZIP_LIMIT = 16 * 1024 * 1024
EXPANSION_LIMIT = 32 * 1024 * 1024
MEMBER_LIMIT = 64
JOURNAL_LIMIT = 16 * 1024 * 1024
ALLOWED = frozenset('athena-reports/' + name + '.json' for name in (
    'execution-failure', 'authentication', 'catalog-proposal', 'execution-journal', 'identity', 'resources-before',
    'resources-after', 'recovered-inspection', 'result', 'snapshot-after', 'snapshot-before', 'sql-plan',
    'resume-receipt', 'resume-diagnostic')) | frozenset((
        'analytics-dependencies.txt', 'athena-resume-source/source-artifact.zip',
        'athena-resume-source/execution-journal.json', 'athena-resume-source/sql-plan.json'))
REQUIRED = ('athena-reports/execution-journal.json', 'athena-reports/sql-plan.json', 'athena-reports/authentication.json')


@dataclass(frozen=True)
class ResumeSource:
    run_id: int
    attempt: int
    artifact_id: int
    source_sha: str
    zip_sha256: str
    zip_bytes: int
    journal_sha256: str
    journal_bytes: int
    sql_plan_sha256: str
    sql_plan_bytes: int

    def __post_init__(self):
        for value in (self.run_id, self.attempt, self.artifact_id):
            check(type(value) is int and 0 < value < 2**63, 'RESUME_SOURCE_ID_INVALID')
        check(type(self.source_sha) is str and re.fullmatch('[0-9a-f]{40}', self.source_sha), 'RESUME_SOURCE_SHA_INVALID')
        for value in (self.zip_sha256, self.journal_sha256, self.sql_plan_sha256):
            hash_id(value)
        for value, limit in ((self.zip_bytes, ZIP_LIMIT), (self.journal_bytes, JOURNAL_LIMIT),
                             (self.sql_plan_bytes, a.PLAN_LIMIT)):
            check(type(value) is int and 0 < value <= limit, 'RESUME_SOURCE_SIZE_INVALID')


def source_document(raw):
    value = document(raw, limit=4096)
    check(set(value) == set(ResumeSource.__dataclass_fields__), 'RESUME_SOURCE_FIELDS_INVALID')
    return ResumeSource(**value)


class GitHubActions:
    """Only explicit gh API reads on github.com; GH_TOKEN belongs to the caller."""
    def _read(self, path, limit):
        check(path.startswith('repos/' + REPOSITORY + '/'), 'RESUME_API_PATH_INVALID')
        with subprocess.Popen(['gh', 'api', '--hostname', 'github.com', path], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL) as process:
            timer = threading.Timer(60, process.kill)
            timer.start()
            try:
                raw = process.stdout.read(limit + 1)
                if len(raw) > limit:
                    process.kill()
                code = process.wait(timeout=5)
            finally:
                timer.cancel()
        check(code == 0 and len(raw) <= limit, 'RESUME_GITHUB_READ_ERROR', stage='RESTORE', operation='GET', key=path)
        return raw

    def get_json(self, path):
        return document(self._read(path, 2 * 1024 * 1024), limit=2 * 1024 * 1024)

    def download(self, artifact_id):
        return self._read(f'repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip', ZIP_LIMIT)


def acquisition(client, source):
    root = 'repos/' + REPOSITORY + '/'
    workflow = client.get_json(root + 'actions/workflows/' + WORKFLOW.rsplit('/', 1)[1])
    run = client.get_json(root + f'actions/runs/{source.run_id}/attempts/{source.attempt}')
    check(workflow.get('path') == WORKFLOW and run.get('workflow_id') == workflow.get('id')
          and run.get('path') == WORKFLOW and run.get('id') == source.run_id
          and type(run.get('run_attempt')) is int
          and run.get('run_attempt') == source.attempt and run.get('head_sha') == source.source_sha
          and run.get('event') == 'workflow_dispatch' and run.get('head_branch') == 'develop'
          and run.get('status') == 'completed' and run.get('conclusion') in ('failure', 'success'),
          'RESUME_RUN_IDENTITY_DIFFERS')
    for key in ('repository', 'head_repository'):
        check(run.get(key, {}).get('full_name') == REPOSITORY
              and run[key].get('id') == REPOSITORY_ID, 'RESUME_REPOSITORY_DIFFERS')
    artifact = client.get_json(root + f'actions/artifacts/{source.artifact_id}')
    check(artifact.get('id') == source.artifact_id and artifact.get('name') == f'sbom-athena-{source.run_id}-{source.attempt}'
          and artifact.get('expired') is False and artifact.get('size_in_bytes') == source.zip_bytes,
          'RESUME_ARTIFACT_IDENTITY_DIFFERS')
    binding = artifact.get('workflow_run', {})
    check(all(binding.get(k) == v for k, v in dict(id=source.run_id, repository_id=REPOSITORY_ID,
          head_repository_id=REPOSITORY_ID, head_branch='develop', head_sha=source.source_sha).items()),
          'RESUME_ARTIFACT_RUN_DIFFERS')
    digest = artifact.get('digest')
    check(digest is None or digest == 'sha256:' + source.zip_sha256, 'RESUME_API_DIGEST_DIFFERS')
    jobs = []
    for page in range(1, 5):
        value = client.get_json(root + f'actions/runs/{source.run_id}/attempts/{source.attempt}/jobs?per_page=100&page={page}')
        check(type(value.get('jobs')) is list and type(value.get('total_count')) is int
              and len(value['jobs']) <= 100, 'RESUME_JOBS_INVALID')
        jobs.extend(value['jobs'])
        if len(jobs) == value['total_count']:
            break
        check(len(jobs) < value['total_count'] and value['jobs'], 'RESUME_JOBS_INVALID')
    else:
        raise IngestionError('RESUME_JOB_PAGE_LIMIT')
    producers = [j for j in jobs if j.get('name') == 'athena' and j.get('run_id') == source.run_id
                 and type(j.get('run_attempt')) is int
                 and j.get('run_attempt') == source.attempt and j.get('head_sha') == source.source_sha]
    check(len(producers) == 1, 'RESUME_PRODUCER_ATTEMPT_DIFFERS')
    created = a._epoch(artifact['created_at'])
    uploads = [s for s in producers[0].get('steps', []) if s.get('name') ==
               'Upload diagnostics, frozen SQL and journal including failure' and s.get('conclusion') == 'success']
    check(len(uploads) == 1 and a._epoch(uploads[0]['started_at']) <= created <=
          a._epoch(uploads[0]['completed_at']), 'RESUME_ARTIFACT_PRODUCER_INCONCLUSIVE')
    return dict(run={k: run[k] for k in ('id', 'run_attempt', 'workflow_id', 'path', 'head_sha', 'event',
                                       'head_branch', 'status', 'conclusion')},
                artifact={k: artifact.get(k) for k in ('id', 'name', 'size_in_bytes', 'digest', 'created_at')},
                producer_job_id=producers[0]['id'], api_digest='VERIFIED' if digest else 'NOT_AVAILABLE')


def archive_members(raw):
    """Bounded central/local headers, descriptors, CRC and streamed expansion.

    v1: 16 MiB ZIP, 32 MiB expanded, 64 entries, 512-byte paths. Only reviewed
    report members are allowed; only the three required documents are extracted.
    The observed GitHub ZIP uses signed data descriptors; unsigned ones are also
    checked field by field. ZIP64, trailing/unlisted bytes and special files fail.
    """
    check(type(raw) is bytes and 22 <= len(raw) <= ZIP_LIMIT, 'RESUME_ZIP_LIMIT')
    end = struct.unpack('<4s4H2IH', raw[-22:])
    check(end[0] == b'PK\x05\x06' and end[1:3] == (0, 0) and end[3] == end[4]
          and 0 < end[4] <= MEMBER_LIMIT and end[-1] == 0 and end[5] <= 256 * 1024
          and end[6] + end[5] == len(raw)-22, 'RESUME_ZIP_LAYOUT_INVALID')
    selected, inventory, total, seen, previous = {}, [], 0, set(), 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = sorted(archive.infolist(), key=lambda i: i.header_offset)
            check(len(infos) == end[4], 'RESUME_ZIP_LAYOUT_INVALID')
            for info in infos:
                name = info.filename
                check(name in ALLOWED and len(name.encode()) <= 512 and name.casefold() not in seen
                      and info.orig_filename == name and not info.extra and not info.comment
                      and not info.is_dir() and not info.external_attr & 0x10 and not info.flag_bits & ~0x808
                      and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                      and stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG), 'RESUME_ZIP_MEMBER_INVALID')
                seen.add(name.casefold())
                limit = JOURNAL_LIMIT if name.endswith('execution-journal.json') else (
                    ZIP_LIMIT if name.endswith('source-artifact.zip') else a.PLAN_LIMIT)
                check(0 <= info.file_size <= limit and total + info.file_size <= EXPANSION_LIMIT,
                      'RESUME_ZIP_EXPANSION_LIMIT')
                check(info.header_offset == previous, 'RESUME_ZIP_LAYOUT_INVALID')
                header = struct.unpack('<4s5H3I2H', raw[previous:previous+30])
                check(header[0] == b'PK\x03\x04' and header[2] == info.flag_bits and header[3] == info.compress_type
                      and header[6] in ((0, info.CRC) if info.flag_bits & 8 else (info.CRC,))
                      and header[7] in ((0, info.compress_size) if info.flag_bits & 8 else (info.compress_size,))
                      and header[8] in ((0, info.file_size) if info.flag_bits & 8 else (info.file_size,)),
                      'RESUME_ZIP_LAYOUT_INVALID')
                start = previous + 30 + header[9] + header[10]
                check(header[10] == 0 and raw[previous+30:previous+30+header[9]].decode(
                      'utf-8' if info.flag_bits & 0x800 else 'cp437') == name, 'RESUME_ZIP_LAYOUT_INVALID')
                previous = start + info.compress_size
                check(previous <= end[6], 'RESUME_ZIP_LAYOUT_INVALID')
                if info.flag_bits & 8:
                    signed = raw[previous:previous+4] == b'PK\x07\x08'
                    offset = previous + (4 if signed else 0)
                    check(struct.unpack('<3I', raw[offset:offset+12]) == (info.CRC, info.compress_size, info.file_size),
                          'RESUME_ZIP_LAYOUT_INVALID')
                    previous = offset + 12
                body = bytearray()
                compressed = memoryview(raw)[start:start+info.compress_size]
                decoder = zlib.decompressobj(-15) if info.compress_type == zipfile.ZIP_DEFLATED else None
                offset, pending = 0, b''
                while offset < len(compressed) or pending:
                    data = pending or compressed[offset:offset+65536]
                    if not pending:
                        offset += len(data)
                    chunk = decoder.decompress(data, min(65536, limit-len(body)+1, EXPANSION_LIMIT-total+1)) if decoder else data
                    pending = decoder.unconsumed_tail if decoder else b''
                    total += len(chunk)
                    check(len(body)+len(chunk) <= limit and total <= EXPANSION_LIMIT, 'RESUME_ZIP_EXPANSION_LIMIT')
                    body.extend(chunk)
                check(decoder is None or (decoder.eof and not decoder.unused_data), 'RESUME_ZIP_LAYOUT_INVALID')
                check(len(body) == info.file_size and zlib.crc32(body) & 0xffffffff == info.CRC, 'RESUME_ZIP_SIZE_DIFFERS')
                inventory.append(dict(path=name, size=len(body), sha256=sha256(body)))
                if name in REQUIRED:
                    selected[name] = bytes(body)
            check(previous == end[6] and set(REQUIRED) <= set(selected), 'RESUME_ZIP_REQUIRED_MEMBER_MISSING')
    except (zipfile.BadZipFile, struct.error, UnicodeError, RuntimeError, NotImplementedError, zlib.error) as error:
        raise IngestionError('RESUME_ZIP_INVALID') from error
    return selected, inventory


def _private_directory(path):
    path = Path(path)
    check(not path.is_symlink() and not path.exists(), 'RESUME_DESTINATION_EXISTS')
    path.mkdir(mode=0o700, parents=True)
    return path


def restore(client, source, reports, originals, *, executor_sha, authorized_sha256, authorization_reference,
            round_id, snapshot_id):
    check(re.fullmatch('[0-9a-f]{40}', executor_sha or '') and source.sql_plan_sha256 == hash_id(authorized_sha256),
          'RESUME_AUTHORIZATION_DIFFERS')
    metadata = acquisition(client, source)
    originals = _private_directory(originals)
    raw = client.download(source.artifact_id)
    (originals/'source-artifact.zip').write_bytes(raw)
    check(len(raw) == source.zip_bytes and sha256(raw) == source.zip_sha256, 'RESUME_ZIP_DIGEST_DIFFERS')
    selected, inventory = archive_members(raw)
    journal_raw, plan_raw, authentication_raw = (selected[name] for name in REQUIRED)
    check(len(journal_raw) == source.journal_bytes and sha256(journal_raw) == source.journal_sha256,
          'RESUME_JOURNAL_DIGEST_DIFFERS')
    check(len(plan_raw) == source.sql_plan_bytes and sha256(plan_raw) == source.sql_plan_sha256,
          'RESUME_PLAN_DIGEST_DIFFERS')
    journal = document(journal_raw, limit=JOURNAL_LIMIT)
    plan = a.validate_journal(plan_raw, journal, authorization_reference)
    check(plan['round_id'] == round_id and plan['snapshot_id'] == snapshot_id and journal['executions'],
          'RESUME_ROUND_DIFFERS')
    authentication = document(authentication_raw, limit=65536)
    check(authentication.get('source_sha') == source.source_sha and authentication.get('run_id') == str(source.run_id)
          and authentication.get('attempt') == str(source.attempt) and authentication.get('round_id') == round_id
          and authentication.get('mode') == 'execute' and authentication.get('outcome') == 'success'
          and authentication.get('cloud_admin_fallback') is False,
          'RESUME_AUTHENTICATION_DIFFERS')
    # Originals stay unmodified; the executor may only mutate the working copy.
    for name, body in (('execution-journal.json', journal_raw), ('sql-plan.json', plan_raw)):
        (originals/name).write_bytes(body)
    reports = Path(reports)
    check(not reports.is_symlink(), 'RESUME_DESTINATION_EXISTS')
    reports.mkdir(mode=0o700, parents=True, exist_ok=True)
    check(all(not (reports/name).exists() and not (reports/name).is_symlink() for name in (
        'execution-journal.json', 'sql-plan.json', 'resume-receipt.json')), 'RESUME_DESTINATION_EXISTS')
    for name, body in (('execution-journal.json', journal_raw), ('sql-plan.json', plan_raw)):
        with (reports/name).open('xb') as stream:
            stream.write(body)
        os.chmod(reports/name, 0o600)
    receipt = dict(protocol_version=1, status='RESTORED_VERIFIED', source=asdict(source), acquisition=metadata,
                   executor_source_sha=executor_sha, authorization_reference=authorization_reference,
                   round_id=round_id, snapshot_id=snapshot_id, members=inventory,
                   restored_executions=len(journal['executions']), total_round_budget=18,
                   remaining_unreserved_executions=18-len(journal['executions']))
    poc.write_json(reports/'resume-receipt.json', receipt)
    return receipt


def validate_working_restore(receipt_path, reports, *, executor_sha, plan_sha256, authorization_reference,
                             round_id, snapshot_id):
    receipt_path, reports = Path(receipt_path), Path(reports)
    check(receipt_path == reports/'resume-receipt.json', 'RESUME_RECEIPT_PATH_DIFFERS')
    receipt = document(read_local(receipt_path, 65536), limit=65536)
    check(set(receipt) == {'protocol_version', 'status', 'source', 'acquisition', 'executor_source_sha',
          'authorization_reference', 'round_id', 'snapshot_id', 'members', 'restored_executions', 'total_round_budget',
          'remaining_unreserved_executions'} and type(receipt.get('protocol_version')) is int,
          'RESUME_RECEIPT_DIFFERS')
    source = source_document(canonical(receipt['source']))
    check(receipt.get('status') == 'RESTORED_VERIFIED' and receipt.get('protocol_version') == 1
          and receipt['executor_source_sha'] == executor_sha and source.sql_plan_sha256 == plan_sha256
          and receipt['authorization_reference'] == authorization_reference and receipt['round_id'] == round_id
          and receipt['snapshot_id'] == snapshot_id, 'RESUME_RECEIPT_DIFFERS')
    journal = read_local(reports/'execution-journal.json', JOURNAL_LIMIT)
    plan = read_local(reports/'sql-plan.json', a.PLAN_LIMIT)
    check(len(journal) == source.journal_bytes and sha256(journal) == source.journal_sha256
          and len(plan) == source.sql_plan_bytes and sha256(plan) == plan_sha256, 'RESUME_WORKING_BYTES_DIFFER')
    a.validate_journal(plan, document(journal, limit=JOURNAL_LIMIT), authorization_reference)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'reports', 'originals', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('executor-sha', 'authorized-plan-sha256', 'authorization-reference', 'round-id', 'snapshot-id'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    try:
        result = restore(GitHubActions(), source_document(read_local(args.source, 4096)), args.reports, args.originals,
                         executor_sha=args.executor_sha, authorized_sha256=args.authorized_plan_sha256,
                         authorization_reference=args.authorization_reference, round_id=args.round_id, snapshot_id=args.snapshot_id)
    except Exception as error:
        result = error.diagnostic() if isinstance(error, IngestionError) else dict(status='ERROR', code='RESUME_INVALID', stage='RESTORE')
    poc.write_json(args.report, result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'RESTORED_VERIFIED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
