"""Closed analytics snapshots. Original normalizer IDs and bytes stay intact."""
from dataclasses import asdict, dataclass
import os
from pathlib import Path
import tempfile

from scripts.pipeline.analytics.ingestion_types import (
    Destination, FIXED_FILES, IngestionError, Limits, SnapshotPlan, check, hash_id, material_path, object_bytes,
)
from scripts.pipeline.analytics.normalize import read_completed
from scripts.pipeline.analytics.spdx import canonical, document, fields, read_local, sha256

JSON_LIMIT = 4 * 1024 * 1024
VERIFICATION = dict(local_batch='VERIFIED', stored_bytes='READBACK_MATCHED',
                    object_inventory='EXACT_AT_VERIFICATION', latest_versions='MATCHED_AT_VERIFICATION',
                    cryptographic_authenticity='NOT_REVALIDATED', publication_authority=False)


def _tree(directory, expected, limits):
    check(directory.is_dir() and not directory.is_symlink(), 'INVALID_BATCH_DIRECTORY', stage='VALIDATE_BATCH')
    directories = {p.as_posix() for name in expected for p in Path(name).parents if p != Path('.')}
    pending, found, visits = [directory], set(), 0
    while pending:
        parent = pending.pop()
        with os.scandir(parent) as entries:
            for entry in entries:
                visits += 1
                check(visits <= limits.objects * 8, 'LOCAL_TREE_LIMIT', stage='VALIDATE_BATCH')
                name = Path(entry.path).relative_to(directory).as_posix()
                check(not entry.is_symlink(), 'LOCAL_SYMLINK', stage='VALIDATE_BATCH')
                if entry.is_dir(follow_symlinks=False):
                    check(name in directories, 'UNEXPECTED_DIRECTORY', stage='VALIDATE_BATCH')
                    pending.append(Path(entry.path))
                else:
                    check(entry.is_file(follow_symlinks=False) and name in expected,
                          'UNEXPECTED_OR_SPECIAL_FILE', stage='VALIDATE_BATCH')
                    found.add(name)
    check(found == expected, 'BATCH_FILE_SET_DIFFERS', stage='VALIDATE_BATCH',
          expected=len(expected), observed=len(found))


def _validate_frozen(plan, *, parquet_budget=None):
    """Validate a private copy of exactly the frozen bytes, before transport."""
    try:
        with tempfile.TemporaryDirectory(prefix='analytics-frozen-') as temporary:
            directory = Path(temporary)
            for item in plan.objects:
                path = directory / item.path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(item.body)
            # Bound Parquet expansion before the existing reader materializes tables.
            import pyarrow.parquet as pq
            expanded = 0
            budget = min(plan.limits.parquet_expanded_bytes, parquet_budget) if parquet_budget is not None else plan.limits.parquet_expanded_bytes
            for table, max_rows in (('observations', 512), ('packages', 250000)):
                metadata = pq.ParquetFile(directory / 'analytics' / ('sbom_' + table) / 'part-00000.parquet',
                    thrift_string_size_limit=JSON_LIMIT, thrift_container_size_limit=1000000).metadata
                check(0 < metadata.num_rows <= max_rows and metadata.num_row_groups <= 4096,
                      'PARQUET_ROW_LIMIT', stage='VALIDATE_BATCH')
                for i in range(metadata.num_row_groups):
                    group = metadata.row_group(i)
                    for j in range(group.num_columns):
                        size = group.column(j).total_uncompressed_size
                        check(size >= 0, 'PARQUET_SIZE_INVALID', stage='VALIDATE_BATCH')
                        expanded += size
                        check(expanded <= budget, 'PARQUET_EXPANSION_LIMIT', stage='VALIDATE_BATCH')
            data = read_completed(directory)
            report = document((directory / 'reports/normalization.json').read_bytes(), limit=JSON_LIMIT)
            fields(report, ('schema_version', 'normalizer_version', 'batch_id', 'observations', 'packages',
                            'parquet_library', 'parquet_versions', 'cryptographic_authenticity', 'publication_authority'))
            check(type(report['schema_version']) is int and report['schema_version'] == 1
                  and report['normalizer_version'] == '1.0.0' and report['batch_id'] == plan.batch_id,
                  'NORMALIZATION_REPORT_VERSION_DIFFERS', stage='VALIDATE_BATCH')
            check(type(report['observations']) is int and report['observations'] == len(data['observations'])
                  and type(report['packages']) is int and report['packages'] == len(data['packages']),
                  'NORMALIZATION_REPORT_COUNTS_DIFFER', stage='VALIDATE_BATCH')
            check(report['parquet_library'] == 'pyarrow' and type(report['parquet_versions']) is list
                  and report['parquet_versions'] and all(type(v) is str and 0 < len(v) <= 64 for v in report['parquet_versions'])
                  and report['cryptographic_authenticity'] == 'NOT_REVALIDATED' and report['publication_authority'] is False,
                  'NORMALIZATION_REPORT_INVALID', stage='VALIDATE_BATCH')
            check(sha256((directory / 'reports/records.json').read_bytes()) == plan.batch_id,
                  'BATCH_ID_DIFFERS', stage='VALIDATE_BATCH')
            return data
    except IngestionError:
        raise
    except Exception as error:
        # Never echo external JSON, paths, SDK messages or original SPDX bytes.
        raise IngestionError('BATCH_INVALID', stage='VALIDATE_BATCH') from error


