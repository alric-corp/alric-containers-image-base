"""Map Factory SPDX 2.3 bytes to records, independently of Parquet or cloud."""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
NORMALIZER_VERSION = '1.0.0'
LIMITS = dict(document_bytes=32 * 1024 * 1024, context_bytes=4 * 1024 * 1024,
              batch_bytes=128 * 1024 * 1024, documents=512, packages=100000,
              batch_packages=250000, references=128, depth=64)
DOCUMENTS = {'index': ('sbom-index.spdx.json', None),
             'linux/amd64': ('sbom-x86_64.spdx.json', 'linux/amd64'),
             'linux/arm64': ('sbom-aarch64.spdx.json', 'linux/arm64')}


class AnalyticsError(ValueError):
    """Invalid/incomplete input or output; never an approval decision."""


def require(condition, message):
    if not condition:
        raise AnalyticsError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def fields(value, required, optional=(), label='object'):
    require(type(value) is dict and set(required) <= set(value)
            and set(value) <= set(required) | set(optional), label + ': missing/unknown fields')


def text(value, label, *, optional=False):
    if value is None and optional:
        return None
    require(type(value) is str, label + ': string required')
    return value


def integer(value, label):
    require(type(value) is int and 0 < value <= 2**63 - 1, label + ': positive int64 required')
    return value


def digest(value, label='digest', *, oci=False, git=False):
    pattern = ('sha256:' if oci else '') + '[0-9a-f]{' + ('40' if git else '64') + '}'
    require(type(value) is str and re.fullmatch(pattern, value), label + ': invalid digest')
    return value


def timestamp(value, label):
    text(value, label)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise AnalyticsError(label + ': invalid timestamp') from error
    require(parsed.tzinfo is not None, label + ': timezone required')
    return value  # The original representation, including offset, is retained.


def read_local(path, limit):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), str(path) + ': regular local file required')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, str(path) + ': byte limit exceeded')
    return raw


def document(raw, *, limit=None):
    require(type(raw) is bytes and len(raw) <= (limit or LIMITS['document_bytes']), 'JSON byte/type limit')

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result

    def constant(value):
        raise AnalyticsError('non-finite JSON value: ' + value)

    try:
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
        pending = [(result, 0)]
        while pending:
            value, depth = pending.pop()
            require(depth <= LIMITS['depth'], 'JSON depth limit')
            if isinstance(value, (dict, list)):
                pending.extend((v, depth + 1) for v in (value.values() if isinstance(value, dict) else value))
            if isinstance(value, float):
                require(math.isfinite(value), 'non-finite JSON number')
    except (UnicodeError, ValueError, RecursionError) as error:
        raise AnalyticsError('invalid JSON: ' + str(error)) from error
    require(type(result) is dict, 'JSON document must be an object')
    return result


