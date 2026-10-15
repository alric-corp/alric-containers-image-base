"""Offline SPDX analytics CLI. Local projections confer no release authority."""
import argparse
from dataclasses import dataclass
import errno
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

from scripts.pipeline.analytics import parquet
from scripts.pipeline.analytics.spdx import (
    AnalyticsError, DOCUMENTS, LIMITS, NORMALIZER_VERSION, SCHEMA_VERSION, canonical, checksum,
    digest, document, fields, integer, packages, read_local, require, sha256, text, timestamp,
)
from scripts.pipeline.artifacts.image_reference import require_digest_reference
from scripts.pipeline.artifacts.oci_artifact import sboms
from scripts.pipeline.release.verify_publication import verify_publication


@dataclass(frozen=True)
class Projection:
    records: bytes
    materials: tuple

    def __post_init__(self):
        require(type(self.records) is bytes and type(self.materials) is tuple, 'freeze records and material bytes')
        data = document(self.records, limit=LIMITS['batch_bytes'] * 8)
        fields(data, ('schema_version', 'normalizer_version', 'observations', 'packages'), label='projection')
        require(type(data['schema_version']) is int and data['schema_version'] == SCHEMA_VERSION
                and data['normalizer_version'] == NORMALIZER_VERSION and canonical(data) == self.records,
                'unsupported/noncanonical projection')
        for table, keys in (('observations', ('observation_id',)), ('packages', ('sbom_sha256', 'package_spdx_id'))):
            rows = data[table]
            require(type(rows) is list and rows, 'nonempty projection tables required')
            columns = {f['name'] for f in parquet.definition()['tables'][table]}
            require(all(type(r) is dict and set(r) == columns for r in rows), 'projection columns differ')
            identities = [tuple(r[k] for k in keys) for r in rows]
            require(identities == sorted(set(identities)), 'duplicate/unsorted projection identities')
            require(all(type(r['schema_version']) is int and r['schema_version'] == SCHEMA_VERSION
                        and r['normalizer_version'] == NORMALIZER_VERSION for r in rows), 'projection version differs')
        for row in data['observations']:
            require(row['observation_id'] == sha256(canonical({k:v for k,v in row.items() if k != 'observation_id'})),
                    'observation identity differs')
            require(row['cryptographic_authenticity'] == 'NOT_REVALIDATED' and row['publication_authority'] is False,
                    'analytics cannot grant authentication/publication authority')
        paths = []
        for path, raw in self.materials:
            match = re.fullmatch(r'raw/(spdx|records)/sha256=([0-9a-f]{64})/(document\.spdx\.json|record\.json)', path)
            require(match is not None and type(raw) is bytes and sha256(raw) == match[2], 'invalid raw material path/hash')
            require((match[1] == 'spdx') == (match[3] == 'document.spdx.json'), 'raw material kind differs')
            paths.append(path)
        require(paths == sorted(set(paths)), 'duplicate/unsorted raw materials')
        required = {r['raw_spdx_path'] for r in data['observations']}
        for row in data['observations']:
            require(row['raw_spdx_path'] == 'raw/spdx/sha256=' + digest(row['sbom_sha256']) + '/document.spdx.json',
                    'observation raw path differs')
            for column in ('validation_record_sha256', 'publication_record_sha256', 'published_index_sha256',
                           'candidate_identity_sha256'):
                if row[column] is not None:
                    required.add('raw/records/sha256=' + digest(row[column]) + '/record.json')
        require(set(paths) == required, 'projection raw inventory differs')
        require({r['sbom_sha256'] for r in data['packages']} == {r['sbom_sha256'] for r in data['observations']},
                'package/document inventory differs')

    @property
    def batch_id(self):
        return sha256(self.records)