def prepare_snapshot(batch, destination, limits=Limits()):
    directory = Path(batch)
    batch_id, plan = None, None
    try:
        marker_bytes = read_local(directory / 'complete.json', JSON_LIMIT)
        marker = document(marker_bytes, limit=JSON_LIMIT)
        fields(marker, ('schema_version', 'status', 'batch_id', 'records_sha256', 'files'))
        check(type(marker['schema_version']) is int and marker['schema_version'] == 1
              and marker['status'] == 'NORMALIZATION_COMPLETE', 'UNSUPPORTED_BATCH', stage='VALIDATE_BATCH')
        batch_id = hash_id(marker['batch_id'])
        check(type(marker['files']) is list and 0 < len(marker['files']) < limits.objects, 'BATCH_INVENTORY_LIMIT')
        entries, total = {}, len(marker_bytes)
        for record in marker['files']:
            fields(record, ('path', 'size', 'sha256'))
            path = material_path(record['path'])
            check(path != 'complete.json' and path not in entries, 'DUPLICATE_BATCH_PATH')
            hash_id(record['sha256'])
            check(type(record['size']) is int and 0 <= record['size'] <= limits.object_bytes, 'BATCH_SIZE_LIMIT')
            total += record['size']
            check(total <= limits.snapshot_bytes, 'BATCH_SIZE_LIMIT')
            entries[path] = record
        expected = set(entries) | {'complete.json'}
        check(FIXED_FILES <= expected, 'BATCH_INCOMPLETE')
        _tree(directory, expected, limits)
        captured = {'complete.json': marker_bytes}
        for name, entry in entries.items():
            raw = read_local(directory / name, limits.object_bytes)
            check(len(raw) == entry['size'] and sha256(raw) == entry['sha256'], 'BATCH_BYTES_DIFFER',
                  stage='VALIDATE_BATCH', key=name, expected={'size':entry['size'], 'sha256':entry['sha256']},
                  observed={'size':len(raw), 'sha256':sha256(raw)})
            captured[name] = raw
        plan = SnapshotPlan(destination, batch_id,
                            tuple(object_bytes(p, b, batch_id) for p,b in sorted(captured.items())), limits)
        _validate_frozen(plan)
        return plan
    except IngestionError as error:
        error.batch_id = batch_id
        error.snapshot_id = plan.snapshot_id if plan else None
        raise
    except Exception as error:
        raise IngestionError('BATCH_INVALID', stage='VALIDATE_BATCH', batch_id=batch_id,
                             snapshot_id=plan.snapshot_id if plan else None) from error


def plan_document(plan):
    return dict(protocol_version=1, snapshot_id=plan.snapshot_id, identity=plan.identity(), limits=asdict(plan.limits))


def _materialize(plan, directory):
    for item in plan.objects:
        path = directory / item.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(item.body)


def save_plan(plan, destination):
    """Persist a retry request locally, including frozen Parquet/original bytes."""
    _validate_frozen(plan)
    destination = Path(destination)
    check(not destination.is_symlink(), 'PLAN_DESTINATION_INVALID', stage='FREEZE_PLAN')
    if destination.exists():
        check(load_plan(destination) == plan, 'PLAN_CONFLICT', stage='FREEZE_PLAN')
        return 'ALREADY_PRESENT_IDENTICAL'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.analytics-plan-', dir=destination.parent) as temporary:
        stage = Path(temporary) / 'plan'
        stage.mkdir()
        _materialize(plan, stage / 'batch')
        (stage / 'plan.json').write_bytes(canonical(plan_document(plan)))
        check(load_plan(stage) == plan, 'PLAN_READBACK_DIFFERS', stage='FREEZE_PLAN')
        check(not destination.exists() and not destination.is_symlink(), 'PLAN_DESTINATION_EXISTS', stage='FREEZE_PLAN')
        os.rename(stage, destination)
    return 'CREATED'


