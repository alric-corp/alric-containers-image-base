"""Opt-in intake of one explicitly selected SBOM lot into a new, closed snapshot plan.

The caller names every artifact with its run, attempt, source SHA, archive
digest and expected OCI index; nothing is discovered, scheduled or published.
Bytes come through an injected read-only source, are checked against those
claims and staged by the unchanged artifact adapter and normalizer. Each lot
becomes its own frozen snapshot plan. Lots and registered closed snapshots are
never rewritten, and an artifact already covered by one of them is refused.
No SDK, credentials, network, release Store or tag lookup. Reported identities
are cross-checked, not cryptographically authenticated.
"""
import argparse
from contextlib import contextmanager
from dataclasses import asdict
import os
from pathlib import Path
import re
import tempfile

from scripts.pipeline.analytics import artifact_input
from scripts.pipeline.analytics.artifact_identity import IdentityError, verify_identity
from scripts.pipeline.analytics.ingest import _report_destination, _write_report
from scripts.pipeline.analytics.ingestion_types import Destination, IngestionError, Limits, check
from scripts.pipeline.analytics.normalize import export, prepare, read_completed
from scripts.pipeline.analytics.snapshot import load_plan, prepare_snapshot, save_plan
from scripts.pipeline.analytics.spdx import LIMITS, canonical, document, fields, read_local, sha256

NAME = re.compile(r'[a-z0-9][a-z0-9._-]{0,63}')
PLATFORMS = ['linux/amd64', 'linux/arm64']
JSON_LIMIT = 4 * 1024 * 1024
LOT_FILES = ['lot.json', 'originals', 'plan', 'request.json', 'staging']
FLAGS = dict(publication='NOT_PUBLISHED', cloud_calls=0, cryptographic_authenticity='NOT_REVALIDATED',
             publication_authority=False)


def _reason(error):
    return ''.join(c if ' ' <= c <= '~' else '?' for c in ' '.join(str(error).split()))[:300]


def _contract(code, stage, function, *args, **kwargs):
    """Core validation failures become one fixed code; their text stays as a bounded reason."""
    try:
        return function(*args, **kwargs)
    except IngestionError:
        raise
    except (ValueError, KeyError, TypeError) as error:
        raise IngestionError(code, stage=stage, observed={'reason': _reason(error)}) from error


def _digest(value, *, oci=True):
    check(type(value) is str and re.fullmatch(('sha256:' if oci else '') + '[0-9a-f]{64}', value),
          'INVALID_DIGEST', stage='REQUEST')
    return value


def _request(value):
    """Shape and declared identities of a lot, before any artifact is read."""
    _contract('INVALID_REQUEST', 'REQUEST', fields, value, ('schema_version', 'lot_id', 'origin', 'repository_id',
              'image_registry', 'repository_prefix', 'artifacts'), label='lot request')
    check(type(value['schema_version']) is int and value['schema_version'] == 1, 'UNSUPPORTED_REQUEST', stage='REQUEST')
    check(type(value['lot_id']) is str and NAME.fullmatch(value['lot_id']), 'INVALID_LOT_ID', stage='REQUEST')
    origin = value['origin']
    check(type(origin) is dict and all(type(origin.get(k)) is int and 0 < origin[k] < 2**63 for k in ('run_id', 'run_attempt'))
          and type(origin.get('source_sha')) is str and re.fullmatch('[0-9a-f]{40}', origin['source_sha'])
          and type(origin.get('repository')) is str and type(origin.get('ref')) is str, 'INVALID_ORIGIN', stage='REQUEST')
    check(type(value['repository_id']) is int and 0 < value['repository_id'] < 2**63, 'INVALID_REQUEST', stage='REQUEST')
    artifacts = value['artifacts']
    check(type(artifacts) is list and 0 < len(artifacts) <= LIMITS['documents'] // 3, 'INVALID_REQUEST', stage='REQUEST')
    seen = set()
    for item in artifacts:
        _contract('INVALID_REQUEST', 'REQUEST', fields, item, ('framework', 'artifact_id', 'name', 'archive_sha256',
                  'archive_bytes', 'expected_index_digest'), ('expected_platforms',), label='lot artifact')
        framework, identity = item['framework'], item['artifact_id']
        check(type(framework) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]*', framework)
              and type(identity) is int and 0 < identity < 2**63
              and type(item['archive_bytes']) is int and 0 < item['archive_bytes'] <= LIMITS['batch_bytes'],
              'INVALID_REQUEST', stage='REQUEST', key=str(framework))
        _digest(item['archive_sha256'], oci=False)
        _digest(item['expected_index_digest'])
        if 'expected_platforms' in item:
            check(type(item['expected_platforms']) is dict and sorted(item['expected_platforms']) == PLATFORMS,
                  'INVALID_REQUEST', stage='REQUEST', key=framework)
            for subject in item['expected_platforms'].values():
                _digest(subject)
        keys = {('framework', framework), ('artifact_id', identity), ('archive', item['archive_sha256'])}
        check(not keys & seen, 'DUPLICATE_ARTIFACT', stage='REQUEST', key=framework)
        seen |= keys
        check(item['name'] == 'sbom-%s-%d' % (framework, origin['run_attempt']), 'ARTIFACT_ATTEMPT_DIFFERS',
              stage='REQUEST', key=framework)
    return value