def _origin(value):
    fields(value, ('repository', 'run_id', 'run_attempt', 'source_sha', 'event', 'ref'),
           ('source_timestamp', 'source_timestamp_origin'), 'origin')
    require(type(value['repository']) is str and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value['repository']),
            'invalid repository')
    integer(value['run_id'], 'run_id')
    integer(value['run_attempt'], 'run_attempt')
    digest(value['source_sha'], 'source SHA', git=True)
    event, ref = value['event'], value['ref']
    require(type(ref) is str and not any(c.isspace() for c in ref) and '..' not in ref, 'invalid ref')
    if event == 'pull_request':
        require(re.fullmatch(r'refs/pull/[1-9][0-9]*/(?:head|merge)', ref), 'PR event requires its original PR ref')
    else:
        require(event in ('push', 'schedule', 'workflow_dispatch') and re.fullmatch(r'refs/(heads|tags)/[^/].*', ref),
                'unsupported/inconsistent event/ref')
    supplied_time = value.get('source_timestamp')
    time_origin = value.get('source_timestamp_origin')
    require((supplied_time is None) == (time_origin is None), 'source timestamp requires an explicit origin')
    if supplied_time is not None:
        timestamp(supplied_time, 'source_timestamp')
        require(text(time_origin, 'source_timestamp_origin') != '', 'empty timestamp origin')
    return dict(value, source_timestamp=supplied_time, source_timestamp_origin=time_origin)


def _external_record(value, acquire, materials):
    fields(value, ('path', 'reference'), label='external record')
    reference = text(value['reference'], 'external record reference')
    require(reference != '', 'external record reference required')
    raw = acquire(value['path'])
    path = 'raw/records/sha256=' + sha256(raw) + '/record.json'
    materials[path] = raw
    return document(raw), sha256(raw), reference