def load_plan(directory):
    directory = Path(directory)
    check(directory.is_dir() and not directory.is_symlink()
          and {p.name for p in directory.iterdir()} == {'plan.json','batch'}, 'PLAN_FILE_SET_DIFFERS')
    try:
        raw = read_local(directory / 'plan.json', JSON_LIMIT)
        value = document(raw, limit=JSON_LIMIT)
        fields(value, ('protocol_version', 'snapshot_id', 'identity', 'limits'))
        check(type(value['protocol_version']) is int and value['protocol_version'] == 1, 'UNSUPPORTED_PLAN')
        target = Destination(**value['identity']['destination'])
        plan = prepare_snapshot(directory / 'batch', target, Limits(**value['limits']))
        check(raw == canonical(plan_document(plan)), 'PLAN_CONTENT_DIFFERS')
        return plan
    except IngestionError:
        raise
    except Exception as error:
        raise IngestionError('PLAN_INVALID', stage='FREEZE_PLAN') from error


def _manifest(plan, versions, data):
    files = [dict(o.inventory(), key=plan.key(o.path), version_id=versions[o.path]) for o in plan.objects]
    value = dict(protocol_version=1, status='SNAPSHOT_COMPLETE', snapshot_id=plan.snapshot_id,
        batch_id=plan.batch_id, schema_version=1, normalizer_version='1.0.0',
        destination=asdict(plan.destination), files=files, observations=data['observations'],
        verification=dict(VERIFICATION), authentication='NOT_REVALIDATED', publication_authority=False,
        delete_protection='NOT_PROVEN', retention_availability='NOT_PROVEN')
    body = canonical(value)
    check(len(body) <= min(JSON_LIMIT, plan.limits.object_bytes)
          and len(body) + sum(len(o.body) for o in plan.objects) <= plan.limits.snapshot_bytes,
          'MANIFEST_LIMIT', stage='FINALIZE')
    return object_bytes('ingestion-manifest.json', body, plan.batch_id)


def _read_files(plan, adapter, versions):
    for item in plan.objects:
        key, version = plan.key(item.path), versions[item.path]
        observed = adapter.compare(key, item, adapter.get(key, version))
        check(observed.version_id == version, 'VERSION_DIFFERS', stage='READBACK', key=key)
        if version is not None:
            latest = adapter.compare(key, item, adapter.get(key))
            check(latest.version_id == version, 'LATEST_VERSION_DIFFERS', stage='READBACK', key=key)


def _inventory(plan, adapter, manifest=None):
    expected = {plan.key(o.path): len(o.body) for o in plan.objects}
    listed = adapter.list_snapshot(plan.snapshot_id)
    marker_key = plan.key('ingestion-manifest.json')
    if manifest is not None:
        expected[marker_key] = len(manifest.body)
    elif marker_key in listed:
        # A concurrent identical writer may have finalized already. Its bytes
        # must still pass conditional-create comparison and full verification.
        del listed[marker_key]
    check(listed == expected, 'REMOTE_FILE_SET_DIFFERS', stage='LIST', operation='ListObjectsV2',
          expected=len(expected), observed=len(listed))


@dataclass(frozen=True)
class VerifiedSnapshot:
    plan: SnapshotPlan
    manifest: object
    manifest_version: object

    def result(self, status):
        return dict(diagnostic_version=1, status='SUCCESS', stage='READBACK', code=status,
            batch_id=self.plan.batch_id, snapshot_id=self.plan.snapshot_id,
            snapshot_uri=self.plan.destination.uri(self.plan.snapshot_id), complete=True, catalog_eligible=True,
            retryable=False, operation='VerifySnapshot', object=self.plan.key(self.manifest.path),
            expected=None, observed={'objects':len(self.plan.objects)+1},
            manifest_sha256=self.manifest.sha256, manifest_version_id=self.manifest_version,
            verification=dict(VERIFICATION))


