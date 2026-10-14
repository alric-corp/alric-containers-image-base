"""Stage Factory `sbom-<framework>-<attempt>` build artifacts as a v1 analytics context.

Artifact bytes are only read, never executed. The unchanged normalizer still
verifies hashes, OCI subjects and the validated-index binding. No SDK,
credentials, network or default destination.
"""
import argparse
import io
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile

from scripts.pipeline.analytics.normalize import prepare
from scripts.pipeline.analytics.spdx import (
    AnalyticsError, DOCUMENTS, LIMITS, canonical, digest, document, fields, integer, read_local, require, sha256,
)

SBOMS = {key: 'sbom/' + name for key, (name, _) in DOCUMENTS.items()}
CONSUMED = tuple(sorted(SBOMS.values())) + ('apko.lock.json', 'build-inputs.json', 'validated-index.json')
UNCONSUMED_LIMIT = 32
NAME = re.compile(r'[A-Za-z0-9_.+-]+(?:/[A-Za-z0-9_.+-]+)*')


def _member(name):
    require(type(name) is str and 0 < len(name) <= 255 and NAME.fullmatch(name)
            and all(part not in ('.', '..') for part in name.split('/')), 'unsafe artifact member path')
    return name


def _add(members, name, body):
    require(name not in members, 'duplicate artifact member')
    require(len(members) < len(CONSUMED) + UNCONSUMED_LIMIT, 'artifact member count limit')
    require(sum(len(b) for b in members.values()) + len(body) <= LIMITS['batch_bytes'], 'artifact byte limit')
    members[name] = body


def _read_zip(path):
    raw = read_local(path, LIMITS['batch_bytes'])
    members = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for info in archive.infolist():
                if info.filename.endswith('/'):
                    _member(info.filename[:-1])  # Directory entries carry no bytes.
                    continue
                _member(info.filename)
                require(not info.flag_bits & 1, 'encrypted artifact member')
                require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), 'unsupported artifact compression')
                require(stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG), 'artifact member must be a regular file')
                require(info.file_size <= LIMITS['document_bytes'], 'artifact member byte limit')
                with archive.open(info) as stream:
                    body = stream.read(LIMITS['document_bytes'] + 1)
                require(len(body) == info.file_size, 'artifact member size differs')
                _add(members, info.filename, body)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError, RuntimeError, EOFError) as error:
        raise AnalyticsError('invalid artifact ZIP') from error
    return members, sha256(raw)


def _read_directory(path):
    members, pending = {}, [(path, '')]
    while pending:
        parent, prefix = pending.pop()
        with os.scandir(parent) as entries:
            for entry in entries:
                name = _member(prefix + entry.name)
                require(not entry.is_symlink(), 'artifact member must not be a symlink')
                if entry.is_dir(follow_symlinks=False):
                    require(name.count('/') < 4, 'artifact directory depth limit')
                    pending.append((Path(entry.path), name + '/'))
                else:
                    require(entry.is_file(follow_symlinks=False), 'artifact member must be a regular file')
                    _add(members, name, read_local(Path(entry.path), LIMITS['document_bytes']))
    return members, None


def _verified_inputs(framework, members, origin, expected_index):
    missing = [name for name in CONSUMED if name not in members]
    require(not missing, framework + ': artifact member missing: ' + ', '.join(missing))
    index = document(members['validated-index.json'], limit=LIMITS['context_bytes'])
    fields(index, ('digest', 'platforms', 'sboms'), label='validated-index.json')
    index_digest = digest(index['digest'], 'validated index digest', oci=True)
    fields(index['platforms'], tuple(k for k in DOCUMENTS if k != 'index'), label='validated-index platforms')
    if expected_index is not None:
        require(digest(expected_index, 'expected index digest', oci=True) == index_digest,
                framework + ': validated index differs from the expected index digest')
    registered = index['sboms']
    require(type(registered) is list and len(registered) == len(SBOMS), 'validated-index SBOM inventory differs')
    hashes = {}
    for record in registered:
        fields(record, ('path', 'subject', 'sha256'), label='validated-index SBOM')
        require(record['path'] in SBOMS.values() and record['path'] not in hashes, 'validated-index SBOM inventory differs')
        hashes[record['path']] = digest(record['sha256'], 'validated-index SBOM SHA256')
    build = document(members['build-inputs.json'], limit=LIMITS['context_bytes'])
    revisions = [build.get('revision')]
    if type(build.get('annotations')) is dict and 'revision' in build['annotations']:
        revisions.append(build['annotations']['revision'])
    require(all(r == origin['source_sha'] for r in revisions), framework + ': build-inputs revision differs from origin')
    require(build.get('lock_sha256') == sha256(members['apko.lock.json']),
            framework + ': apko.lock.json differs from build-inputs lock_sha256')
    return index_digest, dict(index['platforms']), hashes