def prepare(context, *, base_directory=Path('.')):
    """All inputs are bounded/read once; no output is visible during validation."""
    fields(context, ('schema_version', 'origin', 'images'), label='analytics input')
    require(type(context['schema_version']) is int and context['schema_version'] == 1, 'unsupported input schema')
    origin = _origin(context['origin'])
    images = context['images']
    require(type(images) is list and 0 < len(images) <= LIMITS['documents'] // 3, 'image count/type limit')
    materials, observations, package_rows, frameworks = {}, {}, {}, set()
    total_bytes, total_packages = 0, 0

    def acquire(path):
        nonlocal total_bytes
        require(type(path) is str and path != '', 'local input path required')
        raw = read_local(Path(base_directory) / path, LIMITS['document_bytes'])
        total_bytes += len(raw)
        require(total_bytes <= LIMITS['batch_bytes'], 'batch byte limit exceeded')
        return raw

    for image in images:
        fields(image, ('framework', 'image_repository', 'image_index_digest', 'platforms', 'documents'),
               ('validation', 'publication', 'candidate_identity', 'hosted_verification'), 'image context')
        framework = image['framework']
        require(type(framework) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]*', framework), 'invalid framework')
        require(framework not in frameworks, 'duplicate framework in batch')
        frameworks.add(framework)
        index = digest(image['image_index_digest'], 'image index', oci=True)
        image_repository = text(image['image_repository'], 'image repository')
        require_digest_reference(image_repository + '@' + index)
        platforms = image['platforms']
        fields(platforms, ('linux/amd64', 'linux/arm64'), label='platforms')
        for subject in platforms.values():
            digest(subject, 'platform subject', oci=True)
        require(len({index, *platforms.values()}) == 3, 'index/platform subjects must be distinct')
        inputs = image['documents']
        require(type(inputs) is list and len(inputs) == 3, framework + ': three subject-specific SPDXs required')
        loaded, mapped = {}, {}
        for item in inputs:
            fields(item, ('path', 'sbom_scope', 'document_platform'), ('sha256', 'artifact_id', 'source_path'), 'SPDX input')
            key = 'index' if item['sbom_scope'] == 'index' else item['document_platform']
            require(key in DOCUMENTS and key not in loaded, framework + ': missing/duplicate/unexpected document scope')
            name, platform = DOCUMENTS[key]
            require(item['sbom_scope'] == ('index' if platform is None else 'platform')
                    and item['document_platform'] == platform, 'inconsistent document platform/scope')
            if item.get('artifact_id') is not None:
                integer(item['artifact_id'], 'artifact_id')
            source_path = item.get('source_path')
            if source_path is not None:
                text(source_path, 'source_path')
                require(source_path and not source_path.startswith('/') and '\\' not in source_path
                        and all(p not in ('', '.', '..') for p in source_path.split('/')), 'invalid original source path')
            raw = acquire(item['path'])
            if 'sha256' in item:
                require(sha256(raw) == digest(item['sha256'], 'external SPDX SHA256'), framework + '/' + name + ': SPDX hash mismatch')
            subject = index if platform is None else platforms[platform]
            try:
                mapped[key] = packages(raw, subject)
            except AnalyticsError as error:
                raise AnalyticsError(framework + '/' + name + ': ' + str(error)) from error
            loaded[key] = (item, raw, subject)
        require(set(loaded) == set(DOCUMENTS), 'complete index/amd64/arm64 document set required')
        # Reuse the unchanged Factory SBOM contract without loading OCI layers.
        with tempfile.TemporaryDirectory(prefix='sbom-analytics-subject-') as temporary:
            layout = Path(temporary)
            (layout / 'sbom').mkdir()
            for key, (_, raw, _) in loaded.items():
                (layout / 'sbom' / DOCUMENTS[key][0]).write_bytes(raw)
            actual_sboms = sboms(layout, index, platforms)
        checks = dict(validation_record_check='NOT_PROVIDED', validation_record_sha256=None,
                      validation_record_reference=None, publication_record_check='NOT_PROVIDED',
                      publication_record_sha256=None, publication_record_reference=None,
                      published_index_sha256=None, candidate_identity_check='NOT_PROVIDED',
                      candidate_identity_sha256=None, candidate_identity_reference=None)
        if 'validation' in image:
            value, hashed, reference = _external_record(image['validation'], acquire, materials)
            registered = value.get('sboms')
            require(type(registered) is list and len(registered) == 3
                    and all(type(r) is dict and type(r.get('path')) is str for r in registered)
                    and len({r['path'] for r in registered}) == 3, 'invalid validation SPDX inventory')
            require(value.get('digest') == index and value.get('platforms') == platforms
                    and sorted(registered, key=lambda r: r['path']) == sorted(actual_sboms, key=lambda r: r['path']),
                    framework + ': validation record binding differs')
            checks.update(validation_record_check='MATCHED', validation_record_sha256=hashed,
                          validation_record_reference=reference)
        if 'publication' in image:
            publication = image['publication']
            fields(publication, ('path', 'remote_index_path', 'reference'), label='publication input')
            value, hashed, reference = _external_record(
                {k: publication[k] for k in ('path', 'reference')}, acquire, materials)
            remote = acquire(publication['remote_index_path'])
            document(remote)  # Strict JSON parsing before the unchanged binding helper.
            verified = verify_publication(dict(digest=index, platforms=platforms), value.get('copied_digest'),
                                          remote, image_repository + '@' + index)
            require(verified == value, framework + ': publication record binding differs')
            remote_hash = sha256(remote)
            materials['raw/records/sha256=' + remote_hash + '/record.json'] = remote
            checks.update(publication_record_check='MATCHED', publication_record_sha256=hashed,
                          publication_record_reference=reference, published_index_sha256=remote_hash)
        if 'candidate_identity' in image:
            value, hashed, reference = _external_record(image['candidate_identity'], acquire, materials)
            require(all(value.get(k) == v for k, v in dict(run_id=origin['run_id'], attempt=origin['run_attempt'],
                    source_sha=origin['source_sha'], digest=index).items()), framework + ': candidate identity differs')
            require(type(value.get('run_id')) is int and type(value.get('attempt')) is int,
                    'candidate identity IDs must be integers')
            checks.update(candidate_identity_check='MATCHED', candidate_identity_sha256=hashed,
                          candidate_identity_reference=reference)
        hosted = image.get('hosted_verification', dict(status='NOT_PROVIDED', reference=None))
        fields(hosted, ('status', 'reference'), label='reported hosted verification')
        require(hosted['status'] in ('NOT_PROVIDED', 'REPORTED_SUCCESS', 'REPORTED_FAILURE'), 'invalid hosted report status')
        require((hosted['status'] == 'NOT_PROVIDED') == (hosted['reference'] is None), 'hosted report reference differs')
        text(hosted['reference'], 'hosted verification reference', optional=True)
        for key in sorted(loaded):
            item, raw, subject = loaded[key]
            value, rows, created, relationships = mapped[key]
            total_packages += len(rows)
            require(total_packages <= LIMITS['batch_packages'], 'batch package count limit')
            raw_path = 'raw/spdx/sha256=' + sha256(raw) + '/document.spdx.json'
            materials[raw_path] = raw
            for row in rows:
                pk = (row['sbom_sha256'], row['package_spdx_id'])
                require(pk not in package_rows or package_rows[pk] == row, 'conflicting package records')
                package_rows[pk] = row
            observation = dict(schema_version=SCHEMA_VERSION, normalizer_version=NORMALIZER_VERSION,
                sbom_sha256=sha256(raw), predicate_digest=checksum(value), **origin,
                framework=framework, image_repository=image_repository, image_index_digest=index,
                subject_digest=subject, sbom_scope=item['sbom_scope'], document_platform=item['document_platform'],
                document_namespace=value['documentNamespace'], spdx_version=value['spdxVersion'],
                spdx_created=created, package_count=len(rows), relationship_count=relationships,
                artifact_id=item.get('artifact_id'), source_path=item.get('source_path'), raw_spdx_path=raw_path,
                integrity_check='MATCHED_EXTERNAL_SHA256' if 'sha256' in item else 'SHA256_COMPUTED',
                subject_check='MATCHED_EXPECTED_OCI_SHA256',
                hosted_verification_status=hosted['status'], hosted_verification_reference=hosted['reference'],
                cryptographic_authenticity='NOT_REVALIDATED', publication_authority=False, **checks)
            observation['observation_id'] = sha256(canonical(observation))
            observations[observation['observation_id']] = observation
    records = canonical(dict(schema_version=SCHEMA_VERSION, normalizer_version=NORMALIZER_VERSION,
        observations=sorted(observations.values(), key=lambda r: r['observation_id']),
        packages=sorted(package_rows.values(), key=lambda r: (r['sbom_sha256'], r['package_spdx_id']))))
    return Projection(records, tuple(sorted(materials.items())))


def _inventory(directory):
    result = []
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(), 'symlink in completed batch')
        require(path.is_file() or path.is_dir(), 'special file in completed batch')
        if path.is_file() and path != directory / 'complete.json':
            raw = read_local(path, LIMITS['batch_bytes'])
            result.append(dict(path=path.relative_to(directory).as_posix(), size=len(raw), sha256=sha256(raw)))
    return result


