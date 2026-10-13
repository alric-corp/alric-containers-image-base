"""Protection contract of the code branch (G02): offline lint, read-only verify.

`policies/governance/develop-protection.json` keeps two explicit profiles:
`lab`, the protection the owner accepted for the personal LAB, and
`corporate`, a proposal that nothing here applies. `lint` checks offline that
every required check is emitted on every pull request (a path-filtered check
would stay pending forever), that the corporate profile is never weaker than
the LAB one, that each Environment used by the workflows is declared and that
CODEOWNERS keeps privileged paths with an explicit owner. `verify` compares the
live GitHub settings with one profile through GET requests only; changing
Settings is an owner action outside this module.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

from scripts.pipeline.governance.configuration import configuration
from scripts.pipeline.governance.workflow_dependencies import document, local_workflows, unique_pairs

ROOT = Path(__file__).resolve().parents[3]
POLICY = Path('policies/governance/develop-protection.json')
TEMPLATE = Path('policies/governance/CODEOWNERS.template')
# GitHub only reads CODEOWNERS from these locations, in this order.
ACTIVE_CODEOWNERS = (Path('.github/CODEOWNERS'), Path('CODEOWNERS'), Path('docs/CODEOWNERS'))
# Pinning the app keeps a commit status from another integration from
# satisfying a required check with the same name.
GITHUB_ACTIONS_APP_ID = 15368
STATUSES = {'lab': {'OWNER_ACCEPTED_LAB_EXCEPTION'},
            'corporate': {'PROPOSED_AWAITING_APPROVAL', 'APPROVED'}}
PROTECTION_KEYS = {'required_status_checks', 'enforce_admins', 'required_pull_request_reviews',
                   'restrictions', 'required_linear_history', 'allow_force_pushes',
                   'allow_deletions', 'block_creations', 'required_conversation_resolution',
                   'lock_branch', 'allow_fork_syncing'}
REVIEW_KEYS = {'dismiss_stale_reviews', 'require_code_owner_reviews',
               'required_approving_review_count', 'require_last_push_approval'}
FLAGS = ('required_linear_history', 'allow_force_pushes', 'allow_deletions', 'block_creations',
         'required_conversation_resolution', 'lock_branch', 'allow_fork_syncing')
ENVIRONMENT_KEYS = {'branches', 'can_admins_bypass', 'required_reviewers'}
OPTIONAL_ENVIRONMENT_KEYS = {'prevent_self_review', 'reviewers'}
PLACEHOLDER = re.compile(r'@<[a-z0-9-]+>/<[a-z0-9-]+>')
SECURITY_OWNER = '@<org>/<security-reviewers>'
IAM_OWNER = '@<org>/<cloud-iam-reviewers>'
# Trust anchors whose change alters what the Factory accepts as authentic.
SECURITY_PATHS = ('melange/keys/', 'melange/certificates/',
                  'policies/release/signing-identities.json')
IAM_PATHS = ('policies/aws/', 'infra/iam/')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(root=ROOT):
    contract = json.loads((root / POLICY).read_text(), object_pairs_hook=unique_pairs)
    require(isinstance(contract, dict)
            and set(contract) - {'$comment'} == {'schema_version', 'repository', 'branch', 'profiles'},
            f'{POLICY}: unexpected top-level keys')
    require(type(contract['schema_version']) is int and contract['schema_version'] == 1,
            f'{POLICY}: unsupported schema')
    pipeline = configuration(root / 'policies/pipeline/config.json')
    require(contract['repository'] == pipeline['repository'] and contract['branch'] == pipeline['branch'],
            f'{POLICY}: repository/branch differ from policies/pipeline/config.json')
    profiles = contract['profiles']
    require(isinstance(profiles, dict) and set(profiles) == set(STATUSES),
            f'{POLICY}: profiles must be exactly lab and corporate')
    for name, profile in profiles.items():
        require(isinstance(profile, dict)
                and set(profile) == {'status', 'evidence', 'protection', 'environments'},
                f'{name}: unexpected profile keys')
        require(profile['status'] in STATUSES[name], f'{name}: status {profile["status"]!r} not allowed')
        require(isinstance(profile['evidence'], str) and profile['evidence'].strip(),
                f'{name}: evidence is required')
        protection = profile['protection']
        require(isinstance(protection, dict) and set(protection) == PROTECTION_KEYS,
                f'{name}: protection must use exactly the branch protection PUT body keys')
        checks = protection['required_status_checks']
        require(isinstance(checks, dict) and set(checks) == {'strict', 'checks'}
                and type(checks['strict']) is bool and isinstance(checks['checks'], list),
                f'{name}: invalid required_status_checks')
        for check in checks['checks']:
            require(isinstance(check, dict) and set(check) == {'context', 'app_id'}
                    and isinstance(check['context'], str) and check['context'].strip(),
                    f'{name}: invalid required check')
        require(len({check['context'] for check in checks['checks']}) == len(checks['checks']),
                f'{name}: duplicate required check')
        reviews = protection['required_pull_request_reviews']
        require(isinstance(reviews, dict) and set(reviews) == REVIEW_KEYS
                and type(reviews['required_approving_review_count']) is int
                and 0 <= reviews['required_approving_review_count'] <= 6
                and all(type(reviews[key]) is bool for key in REVIEW_KEYS
                        - {'required_approving_review_count'}),
                f'{name}: invalid required_pull_request_reviews')
        require(type(protection['enforce_admins']) is bool and protection['restrictions'] is None
                and all(type(protection[flag]) is bool for flag in FLAGS),
                f'{name}: invalid protection flags')
        environments = profile['environments']
        require(isinstance(environments, dict) and environments, f'{name}: environments required')
        for environment, rules in environments.items():
            require(isinstance(rules, dict) and ENVIRONMENT_KEYS <= set(rules)
                    <= ENVIRONMENT_KEYS | OPTIONAL_ENVIRONMENT_KEYS
                    and isinstance(rules['branches'], list)
                    and type(rules['can_admins_bypass']) is bool
                    and type(rules['required_reviewers']) is bool
                    and type(rules.get('prevent_self_review', False)) is bool,
                    f'{name}/{environment}: invalid environment rules')
    return contract


def triggers(workflow):
    """Normalize the string, list and mapping forms GitHub accepts for `on`."""
    events = workflow.get('on', workflow.get(True)) or {}
    if isinstance(events, str):
        return {events: None}
    if isinstance(events, list):
        return dict.fromkeys(events)
    return events


def always_reported_checks(root=ROOT, branch='develop'):
    """Check names emitted on every pull request targeting the code branch.

    A workflow filtered by paths does not run at all for other PRs, so its
    checks stay "expected" forever; a job skipped by its own `if:` still
    reports. Reusable-workflow calls are excluded because GitHub names their
    checks after the nested jobs.
    """
    names = set()
    for path in local_workflows(root):
        workflow = document(path)
        events = triggers(workflow)
        if 'pull_request' not in events:
            continue
        pull_request = events['pull_request'] or {}
        if 'paths' in pull_request or 'paths-ignore' in pull_request:
            continue
        branches = pull_request.get('branches')
        if branches is not None and branch not in branches:
            continue
        for job_id, job in workflow['jobs'].items():
            if 'uses' not in job:
                names.add(job.get('name', job_id))
    return names


def privileged_workflows(root=ROOT):
    """Workflows that can obtain cloud credentials or receive secrets."""
    found = set()
    for path in local_workflows(root):
        text = path.read_text()
        workflow = document(path)
        scopes = [workflow.get('permissions')] + [job.get('permissions')
                                                   for job in workflow['jobs'].values()]
        if any(isinstance(scope, dict) and scope.get('id-token') == 'write' for scope in scopes) \
                or 'secrets.' in text:
            found.add(path.relative_to(root).as_posix())
    return found


def workflow_environments(root=ROOT):
    names = set()
    for path in local_workflows(root):
        for job in document(path)['jobs'].values():
            environment = job.get('environment')
            if isinstance(environment, dict):
                environment = environment.get('name')
            if environment:
                names.add(environment)
    return names


def parse_codeowners(text):
    rules = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        pattern, *owners = line.split()
        require(owners, f'CODEOWNERS line {number}: pattern without owner')
        require(pattern == '*' or (pattern.startswith('/') and '**' not in pattern),
                f'CODEOWNERS line {number}: pattern {pattern!r} is outside the checked subset')
        rules.append((pattern, owners))
    return rules


def owners_for(rules, path):
    """GitHub semantics: the last matching rule wins."""
    result = None
    for pattern, owners in rules:
        if pattern == '*':
            matched = True
        elif pattern.endswith('/'):
            matched = path.startswith(pattern[1:])
        else:
            expression = re.escape(pattern[1:]).replace(r'\*', '[^/]*').replace(r'\?', '[^/]')
            matched = re.fullmatch(expression, path) is not None
        if matched:
            result = (pattern, owners)
    return result


def tracked_files(root, prefixes):
    files = []
    for prefix in prefixes:
        target = root / prefix
        candidates = [target] if target.is_file() else sorted(target.rglob('*'))
        files += [path.relative_to(root).as_posix() for path in candidates
                  if path.is_file() and not {'__pycache__', '.terraform'} & set(path.parts)]
    return files


def codeowners_problems(root=ROOT):
    problems = []
    rules = parse_codeowners((root / TEMPLATE).read_text())
    if not rules or rules[0][0] != '*':
        problems.append(f'{TEMPLATE}: first rule must give a default owner to every file')
    for pattern, owners in rules:
        for owner in owners:
            if not PLACEHOLDER.fullmatch(owner):
                problems.append(f'{TEMPLATE}: {pattern} names {owner}; the template only holds '
                                'placeholders until the owners approve real teams')
    expectations = [(path, SECURITY_OWNER) for path in sorted(privileged_workflows(root))]
    expectations += [(path, SECURITY_OWNER) for path in tracked_files(root, SECURITY_PATHS)]
    expectations += [(path, IAM_OWNER) for path in tracked_files(root, IAM_PATHS)]
    for path, owner in expectations:
        match = owners_for(rules, path)
        if match is None or match[1] != [owner]:
            problems.append(f'{TEMPLATE}: {path} must be owned only by {owner}')
    for active in ACTIVE_CODEOWNERS:
        if not (root / active).is_file():
            continue
        text = (root / active).read_text()
        if PLACEHOLDER.search(text):
            problems.append(f'{active}: active CODEOWNERS still contains template placeholders')
            continue
        active_rules = parse_codeowners(text)
        for path, _ in expectations:
            match = owners_for(active_rules, path)
            if match is None or match[0] == '*':
                problems.append(f'{active}: {path} needs an explicit owner rule')
        break  # GitHub ignores later locations once one exists.
    return problems


def weaker(corporate, lab):
    """Dimensions where the corporate proposal would relax the LAB profile."""
    problems = []
    checks = {name: {check['context'] for check in profile['required_status_checks']['checks']}
              for name, profile in (('corporate', corporate), ('lab', lab))}
    if not checks['lab'] <= checks['corporate']:
        problems.append('corporate drops required checks: '
                        + ', '.join(sorted(checks['lab'] - checks['corporate'])))
    pairs = [(corporate['required_status_checks']['strict'], lab['required_status_checks']['strict'],
              'strict status checks'), (corporate['enforce_admins'], lab['enforce_admins'], 'enforce_admins'),
             (corporate['required_conversation_resolution'], lab['required_conversation_resolution'],
              'conversation resolution'),
             (corporate['required_linear_history'], lab['required_linear_history'], 'linear history'),
             (not corporate['allow_force_pushes'], not lab['allow_force_pushes'], 'force-push block'),
             (not corporate['allow_deletions'], not lab['allow_deletions'], 'deletion block')]
    reviews = corporate['required_pull_request_reviews'], lab['required_pull_request_reviews']
    pairs += [(reviews[0][key], reviews[1][key], key) for key in sorted(REVIEW_KEYS)]
    problems += [f'corporate relaxes {label}' for strict, baseline, label in pairs if strict < baseline]
    return problems


def corporate_minimum(protection):
    reviews = protection['required_pull_request_reviews']
    required = {'enforce_admins': protection['enforce_admins'] is True,
                'one approving review': reviews['required_approving_review_count'] >= 1,
                'code owner review': reviews['require_code_owner_reviews'] is True,
                'last-push approval': reviews['require_last_push_approval'] is True,
                'stale review dismissal': reviews['dismiss_stale_reviews'] is True,
                'conversation resolution': protection['required_conversation_resolution'] is True,
                'force-push block': protection['allow_force_pushes'] is False,
                'deletion block': protection['allow_deletions'] is False,
                'strict status checks': protection['required_status_checks']['strict'] is True}
    return [f'corporate profile lacks {label}' for label, present in required.items() if not present]


def lint(root=ROOT):
    try:
        contract = load(root)
    except (OSError, ValueError) as error:
        return [str(error)]
    problems = []
    reported = always_reported_checks(root, contract['branch'])
    used = workflow_environments(root)
    for name, profile in contract['profiles'].items():
        for check in profile['protection']['required_status_checks']['checks']:
            if check['app_id'] != GITHUB_ACTIONS_APP_ID:
                problems.append(f'{name}: {check["context"]} must be bound to GitHub Actions')
            if check['context'] not in reported:
                problems.append(f'{name}: required check {check["context"]!r} is not emitted on '
                                'every pull request and would block unrelated PRs')
        declared = set(profile['environments'])
        if declared != used:
            problems.append(f'{name}: environments {sorted(declared)} differ from the ones the '
                            f'workflows use {sorted(used)}')
        for environment, rules in profile['environments'].items():
            if rules['branches'] != [contract['branch']] or rules['can_admins_bypass']:
                problems.append(f'{name}/{environment}: must allow only {contract["branch"]} '
                                'without administrator bypass')
            if 'reviewers' in rules and rules['required_reviewers'] != bool(rules['reviewers']):
                problems.append(f'{name}/{environment}: reviewers and required_reviewers disagree')
    corporate, lab = (contract['profiles'][name]['protection'] for name in ('corporate', 'lab'))
    problems += corporate_minimum(corporate) + weaker(corporate, lab)
    for environment, rules in contract['profiles']['corporate']['environments'].items():
        if rules['required_reviewers'] and rules.get('prevent_self_review') is not True:
            problems.append(f'corporate/{environment}: required reviewers must prevent self-review')
    return problems + codeowners_problems(root)


def gh_fetch(path):
    """GET only; a 404 is returned to the caller, anything else unreadable fails."""
    result = subprocess.run(['gh', 'api', '--method', 'GET', path], check=False,
                            capture_output=True, text=True, timeout=60)
    try:
        body = json.loads(result.stdout) if result.stdout.strip() else None
    except ValueError:
        body = None
    if result.returncode == 0:
        return 200, body
    if 'HTTP 404' in result.stderr:
        return 404, body
    raise RuntimeError(f'GET {path} failed; result is inconclusive')


def normalized_protection(live):
    """Map the GET representation onto the PUT body used by the contract."""
    def enabled(key):
        value = live.get(key)
        return bool(value.get('enabled')) if isinstance(value, dict) else bool(value)
    checks = live.get('required_status_checks') or {}
    reviews = live.get('required_pull_request_reviews')
    result = {
        'required_status_checks': {'strict': bool(checks.get('strict')), 'checks': sorted(
            ({'context': item.get('context'), 'app_id': item.get('app_id')}
             for item in checks.get('checks') or []), key=lambda item: item['context'])},
        'enforce_admins': enabled('enforce_admins'),
        'required_pull_request_reviews': None if reviews is None else {
            key: reviews.get(key, False if key != 'required_approving_review_count' else 0)
            for key in REVIEW_KEYS},
        'restrictions': live.get('restrictions') or None,
    }
    result.update({flag: enabled(flag) for flag in FLAGS})
    return result


def protection_differences(live, expected):
    differences = []
    expected = dict(expected, required_status_checks=dict(
        expected['required_status_checks'], checks=sorted(
            expected['required_status_checks']['checks'], key=lambda item: item['context'])))
    for key in sorted(PROTECTION_KEYS):
        if live.get(key) != expected[key]:
            differences.append(f'{key}: live {json.dumps(live.get(key), sort_keys=True)} '
                               f'!= contract {json.dumps(expected[key], sort_keys=True)}')
    return differences


def bypass_allowances(live):
    reviews = live.get('required_pull_request_reviews') or {}
    allowances = reviews.get('bypass_pull_request_allowances') or {}
    return [f'pull request bypass allowance for {kind}: '
            + ', '.join(str(entry.get('login') or entry.get('slug') or entry.get('name'))
                        for entry in entries)
            for kind, entries in sorted(allowances.items()) if entries]


def environment_differences(repository, expected, fetch):
    status, listing = fetch(f'repos/{repository}/environments?per_page=100')
    require(status == 200 and isinstance(listing, dict), 'environments unreadable')
    live = {item['name']: item for item in listing.get('environments') or []}
    differences = []
    if set(live) != set(expected):
        differences.append(f'environments: live {sorted(live)} != contract {sorted(expected)}')
    for name in sorted(set(live) & set(expected)):
        rules, item = expected[name], live[name]
        status, policies = fetch(f'repos/{repository}/environments/{name}/deployment-branch-policies')
        require(status == 200 and isinstance(policies, dict), f'{name}: branch policies unreadable')
        branches = sorted(entry['name'] for entry in policies.get('branch_policies') or []
                          if entry.get('type', 'branch') == 'branch')
        others = [entry for entry in policies.get('branch_policies') or []
                  if entry.get('type', 'branch') != 'branch']
        deployment = item.get('deployment_branch_policy') or {}
        if deployment.get('custom_branch_policies') is not True or others \
                or branches != sorted(rules['branches']):
            differences.append(f'{name}: deployment refs {branches} (+{len(others)} tag rule(s)) '
                               f'!= contract {rules["branches"]}')
        if item.get('can_admins_bypass') is not rules['can_admins_bypass']:
            differences.append(f'{name}: can_admins_bypass differs')
        reviewers = [rule for rule in item.get('protection_rules') or []
                     if rule.get('type') == 'required_reviewers']
        if bool(reviewers) is not rules['required_reviewers']:
            differences.append(f'{name}: required reviewers present={bool(reviewers)}')
        if reviewers and 'prevent_self_review' in rules \
                and reviewers[0].get('prevent_self_review') is not rules['prevent_self_review']:
            differences.append(f'{name}: prevent_self_review differs')
        if reviewers and 'reviewers' in rules:
            names = sorted(entry['reviewer'].get('login') or entry['reviewer'].get('slug')
                           for entry in reviewers[0].get('reviewers') or [])
            if names != sorted(rules['reviewers']):
                differences.append(f'{name}: reviewers {names} != contract {sorted(rules["reviewers"])}')
    return differences


def verify(profile_name, root=ROOT, fetch=gh_fetch):
    """Read-only comparison of the live settings with one profile."""
    contract = load(root)
    profile = contract['profiles'][profile_name]
    repository, branch = contract['repository'], contract['branch']
    differences = []
    status, live = fetch(f'repos/{repository}/branches/{branch}/protection')
    if status == 404:
        require(isinstance(live, dict) and live.get('message') == 'Branch not protected',
                'protection read returned 404 without "Branch not protected"; inconclusive')
        differences.append(f'{branch} is not protected')
    else:
        require(status == 200 and isinstance(live, dict), 'protection unreadable')
        differences += protection_differences(normalized_protection(live), profile['protection'])
        differences += bypass_allowances(live)
    status, rulesets = fetch(f'repos/{repository}/rulesets?includes_parents=true')
    require(status == 200 and isinstance(rulesets, list), 'rulesets unreadable')
    if rulesets:
        differences.append(f'{len(rulesets)} ruleset(s) present and not modelled by the contract: '
                           + ', '.join(sorted(str(item.get('name')) for item in rulesets)))
    differences += environment_differences(repository, profile['environments'], fetch)
    return {'checked_at': datetime.now(timezone.utc).isoformat(), 'repository': repository,
            'branch': branch, 'profile': profile_name, 'profile_status': profile['status'],
            'result': 'DRIFT' if differences else 'MATCH', 'differences': differences}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('lint', 'verify'))
    parser.add_argument('--profile', choices=sorted(STATUSES), default='lab')
    parser.add_argument('--json', dest='json_output', type=Path)
    args = parser.parse_args(argv)
    if args.mode == 'lint':
        problems = lint()
        for problem in problems:
            print(f'::error::{problem}', file=sys.stderr)
        print(f'Branch protection contract checked: {len(problems)} problem(s).')
        return 1 if problems else 0
    try:
        report = verify(args.profile)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'::error::verification inconclusive: {error}', file=sys.stderr)
        return 2
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['result'] == 'MATCH' else 1


if __name__ == '__main__':
    raise SystemExit(main())
