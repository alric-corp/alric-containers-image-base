"""Single canonical producer-identity contract for SBOM artifact binding and intake.

Both the Frente C binder (`artifact_binding.py`) and the Frente D2 intake
(`intake.py`) must bind a downloaded `sbom-<framework>-<attempt>` artifact to
its declared origin before its bytes are staged. They used to carry two
divergent copies of that cross-check. This module is the one place that
decides what an identity claim is worth, so there is a single contract and a
single set of negatives to maintain. It never downloads, calls GitHub or AWS,
executes artifact members, or infers an absent value.

The contract separates three tiers, because the GitHub artifacts REST record
(`GET /repos/{owner}/{repo}/actions/artifacts/{id}`) simply does not carry
every identity an auditor wants:

* ``verified`` -- cross-checked against the saved artifact record: the
  artifact id and name, the archive sha256 and size, and from the record's
  reduced ``workflow_run`` object the run id, repository id, head repository
  id (no fork), head branch and head source commit.
* ``declared`` -- asserted by the caller's manifest/request but NOT provable
  from the artifact record alone: the ``run_attempt`` (only echoed inside the
  artifact name) and the producing workflow identity (path/name/id). The
  artifacts endpoint omits both.
* resolution of the declared tier -- only an explicitly supplied workflow-run
  record (``GET /actions/runs/{run_id}`` or ``.../attempts/{n}``, which does
  carry ``run_attempt``, ``path``, ``name`` and ``workflow_id``) can move
  ``run_attempt`` and the workflow identity into ``verified``. When no such
  record is supplied they stay ``NOT_VERIFIABLE`` and
  ``corporate_acceptance`` is ``FORBIDDEN``. We never claim a guarantee the
  data cannot support.

The function returns a structured ``identity`` block (safe to embed in a
receipt or a lot record) and raises :class:`IdentityError` on any divergence.
Callers map that single exception onto their own error dialect.
"""
import re

# Fields the reduced workflow_run object inside the artifact record may carry.
_ARTIFACT_RUN_REQUIRED = ('id', 'repository_id', 'head_sha')
# Fields a full workflow-run record (runs endpoint) carries that the artifact
# record does not; these are what let us verify the declared tier.
_RUN_RECORD_IDENTITY = ('run_attempt', 'path', 'name', 'workflow_id')

_SHA = re.compile(r'[0-9a-f]{40}')
_OCI = re.compile(r'sha256:[0-9a-f]{64}')
_WORKFLOW_PATH = re.compile(r'\.github/workflows/[A-Za-z0-9._/-]{1,128}\.ya?ml')


class IdentityError(ValueError):
    """One divergence between a declared identity and the saved evidence.

    ``code`` is a stable machine code; ``message`` is bounded, printable and
    never echoes artifact bytes, URLs or tokens.
    """

    def __init__(self, code, message):
        self.code = code
        super().__init__(code + ': ' + message)


def _refuse(code, message):
    raise IdentityError(code, message)


def _check(condition, code, message):
    if not condition:
        _refuse(code, message)


def _declared(declared):
    """Validate the shape of the caller's declared origin before any comparison."""
    _check(isinstance(declared, dict), 'IDENTITY_DECLARATION_INVALID', 'declared identity must be an object')
    for key in ('framework', 'artifact_id', 'artifact_name', 'repository_id', 'run_id', 'run_attempt', 'source_sha'):
        _check(key in declared, 'IDENTITY_DECLARATION_INVALID', 'declared identity lacks ' + key)
    framework = declared['framework']
    _check(isinstance(framework, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]*', framework),
           'IDENTITY_DECLARATION_INVALID', 'invalid framework')
    for key in ('artifact_id', 'repository_id', 'run_id', 'run_attempt'):
        value = declared[key]
        _check(type(value) is int and 0 < value < 2 ** 63, 'IDENTITY_DECLARATION_INVALID',
               framework + ': ' + key + ' must be a positive integer')
    _check(isinstance(declared['source_sha'], str) and _SHA.fullmatch(declared['source_sha']),
           'IDENTITY_DECLARATION_INVALID', framework + ': source_sha must be a 40-hex commit')
    _check(declared['artifact_name'] == 'sbom-%s-%d' % (framework, declared['run_attempt']),
           'ARTIFACT_ATTEMPT_DIFFERS', framework + ': artifact name does not carry the declared run attempt')
    ref = declared.get('ref')
    _check(ref is None or isinstance(ref, str), 'IDENTITY_DECLARATION_INVALID', framework + ': ref must be a string')
    return framework