def verify_batch(directory, projection):
    directory = Path(directory)
    require(not directory.is_symlink() and directory.is_dir(), 'invalid batch destination')
    marker = document(read_local(directory / 'complete.json', LIMITS['context_bytes']))
    fields(marker, ('schema_version', 'status', 'batch_id', 'records_sha256', 'files'), label='batch marker')
    require(type(marker['schema_version']) is int and marker['schema_version'] == SCHEMA_VERSION
            and marker['status'] == 'NORMALIZATION_COMPLETE'
            and marker['batch_id'] == projection.batch_id and marker['records_sha256'] == sha256(projection.records),
            'conflicting/incomplete batch marker')
    inventory = _inventory(directory)
    expected_paths = {path for path, _ in projection.materials} | {
        'reports/records.json', 'reports/normalization.json',
        'analytics/sbom_observations/part-00000.parquet', 'analytics/sbom_packages/part-00000.parquet'}
    require(marker['files'] == inventory and {r['path'] for r in inventory} == expected_paths,
            'completed batch inventory differs')
    require((directory / 'reports/records.json').read_bytes() == projection.records, 'normalized record conflict')
    for path, raw in projection.materials:
        require((directory / path).read_bytes() == raw, 'original material byte conflict: ' + path)
    data = document(projection.records, limit=LIMITS['batch_bytes'] * 8)
    for table in ('observations', 'packages'):
        require(parquet.read(directory / 'analytics' / ('sbom_' + table) / 'part-00000.parquet', table) == data[table],
                'stored Parquet records differ')
    return marker