def packages(raw, expected_subject):
    """Require the Factory documentDescribes/SHA256 contract; preserve values."""
    digest(expected_subject, 'expected subject', oci=True)
    value = document(raw)
    require(value.get('spdxVersion') == 'SPDX-2.3', 'unsupported SPDX version (expected SPDX-2.3)')
    require(value.get('SPDXID') == 'SPDXRef-DOCUMENT', 'SPDXRef-DOCUMENT identifier required')
    namespace = text(value.get('documentNamespace'), 'documentNamespace')
    require(namespace and urlsplit(namespace).scheme and not any(c.isspace() for c in namespace),
            'absolute documentNamespace URI required')
    describes = value.get('documentDescribes')
    require(type(describes) is list and len(describes) == 1 and type(describes[0]) is str,
            'one unambiguous documentDescribes package required')
    source = value.get('packages')
    require(type(source) is list and 0 < len(source) <= LIMITS['packages'], 'package count/type limit')
    rows, identifiers, raw_hash = [], set(), sha256(raw)
    for package in source:
        require(type(package) is dict, 'package must be an object')
        identifier = text(package.get('SPDXID'), 'package SPDXID')
        require(re.fullmatch(r'SPDXRef-[A-Za-z0-9.-]+', identifier), 'invalid package SPDXID')
        require(identifier not in identifiers and identifier != value.get('SPDXID'), 'duplicate package SPDXID')
        identifiers.add(identifier)
        name = text(package.get('name'), 'package name')
        require(name != '', 'empty package name')
        references, purls = None, None
        if 'externalRefs' in package:
            refs = package['externalRefs']
            require(type(refs) is list and len(refs) <= LIMITS['references'], 'external reference count/type limit')
            references, purls = [], []
            for ref in refs:
                fields(ref, ('referenceCategory', 'referenceType', 'referenceLocator'), ('comment',), 'external reference')
                record = {target: text(ref.get(origin), origin, optional=(origin == 'comment'))
                          for target, origin in [('reference_category', 'referenceCategory'),
                            ('reference_type', 'referenceType'), ('reference_locator', 'referenceLocator'), ('comment', 'comment')]}
                references.append(record)
                if ref['referenceType'] == 'purl':
                    require(ref['referenceLocator'].startswith('pkg:'), 'invalid PURL reference locator')
                    purls.append(ref['referenceLocator'])
        rows.append(dict(schema_version=SCHEMA_VERSION, normalizer_version=NORMALIZER_VERSION,
            sbom_sha256=raw_hash, package_spdx_id=identifier, package_name=name,
            package_version=text(package.get('versionInfo'), 'versionInfo', optional=True), purls=purls,
            external_references=references,
            license_declared=text(package.get('licenseDeclared'), 'licenseDeclared', optional=True),
            license_concluded=text(package.get('licenseConcluded'), 'licenseConcluded', optional=True),
            supplier=text(package.get('supplier'), 'supplier', optional=True),
            download_location=text(package.get('downloadLocation'), 'downloadLocation', optional=True),
            primary_package_purpose=text(package.get('primaryPackagePurpose'), 'primaryPackagePurpose', optional=True),
            is_document_subject=identifier == describes[0]))
    roots = [p for p in source if p['SPDXID'] == describes[0]]
    require(len(roots) == 1, 'document root package missing/ambiguous')
    checksums = roots[0].get('checksums')
    require(type(checksums) is list, 'subject SHA256 checksum required')
    hashes = []
    for item in checksums:
        fields(item, ('algorithm', 'checksumValue'), label='subject checksum')
        text(item['algorithm'], 'checksum algorithm')
        text(item['checksumValue'], 'checksum value')
        if item['algorithm'] == 'SHA256':
            hashes.append(item['checksumValue'])
    require(hashes == [expected_subject[7:]], 'subject checksum differs from expected OCI identity')
    relationships = value.get('relationships')
    if relationships is not None:
        require(type(relationships) is list and len(relationships) <= LIMITS['packages'] * 8,
                'relationship count/type limit')
        for relationship in relationships:
            fields(relationship, ('spdxElementId', 'relatedSpdxElement', 'relationshipType'), ('comment',), 'relationship')
            for key in ('spdxElementId', 'relatedSpdxElement', 'relationshipType'):
                text(relationship[key], key)
            if relationship['relationshipType'] == 'DESCRIBES' and relationship['spdxElementId'] == value.get('SPDXID'):
                require(relationship['relatedSpdxElement'] == describes[0], 'ambiguous relationship document root')
            if relationship['relationshipType'] == 'DESCRIBED_BY' and relationship['relatedSpdxElement'] == value.get('SPDXID'):
                require(relationship['spdxElementId'] == describes[0], 'ambiguous relationship document root')
    created = None
    if 'creationInfo' in value:
        require(type(value['creationInfo']) is dict, 'creationInfo must be an object')
        if 'created' in value['creationInfo']:
            created = timestamp(value['creationInfo']['created'], 'SPDX creationInfo.created')
    return value, sorted(rows, key=lambda r: r['package_spdx_id']), created, (
        len(relationships) if relationships is not None else None)