def _config(value):
    _contract('INVALID_CONFIGURATION', 'REQUEST', fields, value, ('protocol_version', 'destination'), ('limits',),
              label='intake configuration')
    check(type(value['protocol_version']) is int and value['protocol_version'] == 1, 'UNSUPPORTED_CONFIGURATION',
          stage='REQUEST')
    return _contract('INVALID_CONFIGURATION', 'REQUEST', lambda: (Destination(**value['destination']),
                                                                  Limits(**value.get('limits', {}))))


class DirectoryArtifacts:
    """Artifacts the caller already acquired: <id>.zip with its saved GitHub artifact metadata <id>.json."""

    def __init__(self, directory):
        self.directory = Path(directory)

    def _path(self, artifact_id, suffix):
        path = self.directory / ('%d.%s' % (artifact_id, suffix))
        if not path.exists() and not path.is_symlink():
            raise KeyError(artifact_id)
        return path

    def describe(self, artifact_id):
        return document(read_local(self._path(artifact_id, 'json'), 65536), limit=65536)

    def read(self, artifact_id, limit):
        return read_local(self._path(artifact_id, 'zip'), limit)


def _call(operation, identity, *args):
    try:
        return operation(identity, *args)
    except LookupError as error:
        raise IngestionError('ARTIFACT_MISSING', stage='ACQUIRE', key=str(identity)) from error
    except ValueError as error:
        raise IngestionError('ARTIFACT_SOURCE_INVALID', stage='ACQUIRE', key=str(identity),
                             observed={'reason': _reason(error)}) from error
    except Exception as error:  # Transport failures are retryable; nothing was staged for this lot.
        raise IngestionError('ARTIFACT_SOURCE_ERROR', stage='ACQUIRE', key=str(identity), retryable=True,
                             observed={'exception': type(error).__name__}) from error


# The shared identity contract splits id/name into distinct codes; intake
# keeps its coarser ARTIFACT_IDENTITY_DIFFERS, and its expiry and archive-byte
# checks stay local. Everything else (run, repository/fork, source, branch) is
# the one canonical cross-check in artifact_identity.verify_identity.
_IDENTITY_CODE = dict(ARTIFACT_ID_DIFFERS='ARTIFACT_IDENTITY_DIFFERS',
                      ARTIFACT_NAME_DIFFERS='ARTIFACT_IDENTITY_DIFFERS')


def _verify_shared_identity(metadata, item, request, context):
    """Delegate the run-identity cross-check to the single contract; map codes to intake's dialect."""
    origin = request['origin']
    declared = dict(framework=item['framework'], artifact_id=item['artifact_id'], artifact_name=item['name'],
                    repository_id=request['repository_id'], run_id=origin['run_id'],
                    run_attempt=origin['run_attempt'], source_sha=origin['source_sha'], ref=origin['ref'])
    run_record = metadata.get('workflow_run_record')
    try:
        return verify_identity(declared, metadata, run_record)
    except IdentityError as error:
        raise IngestionError(_IDENTITY_CODE.get(error.code, error.code), **context) from error