def read_completed(directory):
    """Inspect local completion/integrity only; this does not authenticate origin."""
    directory = Path(directory)
    records = read_local(directory / 'reports/records.json', LIMITS['batch_bytes'] * 8)
    materials = tuple((path.relative_to(directory).as_posix(), read_local(path, LIMITS['document_bytes']))
                      for path in sorted((directory / 'raw').rglob('*')) if path.is_file())
    projection = Projection(records, materials)
    verify_batch(directory, projection)
    return document(records, limit=LIMITS['batch_bytes'] * 8)


def export(projection, output):
    """Publish a complete local batch atomically in a private caller-owned root.

    This local completion marker is not a signature, release or custody record.
    """
    require(isinstance(projection, Projection), 'prepared projection required')
    output = Path(output)
    require(output.drive or re.match(r'[A-Za-z][A-Za-z0-9+.-]*:', str(output)) is None, 'only local output is supported')
    require(not output.is_symlink(), 'symlink output root refused')
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    batches = output / 'batches'
    require(not batches.is_symlink(), 'symlink batch parent refused')
    batches.mkdir(exist_ok=True)
    target = batches / projection.batch_id
    lock = output / ('.' + projection.batch_id + '.lock')
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise AnalyticsError('batch writer busy; retry the same frozen projection') from error
    os.close(fd)
    stage = None
    try:
        if target.exists() or target.is_symlink():
            verify_batch(target, projection)
            return dict(status='ALREADY_PRESENT_IDENTICAL', batch_id=projection.batch_id, path=str(target))
        stage = Path(tempfile.mkdtemp(prefix='.sbom-analytics-', dir=output))
        for path, raw in projection.materials:
            destination = stage / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        data = document(projection.records, limit=LIMITS['batch_bytes'] * 8)
        versions = set()
        for table in ('observations', 'packages'):
            directory = stage / 'analytics' / ('sbom_' + table)
            directory.mkdir(parents=True)
            versions.add(parquet.write(directory / 'part-00000.parquet', table, data[table]))
        reports = stage / 'reports'
        reports.mkdir()
        (reports / 'records.json').write_bytes(projection.records)
        (reports / 'normalization.json').write_bytes(canonical(dict(schema_version=SCHEMA_VERSION,
            normalizer_version=NORMALIZER_VERSION, batch_id=projection.batch_id,
            observations=len(data['observations']), packages=len(data['packages']),
            parquet_library='pyarrow', parquet_versions=sorted(versions),
            cryptographic_authenticity='NOT_REVALIDATED', publication_authority=False)))
        marker = canonical(dict(schema_version=SCHEMA_VERSION, status='NORMALIZATION_COMPLETE',
            batch_id=projection.batch_id, records_sha256=sha256(projection.records), files=_inventory(stage)))
        (stage / 'complete.json').write_bytes(marker)
        verify_batch(stage, projection)
        os.rename(stage, target)
        stage = None
        return dict(status='CREATED', batch_id=projection.batch_id, path=str(target))
    finally:
        if stage is not None:
            shutil.rmtree(stage)
        lock.unlink()


