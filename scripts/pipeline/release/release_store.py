"""Durable release records; missing objects differ from denied/failed reads."""
import json
from pathlib import Path
import subprocess
import tempfile

from scripts.pipeline.consumer_apps.inventory import json_document, require
from scripts.pipeline.release.release_manifest import canonical, configuration


def command(*args, timeout=300):
    return subprocess.run(args, check=True, capture_output=True, timeout=timeout).stdout


class Store:
    def __init__(self, environment):
        cfg = configuration()[environment]
        self.bucket, self.region = cfg['release_bucket'], cfg['region']

    def aws(self, operation, *args):
        return command('aws', 's3api', operation, '--bucket', self.bucket,
                       '--region', self.region, '--no-cli-pager', *args)

    def get(self, key, optional=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'object.json'
            try:
                self.aws('get-object', '--key', key, str(path))
            except subprocess.CalledProcessError as error:
                if optional and b'(NoSuchKey)' in (error.stderr or b''):
                    return None
                raise
            return json_document(path.read_bytes())

    def put(self, key, document, immutable=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'object.json'
            path.write_bytes(canonical(document))
            flags = ('--if-none-match', '*') if immutable else ()
            try:
                self.aws('put-object', '--key', key, '--body', str(path),
                         '--content-type', 'application/json', *flags)
            except subprocess.CalledProcessError as error:
                if not immutable or b'(PreconditionFailed)' not in (error.stderr or b''):
                    raise
                require(self.get(key) == document, 'immutable release record already exists with different content')

    def keys(self, prefix):
        # AWS CLI combines service pages. Never accept an explicit pagination token.
        result = json_document(self.aws('list-objects-v2', '--prefix', prefix, '--output', 'json'))
        require(not result.get('NextToken') and not result.get('NextContinuationToken')
                and not result.get('IsTruncated'), 'incomplete release inventory')
        return [item['Key'] for item in result.get('Contents', [])]