def _artifact_record(record, declared, framework):
    """Cross-check the saved artifact record. Returns the verified sub-block."""
    _check(isinstance(record, dict), 'ARTIFACT_RECORD_INCOMPLETE', framework + ': artifact record must be an object')
    run = record.get('workflow_run')
    _check(all(key in record for key in ('id', 'name')) and isinstance(run, dict)
           and all(key in run for key in _ARTIFACT_RUN_REQUIRED), 'ARTIFACT_RECORD_INCOMPLETE',
           framework + ': artifact record lacks id/name/workflow_run.{id,repository_id,head_sha}')
    _check(type(record['id']) is int and record['id'] == declared['artifact_id'], 'ARTIFACT_ID_DIFFERS',
           framework + ': artifact record id differs from the declared artifact_id')
    _check(record['name'] == declared['artifact_name'], 'ARTIFACT_NAME_DIFFERS',
           framework + ': artifact record name differs from the declared name')
    _check(type(run['id']) is int and run['id'] == declared['run_id'], 'ARTIFACT_RUN_DIFFERS',
           framework + ': artifact belongs to a different run than declared')
    _check(type(run['repository_id']) is int and run['repository_id'] == declared['repository_id'],
           'ARTIFACT_REPOSITORY_DIFFERS', framework + ': artifact run repository id differs from declared')
    _check(run['head_sha'] == declared['source_sha'], 'ARTIFACT_SOURCE_DIFFERS',
           framework + ': artifact run head_sha differs from the declared source_sha')
    verified = dict(artifact_id='MATCHED', artifact_name='MATCHED', run_id='MATCHED',
                    repository_id='MATCHED', source_sha='MATCHED')
    # head repository: present means we can prove it is not a fork.
    if 'head_repository_id' in run:
        _check(run['head_repository_id'] == declared['repository_id'], 'ARTIFACT_REPOSITORY_DIFFERS',
               framework + ': artifact run head repository differs (fork)')
        verified['head_repository_id'] = 'MATCHED'
    else:
        verified['head_repository_id'] = 'NOT_PROVIDED'
    # branch: only comparable when the declared ref is a branch ref and the
    # record carries head_branch.
    ref = declared.get('ref')
    if isinstance(ref, str) and ref.startswith('refs/heads/') and 'head_branch' in run:
        _check(run['head_branch'] == ref[len('refs/heads/'):], 'ARTIFACT_BRANCH_DIFFERS',
               framework + ': artifact run head_branch differs from the declared ref')
        verified['head_branch'] = 'MATCHED'
    elif 'head_branch' not in run:
        verified['head_branch'] = 'NOT_PROVIDED'
    else:
        verified['head_branch'] = 'NOT_APPLICABLE'
    return verified