# CLI diagnostic only: the core's own message formats select a stable code;
# normalization rules and texts are unchanged. Anchors keep user paths inside
# a message from selecting a rule. First match wins.
FAILURES = tuple((re.compile(pattern), code, category) for pattern, code, category in (
    (r'^batch writer busy', 'OUTPUT_BUSY', 'CONCURRENCY'),
    (r'^only local output is supported$', 'OUTPUT_NOT_LOCAL', 'UNSAFE_PATH'),
    (r'^symlink (?:output root|batch parent) refused$|^symlink in completed batch$', 'SYMLINK_REFUSED', 'UNSAFE_PATH'),
    (r': regular local file required$|^special file in completed batch$', 'NOT_A_REGULAR_FILE', 'UNSAFE_PATH'),
    (r'^invalid original source path$', 'UNSAFE_SOURCE_PATH', 'UNSAFE_PATH'),
    (r': SPDX hash mismatch$', 'SPDX_HASH_MISMATCH', 'INTEGRITY'),
    (r': subject checksum differs from expected OCI identity$|: subject SHA256 checksum required$'
     r'|^sbom-[a-z0-9_]+\.spdx\.json does not describe its OCI subject ', 'SUBJECT_MISMATCH', 'INTEGRITY'),
    (r': (?:validation|publication) record binding differs$|: candidate identity differs$'
     r'|^published |^duplicate platform in published index$', 'RECORD_BINDING_MISMATCH', 'INTEGRITY'),
    (r': invalid digest$|^imagem deve ser referenciada por digest', 'INVALID_DIGEST', 'INTEGRITY'),
    (r'byte limit exceeded$|^JSON byte/type limit$|count(?:/type)? limit$', 'LIMIT_EXCEEDED', 'LIMITS'),
    (r'(?:^|: )(?:invalid JSON: |duplicate JSON key: |non-finite JSON |JSON depth limit$'
     r'|JSON document must be an object$)', 'INVALID_JSON', 'INPUT_JSON'),
    (r': missing/unknown fields$', 'FIELDS_INVALID', 'CONTRACT'),
))
STAGE_FAILURES = dict(ARGUMENTS=('ARGUMENTS_INVALID', 'ARGUMENTS'), READ_CONTEXT=('INPUT_UNREADABLE', 'INPUT_FILE'),
                      PARSE_CONTEXT=('CONTEXT_INVALID', 'CONTRACT'), VALIDATE=('CONTEXT_INVALID', 'CONTRACT'),
                      EXPORT=('OUTPUT_CONFLICT', 'OUTPUT'))
# An existing batch that fails verification is an output conflict, whatever its cause.
EXPORT_CODES = ('OUTPUT_BUSY', 'OUTPUT_NOT_LOCAL', 'SYMLINK_REFUSED', 'LIMIT_EXCEEDED')
SPDX_DOCUMENT = re.compile(r'^[^/: ]+/sbom-[a-z0-9_]+\.spdx\.json: ')


def _diagnostic(status, stage, code, category=None, message=None, **values):
    return dict(dict(diagnostic_version=1, tool='sbom-analytics-normalize', status=status, stage=stage, code=code,
                     category=category, message=message, context={}, batch_id=None, complete=False, retryable=False,
                     exit_code=0 if status == 'SUCCESS' else 1, cryptographic_authenticity='NOT_REVALIDATED',
                     publication_authority=False), **values)


def _failure(error, stage, redactions):
    """Code, stage and a bounded message; never a traceback or an SDK/OS payload."""
    context = dict(exception=type(error).__name__)
    if isinstance(error, ImportError):
        code, category, message = 'DEPENDENCY_UNAVAILABLE', 'DEPENDENCY', 'required module unavailable: ' + str(error.name)
    elif isinstance(error, OSError):
        code, category = 'FILESYSTEM_ERROR', 'FILESYSTEM'
        context['errno'] = errno.errorcode.get(error.errno) if type(error.errno) is int else None
        message = error.strerror or 'filesystem operation failed'
    elif isinstance(error, (ValueError, KeyError, TypeError)):
        message = str(error)
        for path, label in sorted(redactions, key=lambda item: -len(item[0])):
            message = message.replace(path, label)
        message = ''.join(c if ' ' <= c <= '~' else '?' for c in ' '.join(message.split()))[:300]
        code, category = next(((c, k) for pattern, c, k in FAILURES if pattern.search(message)), (None, None))
        if code is None or (stage == 'EXPORT' and code not in EXPORT_CODES):
            code, category = STAGE_FAILURES[stage]
        if stage == 'VALIDATE' and category == 'CONTRACT' and SPDX_DOCUMENT.match(message):
            code, category = 'SPDX_INCOMPATIBLE', 'SPDX_CONTRACT'
    else:
        code, category, message = 'NORMALIZER_INTERNAL_ERROR', 'INTERNAL', 'internal error (' + type(error).__name__ + ')'
    return _diagnostic('ERROR', stage, code, category, message, context=context, retryable=code == 'OUTPUT_BUSY')