def stage(selection, work, *, base_directory=Path('.')):
    """Write verified SPDX/validated-index bytes and context.json into a new private directory."""
    fields(selection, ('schema_version', 'origin', 'image_registry', 'repository_prefix', 'artifacts'),
           label='artifact selection')
    require(type(selection['schema_version']) is int and selection['schema_version'] == 1, 'unsupported selection schema')
    origin = selection['origin']
    require(type(origin) is dict, 'origin must be an object')
    integer(origin.get('run_id'), 'run_id')
    run_attempt = integer(origin.get('run_attempt'), 'run_attempt')
    digest(origin.get('source_sha'), 'source SHA', git=True)
    registry, prefix = selection['image_registry'], selection['repository_prefix']
    require(type(registry) is str and re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*(?::[0-9]{1,5})?(?:/[a-z0-9._-]+)*', registry),
            'image_registry: registry host required (no scheme)')
    require(type(prefix) is str and re.fullmatch(r'[a-z0-9._/-]{0,64}', prefix), 'invalid repository_prefix')
    artifacts = selection['artifacts']
    require(type(artifacts) is list and 0 < len(artifacts) <= LIMITS['documents'] // 3, 'artifact count/type limit')
    work = Path(work)
    require(not work.exists() and not work.is_symlink(), 'staging directory must not exist')
    work.parent.mkdir(parents=True, exist_ok=True)
    images, receipts, frameworks = [], [], set()
    with tempfile.TemporaryDirectory(prefix='.sbom-artifact-input-', dir=work.parent) as temporary:
        staged = Path(temporary) / 'stage'
        for item in artifacts:
            fields(item, ('framework', 'name', 'path'), ('artifact_id', 'expected_index_digest'), 'selected artifact')
            framework = item['framework']
            require(type(framework) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]*', framework)
                    and framework not in frameworks, 'invalid/duplicate framework')
            frameworks.add(framework)
            require(item['name'] == 'sbom-%s-%d' % (framework, run_attempt),
                    framework + ': artifact name differs from framework/run attempt')
            if item.get('artifact_id') is not None:
                integer(item['artifact_id'], 'artifact_id')
            require(type(item['path']) is str and item['path'] != '', 'artifact path required')
            source = Path(base_directory) / item['path']
            require(not source.is_symlink(), 'artifact path must not be a symlink')
            if source.is_dir():
                members, archive_hash = _read_directory(source)
            else:
                require(source.suffix == '.zip', 'artifact path must be a directory or .zip file')
                members, archive_hash = _read_zip(source)
            index_digest, platforms, hashes = _verified_inputs(framework, members, origin, item.get('expected_index_digest'))
            for name in CONSUMED:
                if name.startswith('sbom/') or name == 'validated-index.json':
                    path = staged / framework / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(members[name])
            reference = '%s@run:%d/attempt:%d/artifact:%s' % (origin.get('repository'), origin.get('run_id'),
                                                            run_attempt, item['name'])
            if item.get('artifact_id') is not None:
                reference += '/id:%d' % item['artifact_id']
            documents = []
            for key, name in SBOMS.items():
                record = dict(path=framework + '/' + name, sbom_scope='index' if key == 'index' else 'platform',
                              document_platform=DOCUMENTS[key][1], sha256=hashes[name], source_path=name)
                if item.get('artifact_id') is not None:
                    record['artifact_id'] = item['artifact_id']
                documents.append(record)
            images.append(dict(framework=framework, image_repository=registry + '/' + prefix + framework,
                               image_index_digest=index_digest, platforms=platforms, documents=documents,
                               validation=dict(path=framework + '/validated-index.json', reference=reference)))
            receipts.append(dict(framework=framework, name=item['name'], artifact_id=item.get('artifact_id'),
                                 archive_sha256=archive_hash, reference=reference,
                                 consumed={n: dict(size=len(members[n]), sha256=sha256(members[n])) for n in CONSUMED},
                                 unconsumed={n: dict(size=len(b), sha256=sha256(b))
                                             for n, b in sorted(members.items()) if n not in CONSUMED}))
        context = dict(schema_version=1, origin=origin, images=images)
        projection = prepare(context, base_directory=staged)  # Full existing validation before visibility.
        (staged / 'context.json').write_bytes(canonical(context))
        receipt = dict(schema_version=1, status='STAGED', batch_id=projection.batch_id, context='context.json',
                       artifacts=receipts, cloud_calls=0, cryptographic_authenticity='NOT_REVALIDATED',
                       publication_authority=False)
        (staged / 'staging-receipt.json').write_bytes(canonical(receipt))
        require(not work.exists() and not work.is_symlink(), 'staging directory must not exist')
        os.rename(staged, work)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', required=True, type=Path,
                        help='v1 selection JSON; artifact paths are relative to this file')
    parser.add_argument('--work', required=True, type=Path, help='new private staging directory')
    args = parser.parse_args(argv)
    try:
        selection = document(read_local(args.selection, LIMITS['context_bytes']), limit=LIMITS['context_bytes'])
        result = stage(selection, args.work, base_directory=args.selection.resolve().parent)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('SBOM artifact staging failed: ' + str(error), file=sys.stderr)
        return 1
    print(canonical(result).decode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
