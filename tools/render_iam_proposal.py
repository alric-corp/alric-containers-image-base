"""Render local P1-04 review documents; no AWS client or policy application."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / 'policies/aws/proposals/factory-permissions'
TEMPLATES = ('execution.identity', 'provisioning.identity', 'trust')
PARAMETERS = {'AWS_ACCOUNT_ID', 'AWS_REGION', 'ECR_REPOSITORIES',
              'GITHUB_REPOSITORY', 'GITHUB_REPOSITORY_ID', 'GITHUB_OWNER_ID', 'GITHUB_SUB'}


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def render(parameters, directory=PROPOSAL):
    """Only parameter validation/substitution, never IAM authorization simulation."""
    if not isinstance(parameters, dict) or set(parameters) != PARAMETERS:
        raise ValueError('expected exactly the documented parameters')
    patterns = {
        'AWS_ACCOUNT_ID': r'[0-9]{12}',
        'AWS_REGION': r'[a-z]{2}-[a-z]+-[0-9]+',
        'GITHUB_REPOSITORY': r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',
        'GITHUB_REPOSITORY_ID': r'[1-9][0-9]*',
        'GITHUB_OWNER_ID': r'[1-9][0-9]*',
    }
    for key, pattern in patterns.items():
        if not isinstance(parameters[key], str) or not re.fullmatch(pattern, parameters[key]):
            raise ValueError(f'invalid {key}')
    if parameters['AWS_REGION'].startswith('cn-'):
        raise ValueError('proposal is limited to the commercial aws partition')
    repos = parameters['ECR_REPOSITORIES']
    if (not isinstance(repos, list) or not repos
            or any(not isinstance(repo, str) or not re.fullmatch(
                r'image-base-[a-z0-9]+(?:-[a-z0-9]+)*', repo) for repo in repos)
            or len(repos) != len(set(repos))):
        raise ValueError('expected a nonempty, unique list of exact image-base repository names')
    owner, repo = parameters['GITHUB_REPOSITORY'].split('/')
    subjects = {
        f'repo:{owner}/{repo}:ref:refs/heads/main',
        f'repo:{owner}@{parameters["GITHUB_OWNER_ID"]}/{repo}@{parameters["GITHUB_REPOSITORY_ID"]}:ref:refs/heads/main',
    }
    if not isinstance(parameters['GITHUB_SUB'], str) or parameters['GITHUB_SUB'] not in subjects:
        raise ValueError('sub must be the confirmed exact main subject for these names/IDs')
    account, region = parameters['AWS_ACCOUNT_ID'], parameters['AWS_REGION']
    values = dict(parameters,
                  ECR_REPOSITORY_ARNS=[f'arn:aws:ecr:{region}:{account}:repository/{r}'
                                       for r in sorted(repos)],
                  OIDC_PROVIDER_ARN=f'arn:aws:iam::{account}:oidc-provider/token.actions.githubusercontent.com')

    def substitute(value):
        if isinstance(value, dict):
            return {k: substitute(v) for k, v in value.items()}
        if isinstance(value, list):
            return [substitute(v) for v in value]
        if isinstance(value, str) and '${' in value:
            match = re.fullmatch(r'\$\{([A-Z_]+)\}', value)
            if not match or match[1] not in values:
                raise ValueError(f'unknown or embedded placeholder: {value}')
            return values[match[1]]
        return value

    return {name + '.json': substitute(read_json(directory / (name + '.template.json')))
            for name in TEMPLATES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parameters', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True,
                        help='new directory outside this checkout; never overwritten')
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        if output == ROOT or ROOT in output.parents:
            raise ValueError('output must be outside the repository')
        documents = render(read_json(args.parameters))
        output.mkdir(parents=True, exist_ok=False)
        for name, document in documents.items():
            (output / name).write_text(json.dumps(document, indent=2) + '\n')
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    print('Rendered local proposal only; no AWS validation, simulation or application.')


if __name__ == '__main__':
    main()
