"""Selected existing historical bytes, never production acquisition/authentication."""
import argparse
import json
from pathlib import Path
import zipfile

from scripts.pipeline.analytics.spdx import canonical, sha256

ROOT = Path(__file__).resolve().parents[4]
SOURCES = ROOT / 'tests/fixtures/sbom-analytics/sources.json'


def historical(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sources = json.loads(SOURCES.read_bytes())
    archive = (ROOT / sources['source_zip']).read_bytes()
    assert sha256(archive) == sources['source_zip_sha256']
    external = json.loads((ROOT / 'tests/fixtures/hgc04/expected.json').read_bytes())
    images = []
    with zipfile.ZipFile(ROOT / sources['source_zip']) as z:
        acquisition = json.loads(z.read('acquisition/context.json'))
        for expected in external['candidates']:
            framework = expected['framework']
            prefix = 'candidates/' + framework + '/'
            documents = []
            for source in sources['members']:
                if source['member'].startswith(prefix):
                    raw = z.read(source['member'])
                    assert sha256(raw) == source['sha256'] and len(raw) == source['size']
                    local = directory / source['member']
                    local.parent.mkdir(parents=True, exist_ok=True)
                    local.write_bytes(raw)
                    name = local.name
                    platform = {'sbom-index.spdx.json': None, 'sbom-x86_64.spdx.json': 'linux/amd64',
                                'sbom-aarch64.spdx.json': 'linux/arm64'}[name]
                    documents.append(dict(path=str(local), sbom_scope='index' if platform is None else 'platform',
                        document_platform=platform, sha256=source['sha256'], artifact_id=source['artifact_id'],
                        source_path='sbom/' + name))
            records = {}
            for name in ('validated-index.json', 'publication-evidence.json', 'published-index.json', 'candidate-identity.json'):
                local = directory / prefix / name
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(z.read(prefix + name))
                records[name] = str(local)
            reference = f'https://github.com/{sources["repository"]}/actions/runs/{sources["run_id"]}'
            images.append(dict(framework=framework,
                image_repository=external['source_registry'] + '/image-base-' + framework,
                image_index_digest=expected['digest'], platforms=expected['platforms'], documents=documents,
                validation=dict(path=records['validated-index.json'], reference=reference + '#validated-oci-' + framework),
                publication=dict(path=records['publication-evidence.json'], remote_index_path=records['published-index.json'],
                                 reference=reference + '#publication-' + framework + '-1'),
                candidate_identity=dict(path=records['candidate-identity.json'], reference=reference + '#candidate-' + framework),
                hosted_verification=dict(status='REPORTED_SUCCESS', reference=reference + '#release-dev-1')))
    origin = {k: sources[k] for k in ('repository', 'run_id', 'run_attempt', 'source_sha')}
    origin.update(event='push', ref='refs/heads/develop', source_timestamp=acquisition['build_date'],
                  source_timestamp_origin='Historical Git committer date (%cI), curated acquisition/context.json')
    return dict(schema_version=1, origin=origin, images=images)


def synthetic(directory, *, framework='python-3.14'):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    subjects = {k: 'sha256:' + sha256(k.encode()) for k in ('index', 'linux/amd64', 'linux/arm64')}
    inputs = []
    for key, subject in subjects.items():
        value = dict(spdxVersion='SPDX-2.3', SPDXID='SPDXRef-DOCUMENT',
            documentNamespace='https://example.invalid/spdx/repeated-namespace', documentDescribes=['SPDXRef-image'],
            packages=[dict(SPDXID='SPDXRef-image', name='container', checksums=[dict(algorithm='SHA256', checksumValue=subject[7:])]),
                      dict(SPDXID='SPDXRef-one', name='same-name', versionInfo='1+test'),
                      dict(SPDXID='SPDXRef-two', name='same-name', versionInfo='1+test')])
        path = directory / (key.replace('/', '-') + '.json')
        path.write_bytes(canonical(value))
        inputs.append(dict(path=str(path), sbom_scope='index' if key == 'index' else 'platform',
                           document_platform=None if key == 'index' else key))
    return dict(schema_version=1, origin=dict(repository='example/factory', run_id=17, run_attempt=1,
        source_sha='a'*40, event='push', ref='refs/heads/develop'), images=[dict(framework=framework,
        image_repository='example.invalid/image-base-' + framework, image_index_digest=subjects['index'],
        platforms={k:v for k,v in subjects.items() if k != 'index'}, documents=inputs)])


def mutate_spdx(context, transform, *, image=0, document=0):
    item = context['images'][image]['documents'][document]
    path = Path(item['path'])
    value = json.loads(path.read_bytes())
    transform(value)
    raw = canonical(value)
    path.write_bytes(raw)
    if 'sha256' in item:
        item['sha256'] = sha256(raw)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = historical(args.output.resolve())
    path = args.output.resolve() / 'context.json'
    path.write_bytes(canonical(result))
    print(path)