def _acquire(source, item, request):
    """The source's report must match the declared identity before its bytes are kept."""
    origin, identity = request['origin'], item['artifact_id']
    context = dict(stage='ACQUIRE', key=str(identity))
    metadata = _call(source.describe, identity)
    check(type(metadata) is dict and type(metadata.get('workflow_run')) is dict, 'ARTIFACT_METADATA_INVALID', **context)
    # Expiry and archive bytes are intake-specific; the artifacts endpoint
    # reports both and neither is part of the producer-identity contract.
    check(metadata.get('expired', False) is False, 'ARTIFACT_EXPIRED', **context)
    check(metadata.get('size_in_bytes') == item['archive_bytes']
          and metadata.get('digest') in (None, 'sha256:' + item['archive_sha256']), 'ARCHIVE_DIGEST_DIFFERS', **context)
    identity_block = _verify_shared_identity(metadata, item, request, context)
    raw = _call(source.read, identity, item['archive_bytes'])
    check(type(raw) is bytes and len(raw) == item['archive_bytes'] and sha256(raw) == item['archive_sha256'],
          'ARCHIVE_DIGEST_DIFFERS', **context)
    return raw, identity_block


def _coverage(data):
    """What a batch covers, derived from its own verified records: artifacts and observation IDs."""
    artifacts = {}
    for row in data['observations']:
        key = (row['repository'], row['run_id'], row['run_attempt'], row['framework'])
        item = artifacts.setdefault(key, dict(zip(('repository', 'run_id', 'run_attempt', 'framework'), key),
                                              index_digest=row['image_index_digest'], artifact_ids=set(), sbom_sha256s=set()))
        check(item['index_digest'] == row['image_index_digest'], 'COVERAGE_INCONSISTENT', stage='DEDUPLICATE')
        item['artifact_ids'].update(() if row['artifact_id'] is None else (row['artifact_id'],))
        item['sbom_sha256s'].add(row['sbom_sha256'])
    return ([dict(v, artifact_ids=sorted(v['artifact_ids']), sbom_sha256s=sorted(v['sbom_sha256s']))
             for _, v in sorted(artifacts.items())], sorted(r['observation_id'] for r in data['observations']))


def _read_json(path):
    return document(read_local(path, JSON_LIMIT), limit=JSON_LIMIT)


def _entries(root):
    """Every closed coverage this root knows: registered snapshots and committed lots."""
    paths = [p for p in sorted((root / 'closed').iterdir()) if p.suffix == '.json' and NAME.fullmatch(p.stem)] if (
        root / 'closed').is_dir() else []
    paths += [p / 'lot.json' for p in sorted((root / 'lots').iterdir()) if NAME.fullmatch(p.name)] if (
        root / 'lots').is_dir() else []
    entries = [_contract('LEDGER_ENTRY_INVALID', 'DEDUPLICATE', _read_json, path) for path in paths]
    for entry in entries:
        check(entry.get('kind') in ('LOT', 'CLOSED_IMPORTED') and type(entry.get('artifacts')) is list
              and type(entry.get('observation_ids')) is list, 'LEDGER_ENTRY_INVALID', stage='DEDUPLICATE')
    return entries


def _deduplicate(entries, kind, name, artifacts, observation_ids):
    for entry in entries:
        if (entry['kind'], entry.get('name')) == (kind, name):
            continue
        where = dict(kind=entry['kind'], name=entry.get('name'), snapshot_id=entry.get('snapshot_id'))
        for artifact in artifacts:
            for known in entry['artifacts']:
                if (all(known.get(k) == artifact[k] for k in ('repository', 'run_id', 'run_attempt', 'framework'))
                        or set(known.get('artifact_ids', ())) & set(artifact['artifact_ids'])):
                    same = (known.get('index_digest'), known.get('sbom_sha256s')) == (
                        artifact['index_digest'], artifact['sbom_sha256s'])
                    raise IngestionError('ARTIFACT_ALREADY_INGESTED' if same else 'ARTIFACT_IDENTITY_CONFLICT',
                                         stage='DEDUPLICATE', key=artifact['framework'], observed=where)
        shared = set(entry['observation_ids']) & set(observation_ids)
        check(not shared, 'OBSERVATION_ALREADY_INGESTED', stage='DEDUPLICATE', observed=dict(where, count=len(shared)))


