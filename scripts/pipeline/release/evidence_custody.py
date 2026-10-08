"""Offline HGC-04 v1 custody. No acquisition client or production signer.

Integrity inspection is not authentication. Production authentication is
deliberately unavailable; COMPLETE_VERIFIED is explicitly TEST_ONLY here.
The only subprocess is the externally authorized HGC-03 script, after auth.
"""
import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Protocol

from scripts.pipeline.release.evidence_archive import (
    LIMITS, ExpansionBudget, InvalidEvidence, canonical, check_inventory, digest,
    document, extract_new, fields, inventory, json_value, make_zip, positive, read_zip, require,
    safe_path, sha256,
)
from scripts.pipeline.release.evidence_store import FrozenObject, ReadStatus, WriteStatus
from scripts.pipeline.release.evidence_store import WriteResult
from scripts.pipeline.release.release_manifest import checksum, release_units, validate as validate_release_manifest
from scripts.pipeline.release.verify_publication import verify_publication
from scripts.pipeline.runtime.runtime_images import publication_contract

CORE = ('melange-repo', 'melange-reproduction-reference', 'melange-reproducibility')
RECEIPTS = ('binfmt-evidence.json', 'melange-environment-evidence.json', 'melange-reproducibility-evidence.json')
VERIFIER_REPOSITORY = 'alric-corp/alric-containers-reusable-workflows'
VERIFIER_COMMIT = 'fd44ef512cf2e3ef9c65d0c005a9aa878ee26a69'
VERIFIER_SHA256 = '93504d7fd1b887b29c318c8e75eb0a41e282fd37453410e5ab7c6b9b19f1ca1a'
VERIFIER_PATH = 'scripts/verify_reproducibility.py'
LIMITATIONS = [
    'READBACK_VERIFIED: CA outputs, indexes, public keys, signatures, control/data and recovered bindings',
    'VERIFIED_BY_HOSTED_JOB: historical cache and RESOLUTION_INDEX are not preserved',
    'NOT_PROVEN: dependency replay, complete OCI layers, CROSS_RUN, FULL authority, proving or U3A',
    'TEST_ONLY: no production custody, keyless profile or deployed storage enforcement is demonstrated',
]


def _workflow(value, label, reusable=False):
    fields(value, 'repository path sha' if reusable else 'path sha', label)
    safe_path(value['path'])
    require(value['path'].startswith('.github/workflows/') and value['path'].endswith('.yml'), label + ': workflow path')
    digest(value['sha'], label + ' SHA', 40)
    if reusable:
        require(value['repository'] == VERIFIER_REPOSITORY, 'unsupported reusable repository')


def _identity(value):
    fields(value, 'repository repository_id owner_id source_registry release_id run_id run_attempt event ref source_sha '
           'caller reusable archiver publisher reviewer candidates', 'identity')
    require(type(value['repository']) is str and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value['repository']),
            'invalid repository')
    for name in ('repository_id', 'owner_id', 'run_id', 'run_attempt'):
        positive(value[name], name)
    require(value['release_id'] == f'r{value["run_id"]}-a{value["run_attempt"]}', 'release ID mismatch')
    digest(value['source_sha'], 'source SHA', 40)
    require(type(value['source_registry']) is str and re.fullmatch(r'[a-z0-9.-]+', value['source_registry']),
            'expected source registry required')
    require(value['event'] in ('push', 'schedule', 'workflow_dispatch') and value['ref'] == 'refs/heads/develop',
            'PR/non-release context is ineligible')
    _workflow(value['caller'], 'caller')
    _workflow(value['reusable'], 'reusable', reusable=True)
    require(value['caller']['sha'] == value['source_sha'] and value['reusable']['sha'] == VERIFIER_COMMIT
            and value['reusable']['path'] == '.github/workflows/validate-apko-images.yml', 'caller/reusable binding')
    for role in ('archiver', 'publisher'):
        actor = value[role]
        fields(actor, 'workflow sha run_id run_attempt job', role)
        safe_path(actor['workflow'])
        digest(actor['sha'], role + ' SHA', 40)
        positive(actor['run_id'], role + ' run')
        positive(actor['run_attempt'], role + ' attempt')
        require(type(actor['job']) is str and actor['job'], role + ' job required')
    require(value['publisher']['workflow'] == '.github/workflows/build-base-images.yml'
            and value['publisher']['sha'] == value['source_sha']
            and value['publisher']['run_id'] == value['run_id']
            and value['publisher']['run_attempt'] == value['run_attempt'], 'publisher identity mismatch')
    require(value['reviewer'] in ('NOT_DEMONSTRATED', 'AUTHOR_SELF_REVIEW'), 'review is not inferred from custody')
    candidates = value['candidates']
    require(type(candidates) is list and candidates, 'candidate list required')
    names = []
    for candidate in candidates:
        fields(candidate, 'framework digest platforms', 'candidate')
        name = safe_path(candidate['framework'])
        require('/' not in name, 'invalid framework')
        names.append(name)
        require(type(candidate['digest']) is str and candidate['digest'].startswith('sha256:'), 'candidate digest required')
        digest(candidate['digest'][7:])
        fields(candidate['platforms'], 'linux/amd64 linux/arm64', 'platforms')
        require(len(set(candidate['platforms'].values())) == 2, 'distinct platform digests required')
        for item in candidate['platforms'].values():
            require(type(item) is str and item.startswith('sha256:'), 'platform digest required')
            digest(item[7:])
    require(names == sorted(set(names)), 'candidate order/duplicates')
    release_units(names)  # Existing complete runtime/dev membership contract, unchanged.


@dataclass(frozen=True)
class ExpectedIdentity:
    raw: bytes

    @classmethod
    def freeze(cls, value):
        return cls(canonical(value))

    def __post_init__(self):
        _identity(document(self.raw))

    @property
    def value(self):
        return document(self.raw)

    @property
    def prefix(self):
        return f'releases/{self.value["release_id"]}/evidence/hgc04/v1/'


