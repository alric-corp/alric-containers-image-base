#!/usr/bin/env python3
"""Descobre pares runtime/-dev entre os frameworks promovidos num run e
verifica o binding de cada um com verify_promotion_pair.verify_pair.

Um framework sem par -dev solicitado no mesmo run (ex.: `python3-13`, que
não tem variante -dev) não é um par a verificar -- não é erro, é ausência
de par. Um par cujo -dev FOI solicitado no mesmo run, mas cuja evidência
está ausente ou incompleta, é uma falha: o par deveria ter sido promovido
coordenado.
"""
import argparse
import json
from pathlib import Path
import sys

from scripts.pipeline.release.verify_promotion_pair import verify_pair


def discover_pairs(frameworks):
    """Frameworks solicitados cujo par `<nome>-dev` também foi solicitado."""
    requested = set(frameworks)
    return sorted(name for name in requested
                 if not name.endswith('-dev') and f'{name}-dev' in requested)


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

    frameworks = json.loads(args.frameworks)
    pairs = discover_pairs(frameworks)
    if not pairs:
        print('nenhum par runtime/-dev solicitado neste run -- nada a verificar')
        if args.json_output:
            args.json_output.write_text(json.dumps({'pairs': []}, indent=2) + '\n')
        return 0

    results = []
    failures = []
    for runtime in pairs:
        dev = f'{runtime}-dev'
        try:
            runtime_evidence = load_evidence(args.evidence_dir, runtime, args.attempt)
            dev_evidence = load_evidence(args.evidence_dir, dev, args.attempt)
            result = verify_pair(runtime_evidence, dev_evidence)
            print(f'{runtime} / {dev}: PAIR_BOUND (run {result["source_run_id"]}, '
                 f'attempt {result["source_attempt"]})')
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