def read_snapshot(adapter, snapshot_id):
    """Recover exclusively from the injected transport, with external target/ID."""
    hash_id(snapshot_id)
    marker_key = adapter.destination.snapshot_prefix(snapshot_id) + 'ingestion-manifest.json'
    observed_marker = adapter.get(marker_key)
    check(observed_marker is not None, 'SNAPSHOT_PARTIAL_OR_MISSING', stage='READBACK', key=marker_key, retryable=True)
    try:
        value = document(observed_marker.body, limit=JSON_LIMIT)
        fields(value, ('protocol_version', 'status', 'snapshot_id', 'batch_id', 'schema_version', 'normalizer_version',
                       'destination', 'files', 'observations', 'verification', 'authentication', 'publication_authority',
                       'delete_protection', 'retention_availability'))
        check(type(value['protocol_version']) is int and value['protocol_version'] == 1
              and type(value['schema_version']) is int and value['schema_version'] == 1
              and value['normalizer_version'] == '1.0.0' and value['snapshot_id'] == snapshot_id
              and value['status'] == 'SNAPSHOT_COMPLETE', 'UNSUPPORTED_OR_WRONG_MANIFEST', stage='READBACK')
        adapter.authorize(Destination(**value['destination']))
        batch_id = hash_id(value['batch_id'])
        check(type(value['files']) is list and 0 < len(value['files']) < adapter.limits.objects,
              'MANIFEST_FILE_LIMIT', stage='READBACK')
        files, versions, seen, total = [], {}, set(), len(observed_marker.body)
        for record in value['files']:
            fields(record, ('path','size','sha256','content_type','metadata','key','version_id'))
            path = material_path(record['path'])
            key = adapter.destination.snapshot_prefix(snapshot_id) + path
            check(path not in seen and path != 'ingestion-manifest.json' and record['key'] == key,
                  'MANIFEST_PATH_DIFFERS', stage='READBACK')
            seen.add(path)
            hash_id(record['sha256'])
            check(type(record['size']) is int and 0 <= record['size'] <= adapter.limits.object_bytes, 'MANIFEST_SIZE_LIMIT')
            total += record['size']
            check(total <= adapter.limits.snapshot_bytes, 'MANIFEST_SIZE_LIMIT')
            version = record['version_id']
            check(version is None or (type(version) is str and 0 < len(version) <= 1024), 'MANIFEST_VERSION_INVALID')
            body = adapter.get(key, version)
            check(body is not None, 'READBACK_MISSING', stage='READBACK', key=key)
            item = object_bytes(path, body.body, batch_id)
            check(item.inventory() == {k:record[k] for k in item.inventory()}, 'MANIFEST_BYTES_DIFFER', stage='READBACK', key=key)
            adapter.compare(key, item, body)
            check(body.version_id == version, 'VERSION_DIFFERS', stage='READBACK', key=key)
            files.append(item)
            versions[path] = version
        plan = SnapshotPlan(adapter.destination, batch_id, tuple(files), adapter.limits)
        check(plan.snapshot_id == snapshot_id, 'SNAPSHOT_ID_DIFFERS', stage='READBACK')
        data = _validate_frozen(plan)
        request = _manifest(plan, versions, data)
        adapter.compare(marker_key, request, observed_marker)
        _read_files(plan, adapter, versions)
        specific_marker = adapter.compare(marker_key, request, adapter.get(marker_key, observed_marker.version_id))
        latest_marker = adapter.compare(marker_key, request, adapter.get(marker_key))
        check(specific_marker.version_id == latest_marker.version_id == observed_marker.version_id,
              'LATEST_VERSION_DIFFERS', stage='READBACK', key=marker_key)
        _inventory(plan, adapter, request)
        return VerifiedSnapshot(plan, request, observed_marker.version_id)
    except IngestionError:
        raise
    except Exception as error:
        raise IngestionError('MANIFEST_INVALID', stage='READBACK', key=marker_key) from error


def publish_snapshot(plan, adapter):
    adapter.authorize(plan.destination)
    check(len(plan.objects)+1 <= adapter.limits.objects
          and sum(len(o.body) for o in plan.objects) <= adapter.limits.snapshot_bytes
          and all(len(o.body) <= adapter.limits.object_bytes for o in plan.objects), 'TRANSPORT_LIMIT_EXCEEDED')
    data = _validate_frozen(plan, parquet_budget=adapter.limits.parquet_expanded_bytes)
    marker_key = plan.key('ingestion-manifest.json')
    if adapter.get(marker_key) is not None:
        existing = read_snapshot(adapter, plan.snapshot_id)
        check(existing.plan.objects == plan.objects, 'CONTENT_CONFLICT', stage='RECONCILE')
        return existing.result('SNAPSHOT_ALREADY_PRESENT_IDENTICAL')
    versions = {}
    for item in plan.objects:
        _, observed = adapter.create(plan.key(item.path), item)
        versions[item.path] = observed.version_id
    _read_files(plan, adapter, versions)
    _inventory(plan, adapter)
    marker = _manifest(plan, versions, data)
    status, _ = adapter.create(marker_key, marker)
    verified = read_snapshot(adapter, plan.snapshot_id)
    check(verified.plan.objects == plan.objects, 'CONTENT_CONFLICT', stage='READBACK')
    return verified.result('SNAPSHOT_CREATED' if status == 'CREATED' else 'SNAPSHOT_ALREADY_PRESENT_IDENTICAL')


def recover_snapshot(adapter, snapshot_id, destination):
    destination = Path(destination)
    check(not destination.exists() and not destination.is_symlink(), 'RECOVERY_DESTINATION_EXISTS', stage='RECOVER')
    verified = read_snapshot(adapter, snapshot_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.analytics-recovery-', dir=destination.parent) as temporary:
        stage = Path(temporary) / 'batch'
        _materialize(verified.plan, stage)
        read_completed(stage)
        check(not destination.exists() and not destination.is_symlink(), 'RECOVERY_DESTINATION_EXISTS', stage='RECOVER')
        os.rename(stage, destination)
    return verified.result('SNAPSHOT_RECOVERED')