@dataclass(frozen=True)
class VerifierAuthorization:
    repository: str
    commit: str
    path: str
    sha256: str

    def validate(self):
        require((self.repository, self.commit, self.path, self.sha256) ==
                (VERIFIER_REPOSITORY, VERIFIER_COMMIT, VERIFIER_PATH, VERIFIER_SHA256),
                'verifier is not the supported externally authorized pin')


@dataclass(frozen=True)
class TrustPolicy:
    policy_id: str
    profile: str
    trusted_public_key: bytes
    verifier: VerifierAuthorization


@dataclass(frozen=True)
class Authentication:
    profile: str
    manifest_sha256: str
    expected_identity_sha256: str


class Authenticator(Protocol):
    def authenticate(self, manifest: bytes, bundle: bytes, policy: TrustPolicy,
                     expected: ExpectedIdentity) -> Authentication:
        """Verify against externally supplied trust; never import a bundled root."""
        ...


def authenticate(manifest, bundle, policy, expected, authenticator):
    require(isinstance(policy, TrustPolicy) and authenticator is not None, 'external trust/authenticator required')
    require(policy.profile == 'TEST_ONLY', 'production keyless authentication is NOT_PROVEN and disabled')
    require(type(policy.policy_id) is str and policy.policy_id and type(policy.trusted_public_key) is bytes
            and policy.trusted_public_key, 'external trust configuration required')
    policy.verifier.validate()
    try:
        result = authenticator.authenticate(manifest, bundle, policy, expected)
    except (OSError, subprocess.SubprocessError):
        raise
    except Exception as error:
        raise InvalidEvidence('authentication failed: ' + str(error)) from error
    require(isinstance(result, Authentication) and result == Authentication(
        policy.profile, sha256(manifest), sha256(expected.raw)), 'authenticator did not authenticate this request')
    return result


def _time(value):
    require(type(value) is str, 'timestamp string required')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise InvalidEvidence('invalid timestamp') from error
    require(result.tzinfo is not None, 'timestamp offset required')
    return result


def _index(items, key, label):
    require(type(items) is list, label + ': list required')
    result = {}
    for item in items:
        require(type(item) is dict and key in item and item[key] not in result, label + ': duplicate/missing identity')
        result[item[key]] = item
    return result


def _acquisition(raw, expected):
    context, identity = document(raw), expected.value
    fields(context, 'schema_version purpose run referenced_workflows jobs artifacts producers checkouts candidates build_date',
           'acquisition')
    require(type(context['schema_version']) is int and context['schema_version'] == 1
            and context['purpose'] == 'HISTORICAL_TEST_INPUT', 'unsupported acquisition schema/purpose')
    run = context['run']
    fields(run, 'repository repository_id owner_id id run_attempt event ref head_sha path', 'external run')
    for name in ('repository_id', 'owner_id', 'id', 'run_attempt'):
        positive(run[name], 'external run ' + name)
    require(run == dict(repository=identity['repository'], repository_id=identity['repository_id'], owner_id=identity['owner_id'],
                        id=identity['run_id'], run_attempt=identity['run_attempt'], event=identity['event'],
                        ref=identity['ref'], head_sha=identity['source_sha'], path=identity['caller']['path']),
            'external run identity mismatch')
    refs = context['referenced_workflows']
    require(type(refs) is list and refs, 'external resolved workflows required')
    for ref in refs:
        fields(ref, 'repository path sha', 'resolved workflow')
        safe_path(ref['path'])
        digest(ref['sha'], length=40)
    require(identity['reusable'] in refs, 'external reusable resolution differs')
    require(dict(repository=identity['repository'], path=identity['publisher']['workflow'], sha=identity['publisher']['sha'])
            in refs, 'external publisher workflow resolution differs')
    jobs = _index(context['jobs'], 'id', 'jobs')
    for job in jobs.values():
        fields(job, 'id run_id run_attempt job_key runner_id runner status conclusion', 'producer job')
        positive(job['id'], 'job ID')
        positive(job['runner_id'], 'runner ID')
        positive(job['run_attempt'], 'job attempt')
        require(job['run_id'] == identity['run_id'] and job['run_attempt'] <= identity['run_attempt']
                and type(job['job_key']) is str and job['job_key'] and type(job['runner']) is str and job['runner']
                and job['status'] == 'completed' and job['conclusion'] == 'success', 'producer job not eligible')
    artifacts = _index(context['artifacts'], 'id', 'artifacts')
    for artifact in artifacts.values():
        fields(artifact, 'id name run_id source_sha size sha256 created_at expires_at producer_job_id zip_preserved', 'artifact')
        positive(artifact['id'], 'artifact ID')
        safe_path(artifact['name'])
        require(artifact['run_id'] == identity['run_id'] and artifact['source_sha'] == identity['source_sha']
                and artifact['producer_job_id'] in jobs and type(artifact['size']) is int and artifact['size'] > 0
                and type(artifact['zip_preserved']) is bool, 'artifact origin/size mismatch')
        digest(artifact['sha256'])
        require(_time(artifact['expires_at']) > _time(artifact['created_at']), 'artifact dates differ')
    fields(context['producers'], ' '.join(CORE), 'core producers')
    for name, producer in context['producers'].items():
        fields(producer, 'artifact_id job_id', 'artifact producer binding')
        require(producer['artifact_id'] in artifacts and producer['job_id'] in jobs, 'producer unavailable')
        artifact = artifacts[producer['artifact_id']]
        require(artifact['name'] == name and artifact['producer_job_id'] == producer['job_id'] and artifact['zip_preserved'],
                'artifact/producer binding differs')
    checkouts = context['checkouts']
    require(type(checkouts) is list, 'external checkout list required')
    for checkout in checkouts:
        fields(checkout, 'job_id repository sha', 'checkout')
        require(checkout['job_id'] in jobs, 'checkout job unavailable')
        digest(checkout['sha'], length=40)
    for producer in context['producers'].values():
        for repository, revision in ((identity['repository'], identity['source_sha']),
                                     (identity['reusable']['repository'], identity['reusable']['sha'])):
            require(dict(job_id=producer['job_id'], repository=repository, sha=revision) in checkouts,
                    'source/executor checkout binding missing')
    _time(context['build_date'])
    candidates = _index(context['candidates'], 'framework', 'external candidates')
    require(set(candidates) == {c['framework'] for c in identity['candidates']}, 'external candidate set differs')
    for name, candidate in candidates.items():
        fields(candidate, 'framework validation_job_id publication_job_id validated_artifact_id sbom_artifact_id '
               'publication_artifact_id trust_artifact_id', 'external candidate')
        require(candidate['validation_job_id'] in jobs and candidate['publication_job_id'] in jobs
                and jobs[candidate['validation_job_id']]['job_key'] == 'validate'
                and jobs[candidate['publication_job_id']]['run_attempt'] == identity['run_attempt']
                and jobs[candidate['publication_job_id']]['job_key'] == identity['publisher']['job'], 'candidate jobs differ')
        for field, artifact_name, job_field in (
                ('validated_artifact_id', f'validated-oci-{name}', 'validation_job_id'),
                ('sbom_artifact_id', f'sbom-{name}-{jobs[candidate["validation_job_id"]]["run_attempt"]}', 'validation_job_id'),
                ('publication_artifact_id', f'publication-{name}-{identity["run_attempt"]}', 'publication_job_id')):
            # SBOM names do not establish identity; ID/job/run are all required.
            require(candidate[field] in artifacts, 'candidate artifact missing')
            artifact = artifacts[candidate[field]]
            require(artifact['name'] == artifact_name
                    and artifact['producer_job_id'] == candidate[job_field], 'candidate artifact producer differs')
        require(candidate['trust_artifact_id'] in artifacts, 'cryptographic material origin missing')
        trust_artifact = artifacts[candidate['trust_artifact_id']]
        trust_job = jobs[trust_artifact['producer_job_id']]
        require(trust_artifact['name'] == f'release-dev-{identity["run_attempt"]}'
                and trust_job['job_key'] == 'approve' and trust_job['run_attempt'] == identity['run_attempt'],
                'cryptographic material producer differs')
    return context, jobs, artifacts