def _root(path):
    root = Path(path)
    check(not root.is_symlink() and (root.is_dir() or not root.exists()), 'ROOT_INVALID', stage='REQUEST')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


@contextmanager
def _locked(root):
    lock = root / '.intake.lock'
    try:
        os.close(os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    except FileExistsError as error:
        # A killed intake leaves this file behind: confirm none is running, then remove it explicitly.
        raise IngestionError('INTAKE_BUSY', stage='LOCK', key='.intake.lock', retryable=True) from error
    try:
        yield
    finally:
        lock.unlink()


def _result(code, lot):
    return dict(dict(diagnostic_version=1, status='SUCCESS', stage='COMMIT', code=code, lot_id=lot['name'],
                     batch_id=lot['batch_id'], snapshot_id=lot['snapshot_id'], frameworks=lot['coverage']['frameworks'],
                     observations=len(lot['observation_ids']), plan='lots/' + lot['name'] + '/plan'), **FLAGS)


def process(request, config, source, root):
    """Create lots/<lot_id> atomically, or prove an identical retry without reading any artifact."""
    request, (destination, limits), root = _request(request), _config(config), _root(root)
    lot_id, raw_request = request['lot_id'], canonical(request)
    with _locked(root):
        target = root / 'lots' / lot_id
        if target.exists() or target.is_symlink():
            return _retry(root, lot_id, raw_request, destination)
        entries = _entries(root)
        with tempfile.TemporaryDirectory(prefix='.intake-', dir=root) as temporary:
            stage = Path(temporary) / lot_id
            (stage / 'originals').mkdir(parents=True)
            selected = []
            producer_identity_verified = True
            for item in request['artifacts']:
                path = 'originals/%d.zip' % item['artifact_id']
                raw, identity_block = _acquire(source, item, request)  # The raw original, kept as acquired.
                (stage / path).write_bytes(raw)
                producer_identity_verified = producer_identity_verified and identity_block['producer_identity_verified']
                selected.append(dict(framework=item['framework'], name=item['name'], path=path,
                                     artifact_id=item['artifact_id'], expected_index_digest=item['expected_index_digest']))
            staged = _contract('STAGING_REJECTED', 'STAGE', artifact_input.stage, dict(
                schema_version=1, origin=request['origin'], image_registry=request['image_registry'],
                repository_prefix=request['repository_prefix'], artifacts=selected), stage / 'staging', base_directory=stage)
            context = _read_json(stage / 'staging/context.json')
            expected = {item['framework']: item.get('expected_platforms') for item in request['artifacts']}
            for image in context['images']:
                check(expected[image['framework']] in (None, image['platforms']), 'EXPECTED_SUBJECT_DIFFERS',
                      stage='STAGE', key=image['framework'])
            projection = _contract('STAGING_REJECTED', 'NORMALIZE', prepare, context, base_directory=stage / 'staging')
            check(projection.batch_id == staged['batch_id'], 'STAGING_BATCH_DIFFERS', stage='NORMALIZE')
            artifacts, observation_ids = _coverage(document(projection.records, limit=LIMITS['batch_bytes'] * 8))
            _deduplicate(entries, 'LOT', lot_id, artifacts, observation_ids)
            exported = _contract('NORMALIZATION_FAILED', 'NORMALIZE', export, projection, Path(temporary) / 'normalized')
            plan = prepare_snapshot(Path(exported['path']), destination, limits)
            save_plan(plan, stage / 'plan')
            (stage / 'request.json').write_bytes(raw_request)
            lot = dict(dict(protocol_version=1, kind='LOT', name=lot_id, status='LOT_COMPLETE',
                            request_sha256=sha256(raw_request), destination=asdict(destination), batch_id=plan.batch_id,
                            snapshot_id=plan.snapshot_id, plan_sha256=sha256((stage / 'plan/plan.json').read_bytes()),
                            archives=[{k: item[k] for k in ('framework', 'artifact_id', 'name', 'archive_sha256', 'archive_bytes')}
                                      for item in request['artifacts']],
                            artifacts=artifacts, observation_ids=observation_ids,
                            producer_identity_verified=producer_identity_verified,
                            corporate_acceptance='ELIGIBLE' if producer_identity_verified else 'FORBIDDEN',
                            coverage=dict(scope='SELECTED_ARTIFACTS_ONLY', complete_factory_inventory=False,
                                          frameworks=sorted(expected))), **FLAGS)
            (stage / 'lot.json').write_bytes(canonical(lot))
            (root / 'lots').mkdir(mode=0o700, exist_ok=True)
            check(not target.exists() and not target.is_symlink(), 'LOT_CONFLICT', stage='COMMIT', key=lot_id)
            os.rename(stage, target)  # The only commit point: a lot is complete or absent.
    return _result('LOT_CREATED', lot)


def _retry(root, lot_id, raw_request, destination):
    target = root / 'lots' / lot_id
    stored = _contract('LOT_INTEGRITY_FAILED', 'RETRY', read_local, target / 'request.json', JSON_LIMIT)
    lot = _contract('LOT_INTEGRITY_FAILED', 'RETRY', _read_json, target / 'lot.json')
    check(stored == raw_request and lot.get('destination') == asdict(destination), 'LOT_CONFLICT', stage='RETRY', key=lot_id)
    verify(root, lot_id)  # Identical only after a full read-back, never by name.
    return _result('LOT_ALREADY_PRESENT_IDENTICAL', lot)


def verify(root, lot_id):
    """Independent read-back of one lot from its own directory: no request, source or network."""
    check(type(lot_id) is str and NAME.fullmatch(lot_id), 'INVALID_LOT_ID', stage='VERIFY')
    target = Path(root) / 'lots' / lot_id

    def part(name, condition):
        check(condition, 'LOT_INTEGRITY_FAILED', stage='VERIFY', key=lot_id, observed={'part': name})

    try:
        part('directory', target.is_dir() and not target.is_symlink())
        part('file set', sorted(p.name for p in target.iterdir()) == LOT_FILES)
        lot, request = _read_json(target / 'lot.json'), read_local(target / 'request.json', JSON_LIMIT)
        part('lot', lot.get('kind') == 'LOT' and lot.get('name') == lot_id and lot.get('request_sha256') == sha256(request)
             and document(request, limit=JSON_LIMIT).get('lot_id') == lot_id)
        part('originals', sorted(p.name for p in (target / 'originals').iterdir())
             == sorted('%d.zip' % a['artifact_id'] for a in lot['archives']))
        for archive in lot['archives']:
            raw = read_local(target / 'originals' / ('%d.zip' % archive['artifact_id']), LIMITS['batch_bytes'])
            part('original archive', len(raw) == archive['archive_bytes'] and sha256(raw) == archive['archive_sha256'])
        staged = prepare(_read_json(target / 'staging/context.json'), base_directory=target / 'staging')
        plan = load_plan(target / 'plan')
        part('plan', (plan.batch_id, plan.snapshot_id, asdict(plan.destination)) == (
             lot['batch_id'], lot['snapshot_id'], lot['destination']) and staged.batch_id == plan.batch_id
             and sha256(read_local(target / 'plan/plan.json', JSON_LIMIT)) == lot['plan_sha256'])
        part('coverage', list(_coverage(read_completed(target / 'plan/batch'))) == [lot['artifacts'], lot['observation_ids']])
    except IngestionError as error:
        if error.code == 'LOT_INTEGRITY_FAILED':
            raise
        raise IngestionError('LOT_INTEGRITY_FAILED', stage='VERIFY', key=lot_id, observed={'part': error.code}) from error
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise IngestionError('LOT_INTEGRITY_FAILED', stage='VERIFY', key=lot_id,
                             observed={'part': type(error).__name__}) from error
    return dict(dict(diagnostic_version=1, status='SUCCESS', stage='VERIFY', code='LOT_VERIFIED', lot_id=lot_id,
                     batch_id=plan.batch_id, snapshot_id=plan.snapshot_id, observations=len(lot['observation_ids']),
                     source_reads=0), **FLAGS)


def register_closed(root, plan_directory, name):
    """Record a closed snapshot's coverage from its verified frozen plan; its bytes are never copied or changed."""
    check(type(name) is str and NAME.fullmatch(name), 'INVALID_NAME', stage='REQUEST')
    plan = load_plan(plan_directory)
    artifacts, observation_ids = _coverage(read_completed(Path(plan_directory) / 'batch'))
    raw = canonical(dict(protocol_version=1, kind='CLOSED_IMPORTED', name=name, batch_id=plan.batch_id,
                         snapshot_id=plan.snapshot_id, destination=asdict(plan.destination),
                         plan_sha256=sha256(read_local(Path(plan_directory) / 'plan.json', JSON_LIMIT)),
                         artifacts=artifacts, observation_ids=observation_ids, snapshot_bytes_copied=False,
                         publication_authority=False))
    root = _root(root)
    with _locked(root):
        path = root / 'closed' / (name + '.json')
        if path.exists() or path.is_symlink():
            stored = _contract('CLOSED_ENTRY_CONFLICT', 'COMMIT', read_local, path, JSON_LIMIT)
            check(stored == raw, 'CLOSED_ENTRY_CONFLICT', stage='COMMIT', key=name)
            code = 'CLOSED_ALREADY_PRESENT_IDENTICAL'
        else:
            _deduplicate(_entries(root), 'CLOSED_IMPORTED', name, artifacts, observation_ids)
            path.parent.mkdir(mode=0o700, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.closed-', delete=False) as stream:
                stream.write(raw)
            os.rename(stream.name, path)
            code = 'CLOSED_REGISTERED'
    return dict(diagnostic_version=1, status='SUCCESS', stage='COMMIT', code=code, name=name, batch_id=plan.batch_id,
                snapshot_id=plan.snapshot_id, observations=len(observation_ids), cloud_calls=0, publication_authority=False)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise IngestionError('INTAKE_ARGUMENTS_INVALID', stage='ARGUMENTS')


def main(argv=None):
    parser = _Parser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name, options in (('process', ('request', 'config', 'artifacts', 'root')), ('verify', ('root', 'lot')),
                          ('register-closed', ('root', 'plan', 'name'))):
        command = commands.add_parser(name)
        for option in options + ('report',):
            command.add_argument('--' + option, required=True, type=str if option in ('lot', 'name') else Path)
    report, protected = None, []
    try:
        args = parser.parse_args(argv)
        report = args.report
        protected = [getattr(args, k) for k in ('root', 'artifacts', 'request', 'config', 'plan') if hasattr(args, k)]
        sink = _report_destination(report, protected)
        if args.command == 'process':
            request = _contract('INVALID_REQUEST', 'REQUEST', _read_json, args.request)
            config = _contract('INVALID_CONFIGURATION', 'REQUEST', _read_json, args.config)
            result = process(request, config, DirectoryArtifacts(args.artifacts), args.root)
        elif args.command == 'verify':
            result = verify(args.root, args.lot)
        else:
            result = register_closed(args.root, args.plan, args.name)
        result = _write_report(result, sink)
    except Exception as error:
        failure = error if isinstance(error, IngestionError) else IngestionError(
            'INTAKE_ERROR', stage='INTAKE', observed={'exception': type(error).__name__})
        result = failure.diagnostic()
        if report is not None:
            try:
                result = _write_report(result, _report_destination(report, protected))
            except Exception:
                pass  # The JSON below still carries the failure; no permitted sink exists.
    print(canonical(result).decode())
    return 0 if result.get('status') == 'SUCCESS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
