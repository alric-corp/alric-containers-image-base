#!/usr/bin/env python3
"""Verify final compiled-pair outcomes, complementing pre-write authorization.

Incomplete compiled requests fail closed. Interpreted frameworks retain
independent promotion semantics, including their optional -dev variants.
"""
import argparse
import json
from pathlib import Path
import sys

from scripts.pipeline.release.verify_promotion_pair import require, verify_pair
from scripts.pipeline.runtime.runtime_images import publication_contract


def discover_pairs(frameworks):
    """Compiled relationships only; interpreted -dev variants remain independent."""
    resolutions = [publication_contract(name, frameworks) for name in frameworks]
    return sorted({item['runtime_framework'] for item in resolutions if item['dev_framework']})


def verify_completed_pair(runtime, dev):
    members = (runtime, dev)
    if all(member.get('skipped') is True for member in members):
        require(all(member.get('promoted') is False
                    and member.get('write_status') == 'not_run'
                    and member.get('candidate_digest') is None
                    and not member.get('error') for member in members),
                'skipped pair contains a mutation or candidate')
        return {'status': 'PAIR_SKIPPED', 'runtime_repository': runtime.get('repository'),
                'dev_repository': dev.get('repository')}
    result = verify_pair(runtime, dev)
    require(all(member.get('promoted') is True
                and member.get('write_status') == 'completed'
                and member.get('read_back_status') == 'confirmed'
                and member.get('candidate_digest') == member.get('digest')
                and member.get('candidate_digest') == member.get('stable_digest_observed')
                for member in members), 'pair promotion requires both writes and exact stable read-backs')
    return result


def load_evidence(evidence_dir, framework, attempt):
    path = Path(evidence_dir) / f'promotion-{framework}-{attempt}' / 'promotion-evidence.json'
    if not path.is_file():
        raise ValueError(f"evidência de promoção ausente para '{framework}' em {path}")
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frameworks', help='JSON array dos frameworks pedidos neste run')
    parser.add_argument('evidence_dir', help='diretório com os artifacts promotion-<framework>-<attempt> baixados')
    parser.add_argument('attempt', help='github.run_attempt deste run')
    parser.add_argument('--json', dest='json_output', type=Path)
    args = parser.parse_args()

    try:
        frameworks = json.loads(args.frameworks)
        pairs = discover_pairs(frameworks)
    except (ValueError, TypeError) as error:
        print(f'promotion pair scope failed: {error}', file=sys.stderr)
        return 1
    if not pairs:
        print('nenhum par runtime/-dev solicitado neste run -- nada a verificar')
        if args.json_output:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(json.dumps({'pairs': []}, indent=2) + '\n')
        return 0

    results = []
    failures = []
    for runtime in pairs:
        dev = f'{runtime}-dev'
        try:
            runtime_evidence = load_evidence(args.evidence_dir, runtime, args.attempt)
            dev_evidence = load_evidence(args.evidence_dir, dev, args.attempt)
            result = verify_completed_pair(runtime_evidence, dev_evidence)
            print(f'{runtime} / {dev}: {result["status"]}')
            results.append(result)
        except ValueError as error:
            print(f'{runtime} / {dev}: FAIL -- {error}', file=sys.stderr)
            failures.append({'pair': [runtime, dev], 'error': str(error)})

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps({'pairs': results, 'failures': failures}, indent=2) + '\n')

    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