def _receipt(raw, kind):
    value = document(raw)
    require(value.get('kind') == kind and type(value.get('schema_version')) is int and value['schema_version'] == 1,
            'unsupported HGC receipt')
    return value


def _core_sets(core, context, jobs, expected):
    identity = expected.value
    environment = _receipt(core['melange-repo']['melange-environment-evidence.json'], 'melange-environment-evidence')
    binfmt = _receipt(core['melange-repo']['binfmt-evidence.json'], 'binfmt-evidence')
    reference = _receipt(core['melange-reproduction-reference']['melange-reproduction-reference.json'], 'melange-reproduction-reference')
    reproduction = _receipt(core['melange-reproducibility']['melange-reproducibility-evidence.json'], 'melange-reproducibility-evidence')
    producers = [(binfmt['producer'], 'melange-repo'), (environment['producer'], 'melange-repo'),
                 (reference['producer'], 'melange-reproduction-reference'),
                 (reproduction['reference']['producer'], 'melange-reproduction-reference'),
                 (reproduction['rebuild']['producer'], 'melange-reproducibility')]
    for producer, artifact in producers:
        positive(producer.get('run_id'), 'receipt run')
        positive(producer.get('run_attempt'), 'receipt attempt')
        job = jobs[context['producers'][artifact]['job_id']]
        require(all(producer.get(k) == identity[k] for k in ('repository', 'run_id', 'ref', 'source_sha'))
                and producer.get('release_id') == f'r{identity["run_id"]}-a{job["run_attempt"]}'
                and producer.get('workflow') == identity['caller']['path']
                and producer.get('run_attempt') == job['run_attempt'], 'receipt producer differs from external context')
        if 'job' in producer:
            require(producer['job'] == job['job_key'] and producer['runner'] == job['runner'], 'receipt job/runner differs')
    ref_job = jobs[context['producers']['melange-reproduction-reference']['job_id']]
    rebuild_job = jobs[context['producers']['melange-reproducibility']['job_id']]
    require(context['producers']['melange-repo']['job_id'] == ref_job['id']
            and ref_job['id'] != rebuild_job['id'] and ref_job['runner_id'] != rebuild_job['runner_id']
            and ref_job['runner'] != rebuild_job['runner']
            and reproduction['independence'] == 'CROSS_JOB_SAME_RUN', 'independent producer binding differs')
    targets = sorted(reproduction['scope']['targets'])
    require(targets == ['aarch64', 'x86_64'] and sorted(environment['outputs']) == targets
            and sorted(reproduction['rebuild']['outputs']) == targets, 'CA target contract differs')
    sets = {CORE[0]: set(('binfmt-evidence.json', 'melange-environment-evidence.json', 'melange-version.txt', 'melange.rsa.pub')),
            CORE[1]: {'melange-reproduction-reference.json'}, CORE[2]: {'melange-reproducibility-evidence.json', 'rebuild/melange.rsa.pub'}}
    for arch in targets:
        outputs = environment['outputs'][arch]
        rebuild = reproduction['rebuild']['outputs'][arch]
        require(type(outputs) is list and outputs and type(rebuild) is list and rebuild, 'nonempty output lists required')
        names = []
        for item in outputs:
            positive(item['size'], 'reference output size')
            name = safe_path(item['path']).rsplit('/', 1)[-1]
            require(name.endswith('.apk'), 'APK output required')
            path = f'packages/{arch}/{name}'
            require(path in core[CORE[0]] and sha256(core[CORE[0]][path]) == item['sha256']
                    and len(core[CORE[0]][path]) == item['size'], 'reference output hash/size differs')
            names.append(name)
            sets[CORE[0]].add(path)
        require(len(names) == len(set(names)), 'duplicate reference output')
        rebuild_names = []
        for item in rebuild:
            positive(item['apk_size'], 'rebuild output size')
            name = safe_path(item['file'])
            require('/' not in name and name.endswith('.apk'), 'invalid rebuild output path')
            path = f'rebuild/packages/{arch}/{name}'
            require(path in core[CORE[2]] and sha256(core[CORE[2]][path]) == item['apk_sha256']
                    and len(core[CORE[2]][path]) == item['apk_size'], 'rebuild output hash/size differs')
            rebuild_names.append(name)
            sets[CORE[2]].add(path)
        require(sorted(rebuild_names) == sorted(names), 'reference/rebuild output sets differ')
        sets[CORE[0]].add(f'packages/{arch}/APKINDEX.tar.gz')
        sets[CORE[2]].add(f'rebuild/packages/{arch}/APKINDEX.tar.gz')
    for name in CORE:
        require(set(core[name]) == sets[name], name + ': exact file set differs')
    require(reference['temporal']['build_date'] == context['build_date'], 'external BUILD_DATE differs')
    return environment


