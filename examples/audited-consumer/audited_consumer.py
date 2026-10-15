#!/usr/bin/env python3
"""Gate de consumo auditado das imagens base, para o pipeline do time consumidor.

Resolve cada referência uma única vez, executa os verificadores existentes da
Factory, fixa o mesmo índice OCI em um lock e recusa qualquer evidência
ausente, divergente ou inconclusiva (exit 1, sem lock).

Não implementa criptografia própria. Assinatura, identidade, provenance e SBOM
attestation são verificados por ``scripts/verify-image.sh`` (nível
``simplified``) e por ``scripts.pipeline.release.verify_promotion`` (nível
``full-policy``), ambos de um checkout revisado da Factory. Este gate
acrescenta somente vínculos do lado consumidor: referência resolvida uma vez,
mesmo digest na verificação, no lock e no ``FROM``, par runtime/-dev, release
aprovada (commit/run/attempt) quando informada e diagnósticos JSON.

Não é admission controller, não aprova a segurança da aplicação e não
substitui a política corporativa de consumo. Requer Python 3.9+ em POSIX.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

TOOL_VERSION = '1.0.0'
SCHEMA_VERSION = 1
LEVELS = ('simplified', 'full-policy')
# Valores aplicados de forma fixa pelos verificadores da Factory. A política
# declara a identidade esperada; se ela não for exatamente a que o verificador
# escolhido aplica, o gate recusa em vez de prometer uma checagem que não ocorre.
ENFORCED_ISSUER = 'https://token.actions.githubusercontent.com'
ENFORCED_WORKFLOW = '.github/workflows/build-base-images.yml'
FULL_POLICY_REF = 'refs/heads/develop'
VERIFY_IMAGE_PREFIX = 'image-base-'

DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
HEX64 = re.compile(r'[0-9a-f]{64}')
GIT_SHA = re.compile(r'[0-9a-f]{40}')
TAG = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}')
FRAMEWORK = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
BUILD_ARG = re.compile(r'[A-Z][A-Z0-9_]{0,63}')
REGISTRY = re.compile(r'[a-z0-9]+(?:[.-][a-z0-9]+)*(?::[0-9]{1,5})?')
ECR = re.compile(r'([0-9]{12})\.dkr\.ecr\.([a-z]{2}(?:-[a-z]+)+-[0-9])\.amazonaws\.com(?:\.cn)?')
PREFIX = re.compile(r'[a-z0-9][a-z0-9._/-]{0,63}')
REPOSITORY = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+')
WORKFLOW = re.compile(r'\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml')
BRANCH_REF = re.compile(r'refs/heads/[A-Za-z0-9._/-]+')
ISSUER = re.compile(r'https://[a-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~-]+)*')
IMAGE_REF = re.compile(r'([a-z0-9]+(?:[.-][a-z0-9]+)*(?::[0-9]{1,5})?)/([a-z0-9._/-]+)@(sha256:[0-9a-f]{64})')
PLATFORMS = ('linux/amd64', 'linux/arm64')
LIMITATIONS = ('NOT_AN_ADMISSION_CONTROLLER', 'NOT_AN_APPLICATION_SECURITY_APPROVAL',
               'BASE_SIGNATURE_DOES_NOT_SIGN_THE_DERIVED_IMAGE', 'NOT_A_HOSTED_OR_CORPORATE_ACCEPTANCE')


class GateError(Exception):
    """Confiança não comprovada. Nunca é convertida em sucesso."""

    def __init__(self, code, message, base=None, exit_code=1):
        super().__init__(message)
        self.code, self.base, self.exit_code = code, base, exit_code


def usage_error(code, message):
    return GateError(code, message, exit_code=2)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def render(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')


def strict_json(raw, label, code='INPUT_INVALID', exit_code=2):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise GateError(code, f'{label}: chave duplicada {key!r}', exit_code=exit_code)
            result[key] = value
        return result

    def constant(value):
        raise GateError(code, f'{label}: valor JSON não finito {value}', exit_code=exit_code)

    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError) as error:  # GateError dos hooks não é ValueError e segue intacto
        raise GateError(code, f'{label}: JSON inválido ({error})', exit_code=exit_code) from error


def read_regular(path, label, code='INPUT_INVALID', exit_code=2, limit=8 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise GateError(code, f'{label}: arquivo regular obrigatório ({path})', exit_code=exit_code)
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise GateError(code, f'{label}: tamanho acima do limite', exit_code=exit_code)
    return raw


def exact_keys(value, keys, label, code='POLICY_INVALID', optional=()):
    if type(value) is not dict or not set(keys) <= set(value) or not set(value) <= set(keys) | set(optional):
        raise usage_error(code, f'{label}: campos obrigatórios/desconhecidos divergem de {sorted(keys)}')


def require(condition, code, message, base=None, exit_code=1):
    if not condition:
        raise GateError(code, message, base=base, exit_code=exit_code)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


# ---------------------------------------------------------------------------
# Política do consumidor e release aprovada
# ---------------------------------------------------------------------------

POLICY_KEYS = ('schema_version', 'verification_level', 'registry', 'repository_prefix', 'source_repository',
               'signer_workflow', 'signer_ref', 'oidc_issuer', 'bases', 'require_sbom_attestation',
               'verifier_timeout_seconds', 'factory_checkout_commit', 'verifier_script_sha256')


def uses_verify_image(policy):
    return policy['verification_level'] == 'simplified' or policy['require_sbom_attestation']


def load_policy(path):
    raw = read_regular(path, 'policy', 'POLICY_INVALID')
    policy = strict_json(raw, 'policy', 'POLICY_INVALID')
    exact_keys(policy, POLICY_KEYS, 'policy')
    bad = [s for s in strings(policy) if not s or '<' in s or '>' in s or any(c.isspace() for c in s)]
    if bad:
        raise usage_error('POLICY_PLACEHOLDER', f'policy contém placeholder/valor vazio: {bad[0]!r}')

    def check(condition, message, code='POLICY_INVALID'):
        if not condition:
            raise usage_error(code, message)

    check(type(policy['schema_version']) is int and policy['schema_version'] == SCHEMA_VERSION, 'schema_version')
    check(policy['verification_level'] in LEVELS, 'verification_level deve ser simplified ou full-policy')
    for key, pattern in (('registry', REGISTRY), ('repository_prefix', PREFIX), ('source_repository', REPOSITORY),
                         ('signer_workflow', WORKFLOW), ('signer_ref', BRANCH_REF), ('oidc_issuer', ISSUER)):
        check(type(policy[key]) is str and pattern.fullmatch(policy[key]) is not None, f'{key} inválido')
    check('..' not in policy['signer_ref'] and not policy['signer_ref'].endswith('/'), 'signer_ref inválido')
    check(type(policy['require_sbom_attestation']) is bool, 'require_sbom_attestation deve ser booleano')
    timeout = policy['verifier_timeout_seconds']
    check(type(timeout) is int and 1 <= timeout <= 3600, 'verifier_timeout_seconds deve estar entre 1 e 3600')
    commit, script = policy['factory_checkout_commit'], policy['verifier_script_sha256']
    check(commit is None or (type(commit) is str and GIT_SHA.fullmatch(commit)), 'factory_checkout_commit inválido')
    check(script is None or (type(script) is str and HEX64.fullmatch(script)), 'verifier_script_sha256 inválido')

    bases = policy['bases']
    check(type(bases) is dict and 'runtime' in bases and set(bases) <= {'runtime', 'build'},
          'bases exige runtime e, opcionalmente, build')
    for name, base in bases.items():
        exact_keys(base, ('framework', 'build_arg'), f'bases.{name}')
        check(type(base['framework']) is str and FRAMEWORK.fullmatch(base['framework']), f'bases.{name}.framework')
        check(type(base['build_arg']) is str and BUILD_ARG.fullmatch(base['build_arg']), f'bases.{name}.build_arg')
    runtime = bases['runtime']['framework']
    check(not runtime.endswith('-dev'), 'a base final (runtime) não pode ser uma variante -dev', 'PAIR_INCOMPATIBLE')
    if 'build' in bases:
        check(bases['build']['framework'] == runtime + '-dev',
              f'par incompatível: build deve ser {runtime}-dev, não {bases["build"]["framework"]}', 'PAIR_INCOMPATIBLE')
        check(bases['build']['build_arg'] != bases['runtime']['build_arg'], 'build_arg duplicado')

    # A identidade declarada precisa ser exatamente a aplicada pelo verificador.
    enforce = []
    if policy['oidc_issuer'] != ENFORCED_ISSUER:
        enforce.append(f'issuer {policy["oidc_issuer"]} (verificadores aplicam {ENFORCED_ISSUER})')
    if policy['signer_workflow'] != ENFORCED_WORKFLOW:
        enforce.append(f'workflow {policy["signer_workflow"]} (verificadores aplicam {ENFORCED_WORKFLOW})')
    if policy['verification_level'] == 'full-policy':
        if policy['signer_ref'] != FULL_POLICY_REF:
            enforce.append(f'ref {policy["signer_ref"]} (verify_promotion aplica {FULL_POLICY_REF})')
        check(commit is not None, 'full-policy exige factory_checkout_commit')
    else:
        check(policy['require_sbom_attestation'] is True,
              'simplified sempre verifica SBOM attestation (verify-image.sh); declare true')
    if uses_verify_image(policy):
        if ECR.fullmatch(policy['registry']) is None:
            enforce.append('verify-image.sh exige registry ECR <conta>.dkr.ecr.<região>.amazonaws.com')
        if policy['repository_prefix'] != VERIFY_IMAGE_PREFIX:
            enforce.append(f'verify-image.sh usa o prefixo {VERIFY_IMAGE_PREFIX}')
        check(script is not None, 'verify-image.sh é usado: fixe verifier_script_sha256')
    if enforce:
        raise usage_error('POLICY_NOT_ENFORCEABLE', 'política declara identidade não aplicada: ' + '; '.join(enforce))
    return policy, raw


RELEASE_KEYS = ('schema_version', 'source_repository', 'source_sha', 'run_id', 'run_attempt', 'images')


def load_release(path, policy):
    raw = read_regular(path, 'release record', 'RELEASE_RECORD_INVALID')
    record = strict_json(raw, 'release record', 'RELEASE_RECORD_INVALID')
    exact_keys(record, RELEASE_KEYS, 'release record', 'RELEASE_RECORD_INVALID')
    valid = (type(record['schema_version']) is int and record['schema_version'] == SCHEMA_VERSION
             and record['source_repository'] == policy['source_repository']
             and type(record['source_sha']) is str and GIT_SHA.fullmatch(record['source_sha'])
             and all(type(record[k]) is int and record[k] > 0 for k in ('run_id', 'run_attempt'))
             and type(record['images']) is dict
             and all(type(k) is str and FRAMEWORK.fullmatch(k) and type(v) is str and DIGEST.fullmatch(v)
                     for k, v in record['images'].items()))
    if not valid:
        raise usage_error('RELEASE_RECORD_INVALID', 'release record inválido ou de outro repositório de origem')
    return record, raw


# ---------------------------------------------------------------------------
# Execução limitada dos verificadores externos
# ---------------------------------------------------------------------------

def run_bounded(command, timeout, *, base=None, cwd=None, env=None):
    """Executa sem shell, em grupo de processos próprio; timeout encerra o grupo inteiro."""
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, cwd=cwd, env=env, start_new_session=True)
    except OSError as error:
        raise GateError('VERIFIER_UNAVAILABLE', f'não foi possível executar {command[0]}: {error}', base) from error
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        raise GateError('VERIFIER_TIMEOUT', f'{Path(command[0]).name} excedeu {timeout}s; grupo encerrado', base)
    return subprocess.CompletedProcess(command, process.returncode, out.decode('utf-8', 'replace'),
                                       err.decode('utf-8', 'replace'))


def resolve_tag(policy, framework, tag, base):
    """Única consulta de tag do fluxo, com a mesma validação do contrato de consumo."""
    match = ECR.fullmatch(policy['registry'])
    require(match is not None, 'TAG_RESOLUTION_UNSUPPORTED',
            'resolução de tag implementada só para ECR; informe o digest aprovado', base, 2)
    repository = policy['repository_prefix'] + framework
    result = run_bounded(['aws', 'ecr', 'describe-images', '--region', match.group(2), '--registry-id', match.group(1),
                          '--repository-name', repository, '--image-ids', 'imageTag=' + tag,
                          '--query', 'imageDetails[].imageDigest', '--output', 'text'],
                         policy['verifier_timeout_seconds'], base=base)
    digest = result.stdout.strip()
    require(result.returncode == 0 and DIGEST.fullmatch(digest) is not None, 'TAG_RESOLUTION_FAILED',
            f'tag {tag!r} de {repository} não resolveu para exatamente um digest (obtido {digest!r})', base)
    return digest


def checkout_identity(path, expected, timeout):
    checkout = Path(path).resolve()
    require(checkout.is_dir(), 'FACTORY_CHECKOUT_UNTRUSTED', f'checkout da Factory ausente: {checkout}', None, 2)
    head = run_bounded(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], timeout)
    require(head.returncode == 0 and head.stdout.strip() == expected, 'FACTORY_CHECKOUT_UNTRUSTED',
            f'checkout da Factory em {head.stdout.strip() or "?"}; a política exige {expected}')
    status = run_bounded(['git', '-C', str(checkout), 'status', '--porcelain=v1', '--untracked-files=all'], timeout)
    require(status.returncode == 0 and not status.stdout.strip(), 'FACTORY_CHECKOUT_UNTRUSTED',
            'checkout da Factory com alterações locais; use o commit revisado sem modificações')
    for relative in ('scripts/pipeline/release/verify_promotion.py', 'policies/release/signing-identities.json'):
        require((checkout / relative).is_file(), 'FACTORY_CHECKOUT_UNTRUSTED', f'checkout sem {relative}')
    return checkout


def pinned_script(path, expected, work):
    """Executa a cópia exata dos bytes conferidos, nunca o arquivo original (sem TOCTOU)."""
    raw = read_regular(path, 'verify-image.sh', 'VERIFIER_SCRIPT_UNTRUSTED', exit_code=1)
    require(sha256(raw) == expected, 'VERIFIER_SCRIPT_UNTRUSTED',
            f'verify-image.sh com sha256 {sha256(raw)}; a política fixa {expected}')
    copy = work / 'verify-image.sh'
    copy.write_bytes(raw)
    copy.chmod(0o500)
    return copy


# ---------------------------------------------------------------------------
# Verificação por base
# ---------------------------------------------------------------------------

def image_ref(policy, framework, digest):
    return f'{policy["registry"]}/{policy["repository_prefix"]}{framework}@{digest}'


def verify_image_script(policy, base, framework, digest, script, work, repository):
    """Nível simplified: assinatura + SBOM attestation + provenance (repo/workflow/ref)."""
    match = ECR.fullmatch(policy['registry'])
    reports = work / f'{base}-verify-image'
    result = run_bounded(['bash', str(script), framework, digest, '--account', match.group(1),
                          '--region', match.group(2), '--repo', repository, '--ref', policy['signer_ref'],
                          '--report-dir', str(reports)], policy['verifier_timeout_seconds'], base=base)
    (work / f'{base}-verify-image.stdout').write_text(result.stdout, encoding='utf-8')
    (work / f'{base}-verify-image.stderr').write_text(result.stderr, encoding='utf-8')
    lines = result.stdout.splitlines()
    failed = [line for line in lines if line.startswith('FAIL: ')]
    if result.returncode != 0:
        if result.returncode == 3:
            raise GateError('VERIFIER_UNAVAILABLE', 'verify-image.sh: ' + result.stderr.strip(), base)
        for prefix, code in (('FAIL: assinatura', 'SIGNATURE_REJECTED'), ('FAIL: provenance', 'PROVENANCE_REJECTED'),
                             ('FAIL: attestation SBOM', 'SBOM_ATTESTATION_REJECTED')):
            if any(line.startswith(prefix) for line in failed):
                raise GateError(code, f'verify-image.sh recusou {image_ref(policy, framework, digest)}: '
                                + ' | '.join(failed), base)
        raise GateError('VERIFIER_FAILED', f'verify-image.sh terminou com {result.returncode}', base)
    expected = image_ref(policy, framework, digest)
    verdicts = [line for line in lines if line.startswith('RESULTADO: ')]
    if len(verdicts) == 1 and verdicts[0].startswith('RESULTADO: PASS -- ') and verdicts[0] != 'RESULTADO: PASS -- ' + expected:
        raise GateError('DIGEST_MISMATCH', f'verificador confirmou {verdicts[0][19:]}, esperado {expected}', base)
    passes = {'signature': 'PASS: assinatura', 'sbom_attestation': 'PASS: attestation SBOM',
              'provenance': 'PASS: provenance'}
    require(verdicts == ['RESULTADO: PASS -- ' + expected] and not failed
            and all(any(line.startswith(p) for line in lines) for p in passes.values()),
            'INSUFFICIENT_EVIDENCE', 'saída do verify-image.sh não comprova as três verificações', base)
    evidence = {p.name: sha256(p.read_bytes()) for p in sorted(reports.iterdir()) if p.is_file()} \
        if reports.is_dir() else {}
    return {name: 'PASS' for name in passes}, evidence


def statements(entries):
    for entry in entries:
        result = entry.get('verificationResult') if type(entry) is dict else None
        statement = result.get('statement') if type(result) is dict else None
        yield statement if type(statement) is dict else None


def full_policy(policy, base, framework, digest, checkout, release, work):
    """Nível full-policy: verify_promotion do checkout revisado + vínculos de subject e release."""
    reference = image_ref(policy, framework, digest)
    reports = work / f'{base}-full-policy'
    reports.mkdir(mode=0o700)
    command = [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '_full-policy-worker',
               '--factory-checkout', str(checkout), '--image', reference,
               '--repository', policy['source_repository'], '--reports', str(reports)]
    if release is not None:
        command += ['--source-sha', release['source_sha']]
    result = run_bounded(command, policy['verifier_timeout_seconds'], base=base)
    (work / f'{base}-full-policy.stderr').write_text(result.stderr, encoding='utf-8')
    if result.returncode != 0:
        try:
            failure = json.loads(result.stderr.strip().splitlines()[-1])
            code, message = failure['code'], failure['message']
        except (IndexError, ValueError, KeyError, TypeError):
            code, message = 'VERIFIER_FAILED', f'verify_promotion terminou com {result.returncode}'
        raise GateError(code, message, base)

    def load(name):
        path = reports / name
        require(path.is_file() and not path.is_symlink(), 'INSUFFICIENT_EVIDENCE', f'{name} ausente', base)
        return strict_json(path.read_bytes(), name, 'INSUFFICIENT_EVIDENCE', exit_code=1)

    identity = load('verified-identity.json')
    require(type(identity) is dict and identity.get('image') == reference, 'DIGEST_MISMATCH',
            f'verify_promotion confirmou {identity.get("image") if type(identity) is dict else "?"}, '
            f'esperado {reference}', base)
    signer = identity.get('signer_repository')
    require(identity.get('repository') == policy['source_repository'] and type(signer) is str
            and REPOSITORY.fullmatch(signer), 'INSUFFICIENT_EVIDENCE', 'identidade verificada incompleta', base)
    index = load('candidate-index.json')
    platforms = {}
    for entry in index.get('manifests', []) if type(index) is dict else []:
        platform = entry.get('platform', {}) if type(entry) is dict else {}
        name = f'{platform.get("os")}/{platform.get("architecture")}'
        require(name in PLATFORMS and name not in platforms and DIGEST.fullmatch(str(entry.get('digest', ''))),
                'PLATFORM_SET_INVALID', f'manifest inesperado/duplicado no índice: {name}', base)
        platforms[name] = entry['digest']
    require(sorted(platforms) == list(PLATFORMS) and len({digest, *platforms.values()}) == 3,
            'PLATFORM_SET_INVALID', 'índice deve conter exatamente amd64 e arm64, distintos do índice', base)
    signature = load('signature.json')
    require(type(signature) is list and signature, 'INSUFFICIENT_EVIDENCE', 'assinatura sem registro verificado', base)
    provenance = load('provenance.json')
    require(type(provenance) is list and provenance, 'INSUFFICIENT_EVIDENCE', 'provenance sem registro verificado', base)
    for statement in statements(provenance):
        subjects = [s.get('digest', {}).get('sha256') for s in (statement or {}).get('subject', [])
                    if type(s) is dict and type(s.get('digest')) is dict]
        require(digest[7:] in subjects, 'PROVENANCE_SUBJECT_MISMATCH',
                'statement de provenance verificado não tem o índice como subject', base)
    checks = {'signature': 'PASS', 'provenance': 'PASS', 'platforms': 'PASS', 'repository_ids': 'PASS',
              'release_binding': 'NOT_REQUESTED'}
    invocations = sorted({((s or {}).get('predicate', {}).get('runDetails', {}).get('metadata', {})
                           .get('invocationId')) for s in statements(provenance)} - {None})
    if release is not None:
        expected = (f'https://github.com/{signer}/actions/runs/{release["run_id"]}'
                    f'/attempts/{release["run_attempt"]}')
        require(expected in invocations, 'PROVENANCE_RELEASE_MISMATCH',
                f'provenance não vincula a execução aprovada {expected} (observado: {invocations})', base)
        checks['release_binding'] = 'PASS'
    evidence = {p.name: sha256(p.read_bytes()) for p in sorted(reports.iterdir()) if p.is_file()}
    return checks, evidence, platforms, signer, invocations


def full_policy_worker(args):
    """Processo isolado (-I): importa verify_promotion somente do checkout revisado."""
    checkout = Path(args.factory_checkout).resolve()
    sys.path.insert(0, str(checkout))

    def fail(code, message):
        print(json.dumps({'code': code, 'message': message}, ensure_ascii=False), file=sys.stderr)
        return 1

    try:
        from scripts.pipeline.release import verify_promotion as module  # noqa: PLC0415 - import do checkout
        if not Path(module.__file__).resolve().is_relative_to(checkout):
            return fail('FACTORY_CHECKOUT_UNTRUSTED', f'verify_promotion importado de {module.__file__}')
        module.verify_promotion(args.image, args.repository, Path(args.reports), source_sha=args.source_sha)
    except subprocess.CalledProcessError as error:
        tool = Path(str(error.cmd[0])).name if error.cmd else '?'
        code = {'cosign': 'SIGNATURE_REJECTED', 'gh': 'PROVENANCE_REJECTED'}.get(tool, 'INDEX_UNAVAILABLE')
        detail = (error.stderr or '').strip().splitlines()[-1:] if isinstance(error.stderr, str) else []
        return fail(code, f'{tool} recusou a verificação (exit {error.returncode}) {" ".join(detail)}'.strip())
    except FileNotFoundError as error:
        return fail('VERIFIER_UNAVAILABLE', f'ferramenta ausente: {error.filename or error}')
    except ValueError as error:
        text = str(error)
        code = ('PLATFORM_SET_INVALID' if 'plataforma' in text or 'índice' in text or 'amd64' in text
                else 'INSUFFICIENT_EVIDENCE' if 'nenhuma evidência' in text
                else 'PROVENANCE_REJECTED' if 'provenance' in text
                else 'VERIFIER_FAILED')
        return fail(code, text)
    except Exception as error:  # noqa: BLE001 - qualquer outra falha é recusa fechada
        return fail('VERIFIER_FAILED', f'{type(error).__name__}: {error}')
    return 0


# ---------------------------------------------------------------------------
# verify: resolve, verifica e grava record + lock
# ---------------------------------------------------------------------------

def command_verify(args):
    out = Path(args.out)
    if out.exists() or out.is_symlink():
        print(f'--out deve ser um diretório novo: {out}', file=sys.stderr)
        return 2
    out.mkdir(parents=True, mode=0o700)
    work = out / 'evidence'
    work.mkdir(mode=0o700)
    record = dict(schema_version=SCHEMA_VERSION, tool='audited-consumer', tool_version=TOOL_VERSION,
                  started_at=now(), status='BLOCKED', level=None, policy=None, release_record=None,
                  factory_checkout=None, verifier_script=None, bases={}, pair=None, diagnostics=[],
                  limitations=list(LIMITATIONS))
    try:
        policy, raw_policy = load_policy(args.policy)
        record['level'] = policy['verification_level']
        record['policy'] = dict(path=str(args.policy), sha256=sha256(raw_policy))
        release = None
        if args.release_record:
            release, raw_release = load_release(args.release_record, policy)
            record['release_record'] = dict(path=str(args.release_record), sha256=sha256(raw_release),
                                            source_sha=release['source_sha'], run_id=release['run_id'],
                                            run_attempt=release['run_attempt'])
        requested = {'runtime': args.runtime, 'build': args.build}
        for name, value in requested.items():
            if value is not None and name not in policy['bases']:
                raise usage_error('INPUT_INVALID', f'--{name} informado, mas a política não declara a base {name}')
        script = None
        if uses_verify_image(policy):
            require(args.verifier_script is not None, 'INPUT_INVALID', '--verifier-script é obrigatório', None, 2)
            script = pinned_script(args.verifier_script, policy['verifier_script_sha256'], work)
            record['verifier_script'] = dict(path=str(args.verifier_script), sha256=policy['verifier_script_sha256'])
        checkout = None
        if policy['verification_level'] == 'full-policy':
            require(args.factory_checkout is not None, 'INPUT_INVALID', '--factory-checkout é obrigatório', None, 2)
            checkout = checkout_identity(args.factory_checkout, policy['factory_checkout_commit'],
                                         policy['verifier_timeout_seconds'])
            record['factory_checkout'] = dict(path=str(checkout), commit=policy['factory_checkout_commit'])

        for base in ('runtime', 'build'):
            if base not in policy['bases']:
                continue
            framework = policy['bases'][base]['framework']
            entry = dict(framework=framework, build_arg=policy['bases'][base]['build_arg'], input=None,
                         resolution=None, digest=None, image_ref=None, platforms=None, checks=None, evidence=None)
            record['bases'][base] = entry
            value = requested[base]
            approved = release['images'].get(framework) if release else None
            if value is None and approved is None:
                raise usage_error('INPUT_MISSING', f'sem referência para {base} ({framework})')
            if value is not None and not (DIGEST.fullmatch(value) or TAG.fullmatch(value)):
                raise usage_error('REFERENCE_INVALID', f'--{base} aceita só tag ou sha256:<digest>: {value!r}')
            if value is None:
                entry['input'] = dict(kind='release-record', value=approved)
                digest = approved
            elif DIGEST.fullmatch(value):
                entry['input'] = dict(kind='digest', value=value)
                digest = value
            else:
                entry['input'] = dict(kind='tag', value=value)
                digest = resolve_tag(policy, framework, value, base)
                entry['resolution'] = dict(method='aws ecr describe-images', at=now(), digest=digest)
            if approved is not None and digest != approved:
                raise GateError('DIGEST_MISMATCH', f'{base}: referência resolve para {digest}, '
                                f'mas a release aprovada fixa {approved}', base)
            entry['digest'], entry['image_ref'] = digest, image_ref(policy, framework, digest)
            if policy['verification_level'] == 'simplified':
                checks, evidence = verify_image_script(policy, base, framework, digest, script, work,
                                                       policy['source_repository'])
                checks.update(platforms='NOT_CHECKED', repository_ids='NOT_CHECKED',
                              release_binding='NOT_CHECKED')
                entry['invocations'] = None
            else:
                checks, evidence, platforms, signer, invocations = full_policy(
                    policy, base, framework, digest, checkout, release, work)
                entry.update(platforms=platforms, signer_repository=signer, invocations=invocations)
                if policy['require_sbom_attestation']:
                    sbom, sbom_evidence = verify_image_script(policy, base, framework, digest, script, work, signer)
                    checks['sbom_attestation'] = sbom['sbom_attestation']
                    evidence.update({'verify-image/' + k: v for k, v in sbom_evidence.items()})
                else:
                    checks['sbom_attestation'] = 'NOT_REQUIRED'
            entry['checks'], entry['evidence'] = checks, evidence

        pair = dict(compatible=True, same_release='NOT_APPLICABLE')
        if 'build' in record['bases']:
            if policy['verification_level'] == 'full-policy':
                runtime, build = (set(record['bases'][b]['invocations']) for b in ('runtime', 'build'))
                require(bool(runtime & build), 'PAIR_RELEASE_MISMATCH',
                        'runtime e -dev não compartilham a mesma execução de build na provenance verificada')
                pair['same_release'] = 'PASS'
            else:
                pair['same_release'] = 'NOT_CHECKED'
        record['pair'] = pair
        record['status'] = 'TRUSTED'
    except GateError as error:
        record['diagnostics'].append(dict(code=error.code, base=error.base, message=str(error)))
        record['finished_at'] = now()
        (out / 'verification-record.json').write_bytes(render(record))
        print(f'BLOCKED {error.code}: {error}', file=sys.stderr)
        return error.exit_code
    except Exception as error:  # noqa: BLE001 - erro inesperado é recusa fechada, nunca sucesso
        record['diagnostics'].append(dict(code='UNEXPECTED_ERROR', base=None, message=f'{type(error).__name__}: {error}'))
        record['finished_at'] = now()
        (out / 'verification-record.json').write_bytes(render(record))
        print(f'BLOCKED UNEXPECTED_ERROR: {error}', file=sys.stderr)
        return 1

    record['finished_at'] = now()
    raw_record = render(record)
    (out / 'verification-record.json').write_bytes(raw_record)
    lock = dict(schema_version=SCHEMA_VERSION, status='TRUSTED', level=record['level'],
                record='verification-record.json', record_sha256=sha256(raw_record),
                build_args={entry['build_arg']: entry['image_ref'] for entry in record['bases'].values()},
                bases={name: dict(framework=entry['framework'], image_ref=entry['image_ref'],
                                  digest=entry['digest'], platforms=entry['platforms'])
                       for name, entry in record['bases'].items()})
    temporary = out / '.verified-bases.lock.json.tmp'
    temporary.write_bytes(render(lock))
    os.replace(temporary, out / 'verified-bases.lock.json')
    print(f'TRUSTED {record["level"]}: ' + ' '.join(lock['build_args'][k] for k in sorted(lock['build_args'])))
    return 0


# ---------------------------------------------------------------------------
# lock: leitura conferida, build args e Dockerfile
# ---------------------------------------------------------------------------

LOCK_KEYS = ('schema_version', 'status', 'level', 'record', 'record_sha256', 'build_args', 'bases')


def load_lock(path):
    path = Path(path)
    raw = read_regular(path, 'lock', 'LOCK_INVALID', exit_code=1)
    lock = strict_json(raw, 'lock', 'LOCK_INVALID', exit_code=1)
    if type(lock) is not dict or set(lock) != set(LOCK_KEYS):
        raise GateError('LOCK_INVALID', 'lock com campos divergentes')
    require(lock['status'] == 'TRUSTED' and lock['level'] in LEVELS and lock['record'] == 'verification-record.json'
            and type(lock['record_sha256']) is str and HEX64.fullmatch(lock['record_sha256']),
            'LOCK_INVALID', 'lock não representa uma verificação TRUSTED')
    raw_record = read_regular(path.parent / lock['record'], 'verification record', 'LOCK_TAMPERED', exit_code=1)
    require(sha256(raw_record) == lock['record_sha256'], 'LOCK_TAMPERED', 'record diverge do hash fixado no lock')
    record = strict_json(raw_record, 'verification record', 'LOCK_TAMPERED', exit_code=1)
    require(record.get('status') == 'TRUSTED' and record.get('level') == lock['level'], 'LOCK_TAMPERED',
            'record não é TRUSTED no mesmo nível do lock')
    bases = record.get('bases', {})
    expected_args = {entry['build_arg']: entry['image_ref'] for entry in bases.values()}
    require(lock['build_args'] == expected_args and type(lock['bases']) is dict
            and set(lock['bases']) == set(bases)
            and all(lock['bases'][name].get('image_ref') == entry['image_ref'] for name, entry in bases.items()),
            'LOCK_TAMPERED', 'lock diverge das referências verificadas no record')
    for value in lock['build_args'].values():
        require(IMAGE_REF.fullmatch(value) is not None, 'LOCK_INVALID', f'referência sem digest: {value}')
    return lock, record


def command_build_args(args):
    try:
        lock, _ = load_lock(args.lock)
        if args.require_level == 'full-policy':
            require(lock['level'] == 'full-policy', 'LEVEL_INSUFFICIENT',
                    'lock verificado só no nível simplified; a política exige full-policy')
    except GateError as error:
        print(f'BLOCKED {error.code}: {error}', file=sys.stderr)
        return error.exit_code
    if args.format == 'json':
        sys.stdout.write(json.dumps(lock['build_args'], sort_keys=True) + '\n')
    else:
        for name in sorted(lock['build_args']):
            sys.stdout.write(f'--build-arg\n{name}={lock["build_args"][name]}\n')
    return 0


def logical_lines(text):
    """Instruções do Dockerfile com continuações unidas; comentários ignorados."""
    lines, current, directives = [], '', True
    for raw in text.splitlines():
        stripped = raw.strip()
        if directives and re.match(r'#\s*[A-Za-z]+\s*=', stripped):
            key, value = (part.strip() for part in stripped[1:].split('=', 1))
            if key.lower() == 'escape' and value != '\\':
                raise GateError('DOCKERFILE_UNSUPPORTED', 'diretiva escape diferente de \\ não é suportada')
            if key.lower() == 'syntax' and DIGEST.search(value) is None:
                raise GateError('DOCKERFILE_UNPINNED_FRONTEND', f'frontend BuildKit sem digest: {value}')
            continue
        directives = False
        if not stripped or stripped.startswith('#'):
            continue
        if stripped.endswith('\\'):
            current += stripped[:-1] + ' '
            continue
        lines.append(current + stripped)
        current = ''
    if current.strip():
        lines.append(current.strip())
    return lines


def check_dockerfile(text, build_args, runtime_arg):
    findings, global_args, stages = [], {}, []
    names = {}

    def finding(code, message):
        findings.append(dict(code=code, message=message))

    for line in logical_lines(text):
        instruction, _, rest = line.partition(' ')
        instruction, rest = instruction.upper(), rest.strip()
        if instruction == 'ARG' and not stages:
            for token in rest.split():
                name, has_default, _ = token.partition('=')
                global_args[name] = bool(has_default)
            continue
        if instruction == 'FROM':
            match = re.fullmatch(r'(?:--platform=(\S+)\s+)?(\S+)(?:\s+[Aa][Ss]\s+([A-Za-z0-9][A-Za-z0-9_.-]*))?', rest)
            if match is None:
                finding('DOCKERFILE_UNSUPPORTED', f'FROM não reconhecido: {line}')
                stages.append(None)
                continue
            image, alias = match.group(2), match.group(3)
            variable = re.fullmatch(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)', image)
            if variable:
                arg = variable.group(1) or variable.group(2)
                root = ('arg', arg)
                if arg not in build_args:
                    finding('DOCKERFILE_UNVERIFIED_FROM', f'FROM usa ${arg}, que não vem do lock verificado')
                elif arg not in global_args:
                    finding('DOCKERFILE_UNDECLARED_ARG', f'ARG {arg} não declarado antes do primeiro FROM')
                elif global_args[arg]:
                    finding('DOCKERFILE_ARG_DEFAULT', f'ARG {arg} tem default; sem o lock o build usaria outra imagem')
            elif image.lower() in names:
                root = names[image.lower()]
            elif image == 'scratch':
                root = ('scratch', None)
            else:
                root = ('external', image)
                finding('DOCKERFILE_UNVERIFIED_FROM', f'FROM {image} não é base verificada pelo lock')
            if '$' in image and not variable:
                finding('DOCKERFILE_ARG_DEFAULT', f'expansão com default/modificador não permitida: {image}')
            if alias:
                names[alias.lower()] = root
            stages.append(root)
            continue
        if instruction in ('COPY', 'ADD', 'RUN'):
            for value in re.findall(r'--from=(\S+)', rest) + re.findall(r'--mount=\S*?\bfrom=([^,\s]+)', rest):
                if value.lower() not in names and not value.isdigit():
                    finding('DOCKERFILE_EXTERNAL_IMAGE', f'{instruction} usa imagem externa não verificada: {value}')
            if instruction == 'ADD' and re.search(r'(?:^|\s)(?:https?://|git@|[a-z]+://)', rest) \
                    and '--checksum=sha256:' not in rest:
                finding('DOCKERFILE_REMOTE_ADD', 'ADD remoto sem --checksum=sha256 não tem identidade fixada')
    if not stages:
        finding('DOCKERFILE_UNSUPPORTED', 'Dockerfile sem FROM')
    elif stages[-1] != ('arg', runtime_arg):
        finding('DOCKERFILE_FINAL_STAGE_NOT_RUNTIME', f'estágio final deve derivar de ${runtime_arg} (runtime verificado), '
                f'não de {stages[-1]}')
    return findings, stages


def command_check_dockerfile(args):
    try:
        lock, record = load_lock(args.lock)
        runtime_arg = record['bases']['runtime']['build_arg']
        text = read_regular(args.dockerfile, 'Dockerfile', 'DOCKERFILE_INVALID', exit_code=1).decode('utf-8')
        findings, stages = check_dockerfile(text, set(lock['build_args']), runtime_arg)
    except GateError as error:
        findings, stages = [dict(code=error.code, message=str(error))], []
    except UnicodeError:
        findings, stages = [dict(code='DOCKERFILE_INVALID', message='Dockerfile não é UTF-8')], []
    result = dict(schema_version=SCHEMA_VERSION, status='PASS' if not findings else 'FAIL',
                  dockerfile=str(args.dockerfile), findings=findings,
                  stages=[None if s is None else dict(kind=s[0], value=s[1]) for s in stages])
    sys.stdout.write(render(result).decode('utf-8'))
    return 0 if not findings else 1


def command_record_consumption(args):
    target = Path(args.out)
    try:
        lock, _ = load_lock(args.lock)
        require(not target.exists() and not target.is_symlink(), 'INPUT_INVALID', f'{target} já existe', None, 2)
        image_id = args.image_id.strip()
        require(DIGEST.fullmatch(image_id) is not None, 'INPUT_INVALID', 'image id deve ser sha256:<hex>', None, 2)
    except GateError as error:
        print(f'BLOCKED {error.code}: {error}', file=sys.stderr)
        return error.exit_code
    status = 'PASS' if args.build == 'PASS' and args.smoke == 'PASS' else 'FAIL'
    record = dict(schema_version=SCHEMA_VERSION, status=status, level=lock['level'],
                  lock_sha256=sha256(read_regular(args.lock, 'lock', 'LOCK_INVALID', exit_code=1)),
                  build_args=lock['build_args'], platform=args.platform, image_id=image_id,
                  build_and_tests=args.build, smoke=args.smoke, recorded_at=now(),
                  limitations=list(LIMITATIONS))
    target.write_bytes(render(record))
    return 0 if status == 'PASS' else 1


def main(argv=None):
    if os.name != 'posix':
        print('audited_consumer.py requer POSIX (Linux/macOS)', file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    verify = commands.add_parser('verify', help='resolve uma vez, verifica e grava record + lock')
    verify.add_argument('--policy', required=True, type=Path)
    verify.add_argument('--out', required=True, type=Path, help='diretório novo (0700) para record, lock e evidências')
    verify.add_argument('--runtime', help='tag ou sha256:<digest> da base runtime')
    verify.add_argument('--build', help='tag ou sha256:<digest> da base -dev')
    verify.add_argument('--release-record', type=Path, help='release aprovada: digests, commit e run/attempt')
    verify.add_argument('--factory-checkout', type=Path, help='checkout revisado da Factory (full-policy)')
    verify.add_argument('--verifier-script', type=Path, help='cópia do scripts/verify-image.sh fixada por sha256')
    build_args = commands.add_parser('build-args', help='build args do lock conferido')
    build_args.add_argument('--lock', required=True, type=Path)
    build_args.add_argument('--require-level', choices=LEVELS)
    build_args.add_argument('--format', choices=('lines', 'json'), default='lines')
    dockerfile = commands.add_parser('check-dockerfile', help='FROM somente pelas bases do lock; final = runtime')
    dockerfile.add_argument('--lock', required=True, type=Path)
    dockerfile.add_argument('--dockerfile', required=True, type=Path)
    consumption = commands.add_parser('record-consumption', help='evidência JSON do que foi consumido')
    consumption.add_argument('--lock', required=True, type=Path)
    consumption.add_argument('--out', required=True, type=Path)
    consumption.add_argument('--image-id', required=True)
    consumption.add_argument('--platform', required=True)
    consumption.add_argument('--build', required=True, choices=('PASS', 'FAIL'))
    consumption.add_argument('--smoke', required=True, choices=('PASS', 'FAIL', 'NOT_RUN'))
    worker = commands.add_parser('_full-policy-worker', help=argparse.SUPPRESS)
    worker.add_argument('--factory-checkout', required=True)
    worker.add_argument('--image', required=True)
    worker.add_argument('--repository', required=True)
    worker.add_argument('--reports', required=True)
    worker.add_argument('--source-sha')
    args = parser.parse_args(argv)
    handlers = {'verify': command_verify, 'build-args': command_build_args,
                'check-dockerfile': command_check_dockerfile, 'record-consumption': command_record_consumption,
                '_full-policy-worker': full_policy_worker}
    return handlers[args.command](args)


if __name__ == '__main__':
    raise SystemExit(main())
