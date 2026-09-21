#!/usr/bin/env python3
"""Confirma que os candidatos de promoção runtime/dev vêm do mesmo build run.

RFC-013/ADR-0005: promover `image-base-go1-26:stable` e
`image-base-go1-26-dev:stable` de forma coordenada exige que os dois
apontem para o mesmo release aprovado -- não apenas para dois builds que,
cada um por conta própria, passaram na janela de soak. A tag de build
(`ddmmaa-hhmm-r<run_id>-a<attempt>`) já carrega essa identidade: este módulo
só extrai e compara o sufixo `r<run_id>-a<attempt>` das duas evidências de
promoção (`promotion-<framework>-<attempt>/promotion-evidence.json` do
batch de `promote-stable.yml`), e falha fechado se ele não existir ou não bater.

`promotion_batch.py` invokes this binding check after candidate selection and
BEFORE any stable write. The independent post-write verifier repeats it and
additionally requires both writes and digest read-backs to be confirmed.
"""
import argparse
import json
import re
import sys

from scripts.pipeline.release.find_promotion_candidate import is_build_tag


RUN_SUFFIX = re.compile(r'-r([1-9][0-9]*)-a([1-9][0-9]*)$')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run_identity(tag):
    """Extrai {run_id, attempt} do sufixo da tag de build, ou falha."""
    match = RUN_SUFFIX.search(tag or '')
    require(match is not None,
            f"tag {tag!r} não contém identificador de run (formato "
            "ddmmaa-hhmm-r<run_id>-a<attempt>) -- binding não verificável")
    require(is_build_tag(tag), 'tag de build inválida -- binding não verificável')
    return {'run_id': match[1], 'attempt': match[2]}


def verify_pair(runtime_evidence, dev_evidence):
    """Retorna o binding runtime/dev, ou levanta ValueError se não corresponderem."""
    require(runtime_evidence.get('skipped') is False,
            'runtime não tem candidato elegível nesta promoção')
    require(dev_evidence.get('skipped') is False,
            'dev não tem candidato elegível nesta promoção')

    runtime_tag = runtime_evidence.get('tag')
    dev_tag = dev_evidence.get('tag')
    runtime_run = run_identity(runtime_tag)
    dev_run = run_identity(dev_tag)
    require(runtime_run == dev_run,
            f"runtime (tag {runtime_tag!r}, run {runtime_run}) e dev "
            f"(tag {dev_tag!r}, run {dev_run}) vêm de builds diferentes -- "
            "não são o mesmo release aprovado; não promover automaticamente "
            "um par divergente")

    runtime_digest = runtime_evidence.get('candidate_digest')
    dev_digest = dev_evidence.get('candidate_digest')
    require(isinstance(runtime_digest, str) and runtime_digest,
            'runtime candidate_digest ausente na evidência')
    require(isinstance(dev_digest, str) and dev_digest,
            'dev candidate_digest ausente na evidência')

    return {
        'runtime_repository': runtime_evidence.get('repository'),
        'dev_repository': dev_evidence.get('repository'),
        'runtime_tag': runtime_tag,
        'dev_tag': dev_tag,
        'runtime_digest': runtime_digest,
        'dev_digest': dev_digest,
        'source_run_id': runtime_run['run_id'],
        'source_attempt': runtime_run['attempt'],
        'status': 'PAIR_BOUND',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime_evidence', type=argparse.FileType('r'),
                        help='reports/promotion-evidence.json do framework runtime')
    parser.add_argument('dev_evidence', type=argparse.FileType('r'),
                        help='reports/promotion-evidence.json do framework -dev')
    args = parser.parse_args()
    try:
        runtime_data = json.load(args.runtime_evidence)
        dev_data = json.load(args.dev_evidence)
        result = verify_pair(runtime_data, dev_data)
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        print(f'promotion pair binding failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