def _git_oid(kind, raw):
    return hashlib.sha1(kind.encode() + b' ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def _git_commit(files, namespace, revision, used):
    path = f'git/{namespace}/commit'
    require(path in files, 'Git commit object missing')
    used.add(path)
    raw = files[path]
    require(_git_oid('commit', raw) == revision, 'Git commit identity differs')
    first = raw.split(b'\n', 1)[0]
    require(re.fullmatch(b'tree [0-9a-f]{40}', first), 'Git root tree missing')
    return first[5:].decode(), raw


def _git_file(files, namespace, root, source_path, payload_path, used):
    tree = root
    parts = safe_path(source_path).split('/')
    for position, part in enumerate(parts):
        tree_path = f'git/{namespace}/trees/{tree}'
        require(tree_path in files, 'Git path proof missing')
        used.add(tree_path)
        raw = files[tree_path]
        require(_git_oid('tree', raw) == tree, 'Git tree identity differs')
        entries, offset = {}, 0
        while offset < len(raw):
            end = raw.find(b'\0', offset)
            require(end > offset and end + 21 <= len(raw), 'malformed Git tree')
            header = raw[offset:end].decode('utf-8')
            mode, name = header.split(' ', 1)
            require(name not in entries and '/' not in name, 'duplicate/invalid Git tree name')
            entries[name] = (mode, raw[end + 1:end + 21].hex())
            offset = end + 21
        require(part in entries, 'source path not in executed Git tree')
        mode, oid = entries[part]
        if position < len(parts) - 1:
            require(mode == '40000', 'Git path is not a tree')
            tree = oid
        else:
            require(mode in ('100644', '100755') and payload_path in files
                    and _git_oid('blob', files[payload_path]) == oid, 'Git source blob differs or is a link')
            used.add(payload_path)


def _source(files, environment, context, expected):
    identity, used = expected.value, set()
    root, commit = _git_commit(files, 'source', identity['source_sha'], used)
    match = re.search(rb'^committer .* ([0-9]+) ([+-][0-9]{4})$', commit.split(b'\n\n', 1)[0], re.MULTILINE)
    require(match is not None, 'Git committer date missing')
    epoch, offset = int(match[1]), match[2].decode()
    minutes = (int(offset[1:3]) * 60 + int(offset[3:])) * (1 if offset[0] == '+' else -1)
    date = datetime.fromtimestamp(epoch, timezone(timedelta(minutes=minutes))).isoformat()
    require(date == context['build_date'], 'BUILD_DATE differs from exact Git committer offset')
    records = environment['environment']['source_files']
    require(type(records) is list and records, 'source file evidence missing')
    paths = set()
    configuration = environment['environment']['configuration']
    for record in records:
        fields(record, 'path sha256', 'source file')
        path = safe_path(record['path'])
        require(path not in paths, 'duplicate source file')
        paths.add(path)
        payload_path = 'source/' + path
        _git_file(files, 'source', root, path, payload_path, used)
        require(sha256(files[payload_path]) == record['sha256'], 'source file differs from HGC-02')
    require(configuration['path'] in paths and sha256(files['source/' + configuration['path']]) == configuration['sha256'],
            'configuration source binding differs')
    root, _ = _git_commit(files, 'reusable', identity['reusable']['sha'], used)
    _git_file(files, 'reusable', root, VERIFIER_PATH, 'verifier/verify_reproducibility.py', used)
    require(sha256(files['verifier/verify_reproducibility.py']) == VERIFIER_SHA256, 'verifier bytes differ from supported pin')
    return used


def _candidate_files(files, core, expected):
    identity, used = expected.value, set()
    candidates = {c['framework']: c for c in identity['candidates']}
    names = sorted(candidates)
    original_receipts = {RECEIPTS[0]: core[CORE[0]][RECEIPTS[0]], RECEIPTS[1]: core[CORE[0]][RECEIPTS[1]],
                         RECEIPTS[2]: core[CORE[2]][RECEIPTS[2]]}
    for name, candidate in candidates.items():
        prefix = f'candidates/{name}/'

        def raw(path):
            key = prefix + path
            require(key in files, 'candidate material missing: ' + key)
            used.add(key)
            return files[key]

        def read(path):
            return document(raw(path))

        validated = read('validated-index.json')
        require(validated['digest'] == candidate['digest'] and validated['platforms'] == candidate['platforms'],
                'candidate differs from externally expected digests')
        publication = read('publication-evidence.json')
        require(publication == verify_publication(validated, raw('published.digest').decode().strip(),
                    raw('published-index.json'), f'{identity["source_registry"]}/image-base-{name}@{candidate["digest"]}'),
                'publication evidence differs')
        source = read('candidate-identity.json')
        positive(source['run_id'], 'candidate run')
        positive(source['attempt'], 'candidate attempt')
        require(source['run_id'] == identity['run_id'] and source['attempt'] == identity['run_attempt']
                and source['source_sha'] == identity['source_sha'] and source['digest'] == candidate['digest'],
                'candidate source identity differs')
        build = read('build-inputs.json')
        require(build['revision'] == identity['source_sha'] and build['annotations']['revision'] == identity['source_sha']
                and build['annotations']['source'] == 'https://github.com/' + identity['repository']
                and sha256(raw('apko.lock.json')) == build['lock_sha256'], 'candidate build input binding differs')
        gate = read('runtime-gate-result.json')
        positive(gate['run_attempt'], 'runtime attempt')
        require(all(gate.get(k) == v for k, v in publication_contract(name, names).items())
                and gate['passed'] is True and str(gate['run_id']) == str(identity['run_id'])
                and gate['run_attempt'] == identity['run_attempt'] and gate['revision'] == identity['source_sha']
                and gate['repository'] == identity['repository'], 'runtime gate identity differs')
        runtime, dev = candidates[gate['runtime_framework']], candidates.get(gate['dev_framework'])
        require(gate['index_digest'] == runtime['digest'] and gate['platforms'] == runtime['platforms']
                and gate['dev_index_digest'] == (dev['digest'] if dev else None)
                and gate['dev_platforms'] == (dev['platforms'] if dev else None), 'runtime pair digest differs')
        attested = json_value(raw('sbom-publication.json'))
        records = validated['sboms']
        require(type(records) is list and len(records) == 3 and type(attested) is list and len(attested) == 3
                and {r['subject'] for r in records} == {candidate['digest'], *candidate['platforms'].values()},
                'SBOM subjects differ')
        for record in records:
            require(record['path'] in ('sbom/sbom-index.spdx.json', 'sbom/sbom-x86_64.spdx.json',
                                      'sbom/sbom-aarch64.spdx.json'), 'SBOM path differs')
            sbom = raw(record['path'])
            require(sha256(sbom) == record['sha256'], 'original SBOM bytes differ')
            item = dict(record, image_ref=publication['image_ref'].split('@')[0] + '@' + record['subject'], attested=True)
            require(item in attested, 'SBOM publication binding differs')
            envelope = json_value(raw('trust/' + record['subject'][7:] + '-spdx.json'))
            envelopes = [envelope] if type(envelope) is dict else envelope
            require(type(envelopes) is list and envelopes, 'SPDX verification material missing')
            statements = [document(base64.b64decode(e['payload'], validate=True)) for e in envelopes]
            require(any(s.get('predicateType') == 'https://spdx.dev/Document'
                        and s.get('predicate') == document(sbom)
                        and any(x.get('digest', {}).get('sha256') == record['subject'][7:] for x in s.get('subject', []))
                        for s in statements), 'preserved SPDX subject/predicate differs')
        signature = json_value(raw('trust/signature.json'))
        require(type(signature) is list and signature, 'image signature material missing')
        provenance = json_value(raw('trust/provenance.json'))
        invocation = f'https://github.com/{identity["repository"]}/actions/runs/{identity["run_id"]}/attempts/{identity["run_attempt"]}'
        require(type(provenance) is list and any(
            entry.get('verificationResult', {}).get('statement', {}).get('predicate', {}).get('runDetails', {})
            .get('metadata', {}).get('invocationId') == invocation
            and any(s.get('digest', {}).get('sha256') == candidate['digest'][7:]
                    for s in entry.get('verificationResult', {}).get('statement', {}).get('subject', []))
            for entry in provenance), 'provenance subject/run binding differs')
        for location in ('validated', 'sbom'):
            for receipt, original in original_receipts.items():
                require(raw(f'receipts/{location}/{receipt}') == original, 'propagated receipt bytes differ')
    return used


def _role(path):
    if path == 'acquisition/context.json':
        return 'acquisition'
    if path.startswith(('git/source/', 'source/')):
        return 'source'
    if path.startswith(('git/reusable/', 'verifier/')):
        return 'verifier'
    if path.startswith('release/'):
        return 'release'
    if path.startswith('candidates/'):
        return 'cryptographic' if '/trust/' in path else 'candidate'
    raise InvalidEvidence('unsupported material role')


def _origins(records, files, context, artifacts, expected):
    require(type(records) is list and [r.get('path') for r in records] == sorted(files), 'material origin set/order differs')
    candidates = {c['framework']: c for c in context['candidates']}
    identity = expected.value
    for record in records:
        fields(record, 'path role origin', 'material')
        path, origin = record['path'], record['origin']
        require(record['role'] == _role(path), 'material role differs')
        if path == 'acquisition/context.json':
            fields(origin, 'kind locator', 'external origin')
            require(origin['kind'] == 'external-snapshot' and type(origin['locator']) is str and origin['locator'],
                    'external acquisition origin missing')
        elif path.startswith(('git/', 'source/', 'verifier/')):
            fields(origin, 'kind repository commit path', 'Git origin')
            repository, revision = ((identity['repository'], identity['source_sha']) if path.startswith(('git/source/', 'source/'))
                                    else (VERIFIER_REPOSITORY, VERIFIER_COMMIT))
            require(origin['kind'] == 'git' and origin['repository'] == repository and origin['commit'] == revision
                    and type(origin['path']) is str and origin['path'], 'Git material origin differs')
            if path.startswith('source/'):
                require(origin['path'] == path[len('source/'):], 'source origin path differs')
            if path.startswith('verifier/'):
                require(origin['path'] == VERIFIER_PATH, 'verifier origin path differs')
        elif path.startswith('release/store-'):
            fields(origin, 'kind bucket key version_id', 'S3 acquisition origin')
            kind = 'candidate' if path.endswith('candidate.json') else 'manifest'
            require(origin['kind'] == 's3' and type(origin['bucket']) is str and origin['bucket']
                    and origin['key'] == f'releases/{identity["release_id"]}/{kind}.json'
                    and type(origin['version_id']) is str and origin['version_id'], 'release object origin differs')
        else:
            fields(origin, 'kind artifact_id member source_zip_sha256 zip_preserved', 'selected artifact origin')
            require(origin['kind'] == 'github-artifact' and origin['artifact_id'] in artifacts
                    and origin['zip_preserved'] is False, 'selected artifact origin differs')
            artifact = artifacts[origin['artifact_id']]
            safe_path(origin['member'])
            require(origin['source_zip_sha256'] == artifact['sha256'] and not artifact['zip_preserved'],
                    'source ZIP digest boundary differs')
            if path.startswith('candidates/'):
                _, framework, member = path.split('/', 2)
                candidate = candidates[framework]
                if member.startswith('receipts/'):
                    _, location, receipt = member.split('/')
                    source_id = candidate[location + '_artifact_id']
                    expected_member = receipt
                elif member.startswith('trust/'):
                    source_id = candidate['trust_artifact_id']
                    expected_member = f'trust/{framework}/' + member[len('trust/'):]
                else:
                    source_id = candidate['publication_artifact_id']
                    expected_member = ('image.oci/' + member if member in ('validated-index.json', 'build-inputs.json', 'apko.lock.json')
                                       or member.startswith('sbom/') else member)
                require(origin['artifact_id'] == source_id and origin['member'] == expected_member,
                        'selected file/producer binding differs')
            else:
                require(origin['artifact_id'] in {c['trust_artifact_id'] for c in candidates.values()}
                        and origin['member'] == ('validated-candidate.json' if path.endswith('candidate.json') else 'release-manifest.json'),
                        'release artifact member differs')


def _release_files(files, expected):
    identity, used = expected.value, set()
    permitted = {'release/store-candidate.json', 'release/artifact-candidate.json',
                 'release/store-manifest.json', 'release/artifact-manifest.json'}
    for path in files:
        if not path.startswith('release/'):
            continue
        require(path in permitted, 'unsupported release material')
        value = document(files[path])
        validate_release_manifest(value)
        positive(value['run_id'], 'release run')
        positive(value['attempt'], 'release attempt')
        require(type(value.get('schema_version')) is int and value['schema_version'] == 1
                and value['repository'] == identity['repository'] and value['release_id'] == identity['release_id']
                and value['run_id'] == identity['run_id'] and value['attempt'] == identity['run_attempt']
                and value['source_sha'] == identity['source_sha'] and value['branch'] == 'develop', 'release document identity differs')
        require(value['source_registry'] == identity['source_registry'], 'release source registry differs')
        require(set(value['images']) == {c['framework'] for c in identity['candidates']}, 'release candidate set differs')
        for candidate in identity['candidates']:
            image = value['images'][candidate['framework']]
            require(image['digest'] == candidate['digest'] and image['platforms'] == candidate['platforms'],
                    'release document digests differ')
            prefix = f'candidates/{candidate["framework"]}/'
            require(image['tag'] == document(files[prefix + 'candidate-identity.json'])['tag'], 'release candidate tag differs')
            validated = document(files[prefix + 'validated-index.json'])
            sboms = [dict(subject=record['subject'], predicate_digest=checksum(document(files[prefix + record['path']])))
                     for record in validated['sboms']]
            require(image['sboms'] == sboms, 'release SPDX predicate binding differs')
        used.add(path)
    return used


def _plan_header(plan, expected):
    fields(plan, 'schema_version kind identity acquisition producers inventory core_archives materials verifier policy limitations',
           'custody plan')
    require(type(plan['schema_version']) is int and plan['schema_version'] == 1 and plan['kind'] == 'hgc04-custody',
            'unsupported custody schema')
    require(plan['identity'] == expected.value and canonical(plan['identity']) == expected.raw, 'external custody identity differs')
    require(plan['acquisition'] == 'acquisition/context.json' and plan['limitations'] == LIMITATIONS, 'custody scope differs')
    fields(plan['policy'], 'id profile limits', 'custody policy')
    require(type(plan['policy']['id']) is str and plan['policy']['id'] and plan['policy']['profile'] == 'TEST_ONLY'
            and plan['policy']['limits'] == LIMITS, 'unsupported custody policy/limits')
    fields(plan['verifier'], 'repository commit path payload_path sha256', 'verifier')
    require(plan['verifier'] == dict(repository=VERIFIER_REPOSITORY, commit=VERIFIER_COMMIT, path=VERIFIER_PATH,
                payload_path='verifier/verify_reproducibility.py', sha256=VERIFIER_SHA256), 'verifier identity differs')


def _inspect(data, plan, expected):
    _plan_header(plan, expected)
    budget = ExpansionBudget()
    files = read_zip(data, budget=budget, custody=True)
    check_inventory(plan['inventory'], files)
    require('acquisition/context.json' in files, 'external acquisition missing')
    context, jobs, artifacts = _acquisition(files['acquisition/context.json'], expected)
    require(plan['producers'] == {name: dict(artifact=artifacts[p['artifact_id']], job=jobs[p['job_id']])
                                 for name, p in context['producers'].items()}, 'manifest producer bindings differ')
    fields(plan['core_archives'], ' '.join(CORE), 'original ZIP set')
    core = {}
    originals = set()
    for name in CORE:
        record = plan['core_archives'][name]
        fields(record, 'path size sha256 members', 'original ZIP')
        path = f'originals/{name}.zip'
        require(record['path'] == path and path in files, 'original ZIP path differs')
        originals.add(path)
        raw = files[path]
        artifact = artifacts[context['producers'][name]['artifact_id']]
        require(type(record['size']) is int and len(raw) == record['size'] == artifact['size']
                and sha256(raw) == record['sha256'] == artifact['sha256'], 'original ZIP digest/size differs from acquisition')
        core[name] = read_zip(raw, budget=budget)
        check_inventory(record['members'], core[name])
    materials = {path: raw for path, raw in files.items() if path not in originals}
    _origins(plan['materials'], materials, context, artifacts, expected)
    environment = _core_sets(core, context, jobs, expected)
    required = {'acquisition/context.json'} | _source(materials, environment, context, expected)
    required |= _candidate_files(materials, core, expected) | _release_files(materials, expected)
    require(set(materials) == required, 'additional material exact set differs')
    return files, core, context


@dataclass(frozen=True)
class PreparedPayload:
    data: bytes
    plan: bytes


def prepare_payload(core_zips, materials, origins, expected, policy_id):
    require(isinstance(expected, ExpectedIdentity), 'external identity required')
    require(type(core_zips) is dict and set(core_zips) == set(CORE) and type(materials) is dict
            and type(origins) is dict and set(origins) == set(materials), 'input/origin sets differ')
    context, jobs, artifacts = _acquisition(materials['acquisition/context.json'], expected)
    files = dict(materials)
    for name, raw in core_zips.items():
        path = f'originals/{name}.zip'
        require(path not in files, 'original ZIP path collision')
        files[path] = raw
    data = make_zip(files)
    plan = dict(schema_version=1, kind='hgc04-custody', identity=expected.value, acquisition='acquisition/context.json',
        producers={name: dict(artifact=artifacts[p['artifact_id']], job=jobs[p['job_id']]) for name, p in context['producers'].items()},
        inventory=inventory(files), core_archives={name: dict(path=f'originals/{name}.zip', size=len(raw), sha256=sha256(raw),
            members=inventory(read_zip(raw))) for name, raw in core_zips.items()},
        materials=[dict(path=path, role=_role(path), origin=origins[path]) for path in sorted(materials)],
        verifier=dict(repository=VERIFIER_REPOSITORY, commit=VERIFIER_COMMIT, path=VERIFIER_PATH,
                      payload_path='verifier/verify_reproducibility.py', sha256=VERIFIER_SHA256),
        policy=dict(id=policy_id, profile='TEST_ONLY', limits=LIMITS), limitations=LIMITATIONS)
    _inspect(data, plan, expected)
    return PreparedPayload(data, canonical(plan))


def object_content(raw, kind):
    return FrozenObject.freeze(raw, dict(kind=kind, schema_version='1', sha256=sha256(raw)))


def payload_key(expected, raw):
    return expected.prefix + 'payload/' + sha256(raw) + '.zip'


def store_payload(store, prepared, expected):
    _inspect(prepared.data, document(prepared.plan), expected)
    return store.create_once(payload_key(expected, prepared.data), object_content(prepared.data, 'hgc04-payload'))


def manifest_bytes(prepared, stored_payload, expected):
    plan = document(prepared.plan)
    _inspect(prepared.data, plan, expected)
    require(stored_payload.content == object_content(prepared.data, 'hgc04-payload'), 'confirmed payload bytes/metadata differ')
    plan['payload'] = dict(key=payload_key(expected, prepared.data), size=len(prepared.data), sha256=sha256(prepared.data),
                           version_id=stored_payload.version_id)
    return canonical(plan)


def _manifest(raw, expected):
    value = document(raw)
    require(canonical(value) == raw, 'new custody manifest is not canonical')
    require('payload' in value, 'payload reference missing')
    payload = value.pop('payload')
    fields(payload, 'key size sha256 version_id', 'payload reference')
    digest(payload['sha256'])
    require(payload['key'] == expected.prefix + 'payload/' + payload['sha256'] + '.zip', 'payload location differs from expected identity')
    require(type(payload['size']) is int and 0 < payload['size'] <= LIMITS['archive_bytes']
            and type(payload['version_id']) is str and payload['version_id'], 'invalid payload size/version')
    _plan_header(value, expected)
    return value, payload


def _encoded(raw):
    return dict(encoding='base64', size=len(raw), sha256=sha256(raw), data=base64.b64encode(raw).decode('ascii'))


def _decoded(value):
    fields(value, 'encoding size sha256 data', 'encoded bytes')
    require(value['encoding'] == 'base64' and type(value['data']) is str and type(value['size']) is int
            and 0 < value['size'] <= LIMITS['json_bytes'], 'invalid byte envelope')
    digest(value['sha256'])
    try:
        raw = base64.b64decode(value['data'], validate=True)
    except ValueError as error:
        raise InvalidEvidence('invalid base64 envelope') from error
    require(_encoded(raw) == value, 'encoded byte size/hash/representation differs')
    return raw


@dataclass(frozen=True)
class FrozenCommit:
    content: FrozenObject

    @property
    def sha256(self):
        return sha256(self.content.data)


def freeze_commit(manifest, bundle, policy, expected, authenticator):
    _manifest(manifest, expected)
    authenticate(manifest, bundle, policy, expected, authenticator)
    envelope = canonical(dict(schema_version=1, kind='hgc04-commit', manifest=_encoded(manifest), bundle=_encoded(bundle)))
    require(len(envelope) <= LIMITS['json_bytes'], 'commit envelope size limit')
    return FrozenCommit(object_content(envelope, 'hgc04-commit'))


def inspect_commit(raw, expected):
    """Structural/integrity inspection only. Does not approve origin or run code."""
    value = document(raw)
    fields(value, 'schema_version kind manifest bundle', 'commit envelope')
    require(type(value['schema_version']) is int and value['schema_version'] == 1 and value['kind'] == 'hgc04-commit'
            and canonical(value) == raw, 'unsupported/noncanonical commit envelope')
    manifest, bundle = _decoded(value['manifest']), _decoded(value['bundle'])
    plan, payload = _manifest(manifest, expected)
    return manifest, bundle, plan, payload


class CustodyState(str, Enum):
    LEGACY_NO_CUSTODY = 'LEGACY_NO_CUSTODY'
    COMPLETE_VERIFIED = 'COMPLETE_VERIFIED'
    PARTIAL = 'PARTIAL'
    INVALID = 'INVALID'
    REQUIRED_MISSING = 'REQUIRED_MISSING'
    ERROR = 'ERROR'
    ADOPTION_UNKNOWN = 'ADOPTION_UNKNOWN'


@dataclass(frozen=True)
class AdoptionPolicy:
    required: frozenset
    legacy: frozenset

    def __post_init__(self):
        require(type(self.required) is frozenset and type(self.legacy) is frozenset and not self.required & self.legacy,
                'external adoption sets must be immutable and disjoint')
        require(all(type(key) is str and re.fullmatch(r'[1-9][0-9]*/r[1-9][0-9]*-a[1-9][0-9]*', key)
                    for key in self.required | self.legacy), 'invalid adoption identity')


@dataclass(frozen=True)
class CustodyRead:
    state: CustodyState
    reason: str = ''
    profile: str = 'UNAUTHENTICATED'
    production_authority: bool = False
    report: object = None


def _readback(files, core, context, expected, policy, target):
    policy.verifier.validate()
    script = files['verifier/verify_reproducibility.py']
    require(sha256(script) == policy.verifier.sha256, 'verifier not externally authorized')
    root = extract_new({}, Path(target))
    extracted = root / 'extracted'
    extracted.mkdir(mode=0o700)
    for name in CORE:
        extract_new(core[name], extracted / name)
    tools = root / 'tools'
    tools.mkdir(mode=0o700)
    script_path = tools / 'verify_reproducibility.py'
    script_path.write_bytes(script)
    identity = expected.value
    args = [sys.executable, '-I', '-B', str(script_path), '--melange-repo', str(extracted / CORE[0]),
            '--reference', str(extracted / CORE[1]), '--reproducibility', str(extracted / CORE[2]),
            '--repository', identity['repository'], '--run-id', str(identity['run_id']),
            '--run-attempt', str(identity['run_attempt']), '--source-sha', identity['source_sha'], '--ref', identity['ref']]
    reports = root / 'reports'
    reports.mkdir(mode=0o700)
    completed = subprocess.run(args, capture_output=True, timeout=120, cwd=str(root),
        env={'PATH': os.environ.get('PATH', os.defpath), 'LANG': 'C', 'PYTHONNOUSERSITE': '1'})
    (reports / 'stdout').write_bytes(completed.stdout)
    (reports / 'stderr').write_bytes(completed.stderr)
    (reports / 'exit-code').write_text(str(completed.returncode) + '\n')
    require(completed.returncode == 0, 'HGC-03 verifier exit ' + str(completed.returncode))
    report = document(completed.stdout)
    evidence = document(core[CORE[2]]['melange-reproducibility-evidence.json'])
    require(report.get('result') == 'READBACK_VERIFIED' and report.get('build_date') == context['build_date']
            and report.get('reproduction_input_digest') == evidence['reproduction_input_digest']
            and report.get('evidence_sha256') == sha256(core[CORE[2]]['melange-reproducibility-evidence.json']),
            'HGC-03 read-back result/bindings differ')
    return report


def _verify_payload(store, raw, expected, policy, authenticator, target):
    manifest, bundle, plan, payload = inspect_commit(raw, expected)
    authenticate(manifest, bundle, policy, expected, authenticator)
    require(plan.get('policy', {}).get('id') == policy.policy_id, 'external policy identity differs')
    result = store.get(payload['key'], version_id=payload['version_id'])
    if result.status == ReadStatus.ERROR:
        return CustodyRead(CustodyState.ERROR, result.reason, profile=policy.profile)
    require(result.status == ReadStatus.FOUND, 'committed payload version missing')
    data = result.object.content.data
    require(result.object.content == object_content(data, 'hgc04-payload') and len(data) == payload['size']
            and sha256(data) == payload['sha256'], 'committed payload bytes/metadata differ')
    files, core, context = _inspect(data, plan, expected)
    report = _readback(files, core, context, expected, policy, target)
    return CustodyRead(CustodyState.COMPLETE_VERIFIED, profile=policy.profile, report=report)


def recover(store, expected, policy, authenticator, target, *, adoption=None):
    """Read durable transport only. No GitHub, build or scratch fallback exists."""
    try:
        require(isinstance(expected, ExpectedIdentity), 'external identity required')
        result = store.get(expected.prefix + 'commit.json')
        if result.status == ReadStatus.ERROR:
            return CustodyRead(CustodyState.ERROR, result.reason)
        if result.status == ReadStatus.MISSING:
            listed = store.keys(expected.prefix + 'payload/')
            if listed.status == ReadStatus.ERROR:
                return CustodyRead(CustodyState.ERROR, listed.reason)
            if listed.keys:
                return CustodyRead(CustodyState.PARTIAL, 'payload exists without commit')
            if adoption is None:
                return CustodyRead(CustodyState.ADOPTION_UNKNOWN, 'external adoption policy not provided')
            key = f'{expected.value["repository_id"]}/{expected.value["release_id"]}'
            if key in adoption.legacy:
                return CustodyRead(CustodyState.LEGACY_NO_CUSTODY, 'explicit external legacy classification')
            if key in adoption.required:
                return CustodyRead(CustodyState.REQUIRED_MISSING, 'expected custody absent')
            return CustodyRead(CustodyState.ADOPTION_UNKNOWN, 'release not classified by external adoption policy')
        require(result.object.content == object_content(result.object.content.data, 'hgc04-commit'), 'commit application metadata differs')
        return _verify_payload(store, result.object.content.data, expected, policy, authenticator, target)
    except (InvalidEvidence, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        return CustodyRead(CustodyState.INVALID, str(error))
    except (OSError, subprocess.SubprocessError) as error:
        return CustodyRead(CustodyState.ERROR, str(error))


def commit_record(store, frozen, expected, policy, authenticator, work_root):
    """Finalize frozen bytes. Recover existing commit before considering writes.

    The work_root must be a new directory in a private caller-owned parent.
    No signer is invoked here, so retries cannot regenerate a signature.
    """
    try:
        require(isinstance(frozen, FrozenCommit), 'frozen commit required')
        current = store.get(expected.prefix + 'commit.json')
        if current.status == ReadStatus.ERROR:
            return WriteResult(WriteStatus.ERROR, reason=current.reason)
        if current.status == ReadStatus.FOUND:
            # Authenticate/recover even on a conflicting request; no writes.
            read = recover(store, expected, policy, authenticator, Path(work_root))
            if read.state != CustodyState.COMPLETE_VERIFIED:
                return WriteResult(WriteStatus.ERROR, reason='existing commit is not verified: ' + read.reason)
            return WriteResult(WriteStatus.ALREADY_PRESENT_IDENTICAL if current.object.content == frozen.content
                               else WriteStatus.CONFLICT, current.object)
        root = extract_new({}, Path(work_root))
        before = _verify_payload(store, frozen.content.data, expected, policy, authenticator, root / 'before-commit')
        if before.state != CustodyState.COMPLETE_VERIFIED:
            return WriteResult(WriteStatus.ERROR, reason=before.reason)
        require(frozen.content == object_content(frozen.content.data, 'hgc04-commit'), 'frozen commit metadata differs')
        result = store.create_once(expected.prefix + 'commit.json', frozen.content)
        if result.status not in (WriteStatus.CREATED, WriteStatus.ALREADY_PRESENT_IDENTICAL):
            return result
        after = recover(store, expected, policy, authenticator, root / 'after-commit')
        if after.state != CustodyState.COMPLETE_VERIFIED:
            return WriteResult(WriteStatus.ERROR, result.object, 'final record read-back failed: ' + after.reason)
        return result
    except (InvalidEvidence, ValueError, KeyError, TypeError, AttributeError, OSError, subprocess.SubprocessError) as error:
        return WriteResult(WriteStatus.ERROR, reason=str(error))