def _run_record(run_record, declared, framework):
    """Resolve the declared tier against an explicitly supplied workflow-run record.

    Only this record proves ``run_attempt`` and the producing workflow
    identity. Its own run id/repository/head_sha must still agree with the
    artifact-level facts, so a record for a different run cannot be swapped in.
    """
    _check(isinstance(run_record, dict), 'RUN_RECORD_INVALID', framework + ': workflow-run record must be an object')
    for key in _RUN_RECORD_IDENTITY + ('id', 'head_sha'):
        _check(key in run_record, 'RUN_RECORD_INCOMPLETE',
               framework + ': workflow-run record lacks ' + key)
    _check(type(run_record['id']) is int and run_record['id'] == declared['run_id'], 'RUN_RECORD_RUN_DIFFERS',
           framework + ': workflow-run record is for a different run than the artifact')
    _check(run_record['head_sha'] == declared['source_sha'], 'RUN_RECORD_SOURCE_DIFFERS',
           framework + ': workflow-run record head_sha differs from the declared source_sha')
    _check(type(run_record['run_attempt']) is int and run_record['run_attempt'] == declared['run_attempt'],
           'RUN_ATTEMPT_DIFFERS', framework + ': actual run attempt differs from the declared attempt')
    declared_workflow = declared.get('workflow')
    _check(isinstance(declared_workflow, dict) and _WORKFLOW_PATH.fullmatch(str(declared_workflow.get('path', ''))),
           'WORKFLOW_IDENTITY_UNDECLARED',
           framework + ': a supplied run record requires a declared workflow.path to bind against')
    _check(run_record['path'] == declared_workflow['path'], 'WORKFLOW_IDENTITY_DIFFERS',
           framework + ': producing workflow path differs from the declared workflow identity')
    for key in ('name', 'workflow_id'):
        if key in declared_workflow:
            _check(run_record[key] == declared_workflow[key], 'WORKFLOW_IDENTITY_DIFFERS',
                   framework + ': producing workflow ' + key + ' differs from the declared workflow identity')
    return dict(run_attempt='VERIFIED', workflow_path='VERIFIED',
                workflow_name='VERIFIED' if 'name' in declared_workflow else 'DECLARED_NOT_COMPARED',
                workflow_id='VERIFIED' if 'workflow_id' in declared_workflow else 'DECLARED_NOT_COMPARED',
                evidence='workflow-run-record')


def verify_identity(declared, api_record, run_record=None):
    """Bind one artifact's declared identity to the saved evidence.

    ``declared`` -- caller's claim: framework, artifact_id, artifact_name,
    repository_id, run_id, run_attempt, source_sha, optional ref and optional
    ``workflow`` {path[, name, workflow_id]}.
    ``api_record`` -- the saved GitHub artifacts REST record.
    ``run_record`` -- optional saved workflow-run record that alone can verify
    the attempt and the producing workflow identity.

    Returns an ``identity`` block with ``verified`` / ``declared`` /
    ``not_verifiable`` tiers and a ``corporate_acceptance`` verdict. Raises
    :class:`IdentityError` on any divergence.
    """
    framework = _declared(declared)
    verified = _artifact_record(api_record, declared, framework)

    attempt_and_workflow = {}
    not_verifiable = {}
    if run_record is not None:
        attempt_and_workflow = _run_record(run_record, declared, framework)
    else:
        # The artifacts endpoint cannot prove either; say so explicitly and
        # forbid corporate acceptance rather than inventing a guarantee.
        not_verifiable = dict(
            run_attempt='NOT_VERIFIABLE_FROM_ARTIFACT_RECORD',
            workflow_identity='NOT_VERIFIABLE_FROM_ARTIFACT_RECORD',
            reason='the GitHub artifacts record omits run_attempt and workflow identity; '
                   'supply a workflow-run record to verify them')

    corporate_acceptance = 'ELIGIBLE' if run_record is not None else 'FORBIDDEN'
    identity = dict(
        framework=framework,
        verified=dict(verified, **{k: v for k, v in attempt_and_workflow.items()}),
        declared=dict(run_attempt=declared['run_attempt'], run_id=declared['run_id'],
                      repository_id=declared['repository_id'], source_sha=declared['source_sha'],
                      ref=declared.get('ref'),
                      workflow=declared.get('workflow', 'NOT_DECLARED')),
        not_verifiable=not_verifiable,
        producer_identity_verified=run_record is not None,
        corporate_acceptance=corporate_acceptance,
        network_calls=0, cloud_calls=0)
    return identity