def _report_sink(value, protected):
    """Explicit local file outside the context file and the output root."""
    require(type(value) is str and value and '://' not in value, 'report must be a local file')
    path = Path(value)
    require(not path.is_symlink() and not path.is_dir(), 'report must not be a symlink or directory')
    resolved = path.resolve()
    require(all(resolved != root and root not in resolved.parents for root in protected),
            'report must be outside the context file and the output root')
    return path


def _write_report(value, protected, diagnostic):
    path = _report_sink(value, protected)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.normalize-report-', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(canonical(diagnostic) + b'\n')
    try:
        _report_sink(value, protected)  # The sink may have changed while the batch was written.
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _option(argv, name):
    values = [argv[i + 1] for i, value in enumerate(argv[:-1]) if value == name]
    values += [value.split('=', 1)[1] for value in argv if value.startswith(name + '=')]
    return values[0] if len(values) == 1 else None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path, help='local v1 context JSON; paths relative to this file')
    parser.add_argument('--output', required=True, help='private local output root (never an S3 URI)')
    parser.add_argument('--report', help='optional local JSON diagnostic, written on success and failure; '
                                         'never the context file or inside --output')
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit:
        report = _option(argv, '--report')
        if exit.code and report is not None:  # Usage errors keep argparse's exit status.
            try:
                protected = [Path(p).resolve() for p in (_option(argv, '--input'), _option(argv, '--output')) if p]
                _write_report(report, protected, _diagnostic('ERROR', 'ARGUMENTS', 'ARGUMENTS_INVALID', 'ARGUMENTS',
                                                             'invalid command-line arguments', exit_code=exit.code))
            except (OSError, ValueError, RuntimeError):
                print('SBOM analytics report not written', file=sys.stderr)
        raise
    try:
        protected = [args.input.resolve(), Path(args.output).resolve()]
        if args.report is not None:
            _report_sink(args.report, protected)  # Before any work: a refused sink never follows a batch.
    except (OSError, ValueError, RuntimeError) as error:
        print('SBOM analytics failed: ' + str(error), file=sys.stderr)
        return 1
    stage, redactions = 'ARGUMENTS', [(str(protected[0].parent), '<context-directory>'), (str(protected[1]), '<output>')]
    try:
        require('://' not in str(args.output), 'only local output is supported')
        stage = 'READ_CONTEXT'
        raw = read_local(args.input, LIMITS['context_bytes'])
        stage = 'PARSE_CONTEXT'
        context = document(raw, limit=LIMITS['context_bytes'])
        stage = 'VALIDATE'
        projection = prepare(context, base_directory=args.input.resolve().parent)
        stage = 'EXPORT'
        result = export(projection, args.output)
    except Exception as error:  # Known types keep their original text; others never print a traceback.
        known = isinstance(error, (OSError, ValueError, KeyError, TypeError, ImportError))
        print('SBOM analytics failed: ' + (str(error) if known else 'internal error (' + type(error).__name__ + ')'),
              file=sys.stderr)
        diagnostic = _failure(error, stage, redactions)
        if args.report is not None:
            try:
                _write_report(args.report, protected, diagnostic)
            except (OSError, ValueError, RuntimeError):
                print('SBOM analytics report not written', file=sys.stderr)
        return 1
    if args.report is not None:
        try:
            _write_report(args.report, protected, _diagnostic(
                'SUCCESS', 'EXPORT', 'BATCH_' + result['status'], batch_id=result['batch_id'], complete=True))
        except (OSError, ValueError, RuntimeError):
            print('SBOM analytics report not written', file=sys.stderr)
            return 1
    print(canonical(result).decode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
