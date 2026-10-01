"""Bind a release to one build run/attempt and its validated, published digests."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from scripts.pipeline.governance.configuration import configuration
from scripts.pipeline.consumer_apps.inventory import json_document, require
from scripts.pipeline.consumer_apps.model import CATALOG, SCENARIOS
from scripts.pipeline.release.verify_publication import verify_publication
from scripts.pipeline.runtime.runtime_images import publication_contract

ROOT = Path(__file__).resolve().parents[3]
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
RELEASE_ID = re.compile(r'r([1-9][0-9]*)-a([1-9][0-9]*)')


def registry(environment):
    cfg = configuration()[environment]
    return f'{cfg["account_id"]}.dkr.ecr.{cfg["region"]}.amazonaws.com'


def canonical(document):
    return json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def checksum(document):
    return 'sha256:' + hashlib.sha256(canonical(document)).hexdigest()


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.tzinfo is not None, 'release timestamp needs a timezone')
    return result.astimezone(timezone.utc)


def release_units(frameworks):
    require(isinstance(frameworks, list) and frameworks and all(isinstance(x, str) for x in frameworks)
            and len(frameworks) == len(set(frameworks)) and set(frameworks) <= set(CATALOG),
            'release must contain distinct catalog frameworks')
    units = []
    for scenario in SCENARIOS:
        pair = [scenario['framework']] + ([scenario['dev_framework']] if scenario['dev_framework'] else [])
        if set(pair) & set(frameworks):
            require(set(pair) <= set(frameworks), 'release requires a complete consumer runtime/dev pair')
            units.append(pair)
    return units


def validate(manifest):
    cfg = configuration()
    require(type(manifest.get('schema_version')) is int and manifest['schema_version'] == 1,
            'unsupported release manifest schema')
    run, attempt = manifest['run_id'], manifest['attempt']
    require(type(run) is int and run > 0 and type(attempt) is int and attempt > 0,
            'release requires positive run and attempt numbers')
    require(manifest['release_id'] == f'r{run}-a{attempt}', 'release ID mismatch')
    require(manifest['repository'] == cfg['repository'] and manifest['branch'] == cfg['branch']
            and manifest['source_registry'] == registry('DEV'), 'release source mismatch')
    require(re.fullmatch(r'[0-9a-f]{40}', manifest['source_sha']), 'invalid source revision')
    frameworks = sorted(manifest['images'])
    units = release_units(frameworks)
    require(manifest['units'] == units, 'release must contain complete runtime/dev units')
    for framework, item in manifest['images'].items():
        require(DIGEST.fullmatch(item['digest']) is not None, 'invalid image digest')
        require(set(item['platforms']) == {'linux/amd64', 'linux/arm64'}
                and all(DIGEST.fullmatch(d) for d in item['platforms'].values())
                and len(set(item['platforms'].values())) == 2, 'invalid platform digests')
        subjects = {item['digest'], *item['platforms'].values()}
        require(len(item['sboms']) == 3 and {s['subject'] for s in item['sboms']} == subjects
                and all(DIGEST.fullmatch(s['predicate_digest']) for s in item['sboms']),
                'release requires original SPDX evidence for index and both platforms')
        require(re.fullmatch(rf'[0-9]{{6}}-[0-9]{{4}}-r{run}-a{attempt}', item['tag']),
                f'{framework}: candidate tag must bind the exact run and attempt')
    return manifest


def from_publications(directory, frameworks, run_id, attempt, revision):
    """Read only integrity-checked artifacts from successful build-push jobs."""
    cfg = configuration()
    frameworks = sorted(frameworks)
    units = release_units(frameworks)
    run_id, attempt = int(run_id), int(attempt)
    result = dict(schema_version=1, release_id=f'r{run_id}-a{attempt}',
                  run_id=run_id, attempt=attempt, source_sha=revision,
                  repository=cfg['repository'], branch=cfg['branch'],
                  source_registry=registry('DEV'), units=units, images={})
    gates = {}
    for framework in frameworks:
        root = Path(directory) / f'publication-{framework}-{attempt}'
        read = lambda path: json_document((root / path).read_bytes())
        expected = read('image.oci/validated-index.json')
        image = f'{registry("DEV")}/image-base-{framework}@{expected["digest"]}'
        verified = verify_publication(expected, (root / 'published.digest').read_text().strip(),
                                      (root / 'published-index.json').read_bytes(), image)
        require(read('publication-evidence.json') == verified, 'publication evidence mismatch')
        build = read('image.oci/build-inputs.json')
        require(build['revision'] == revision and build['annotations']['revision'] == revision
                and build['annotations']['source'] == f'https://github.com/{cfg["repository"]}',
                'publication source revision mismatch')
        identity = read('candidate-identity.json')
        require(identity['run_id'] == run_id and identity['attempt'] == attempt
                and identity['source_sha'] == revision and identity['digest'] == expected['digest'],
                'candidate identity mismatch')
        gate = read('runtime-gate-result.json')
        require(all(gate.get(k) == v for k, v in publication_contract(framework, frameworks).items())
                and gate['passed'] is True and int(gate['run_id']) == run_id
                and int(gate['run_attempt']) == attempt and gate['revision'] == revision
                and gate['repository'] == cfg['repository'], 'functional gate mismatch')
        gates[framework] = gate
        sboms, attested = [], read('sbom-publication.json')
        require(len(attested) == len(expected['sboms']) == 3, 'missing SBOM attestations')
        for record in expected['sboms']:
            # Only canonical paths produced by apko can be read from the artifact.
            require(record['path'] in {'sbom/sbom-index.spdx.json', 'sbom/sbom-x86_64.spdx.json',
                                      'sbom/sbom-aarch64.spdx.json'}, 'invalid SBOM path')
            raw = (root / 'image.oci' / record['path']).read_bytes()
            require(hashlib.sha256(raw).hexdigest() == record['sha256'], 'SBOM changed after scan')
            require(dict(record, image_ref=image.split('@')[0] + '@' + record['subject'],
                         attested=True) in attested, 'SBOM publication not confirmed')
            sboms.append(dict(subject=record['subject'], predicate_digest=checksum(json_document(raw))))
        result['images'][framework] = dict(digest=expected['digest'], platforms=expected['platforms'],
                                           tag=identity['tag'], sboms=sboms)
    for framework, gate in gates.items():
        runtime = result['images'][gate['runtime_framework']]
        dev = result['images'].get(gate['dev_framework'])
        require(gate['index_digest'] == runtime['digest'] and gate['platforms'] == runtime['platforms']
                and gate['dev_index_digest'] == (dev['digest'] if dev else None)
                and gate['dev_platforms'] == (dev['platforms'] if dev else None),
                'runtime/dev evidence does not authorize the exact published pair')
    return validate(result)


def consumer_inventory(manifest):
    validate(manifest)
    return dict(schema_version=1, scope='release',
                source_run_id=manifest['run_id'], source_run_attempt=manifest['attempt'],
                source_sha=manifest['source_sha'],
                candidates={framework: dict(framework=framework, repository=f'image-base-{framework}',
                    digest=item['digest'], image_ref=f'{manifest["source_registry"]}/image-base-{framework}@{item["digest"]}',
                    immutable_tag=item['tag'], imagePushedAt='verified-at-publication',
                    platforms={key.removeprefix('linux/'): value for key, value in item['platforms'].items()})
                    for framework, item in manifest['images'].items()})
