# Testes de regressão

O workflow `ci.yml` executa as verificações em todo PR e push para
`main`, sem filtro de paths e com `contents: read`. Ele usa os mesmos alvos
Make disponíveis localmente. Preparação do ambiente e checkout do executor:
[CONTRIBUTING.md](../CONTRIBUTING.md).

| Camada | Local | Dependências |
| --- | --- | --- |
| Unitária | `unit/pipeline/` | Python, PyYAML e fixtures locais; sem Docker, AWS, sockets ou rede |
| Integração | `integration/` | Certificados sintéticos/OpenSSL, TLS local, CLIs reais e checkout do executor fixado |
| Runtime | `runtime/` | Docker, OCI validado, OpenSSL e execução/emulação das duas arquiteturas |

```sh
make test-unit
make test-integration
make check
```

Os testes Python são pacotes regulares com `__init__.py`; a descoberta parte
da camada e usa `-t .`. Isso evita colisões de nomes entre testes e imports
que dependem do diretório de execução.

## Regras de pipeline

A suíte unitária cobre candidatos e soak, prevenção de rollback, identidade
por digest, OCI, scan nas duas arquiteturas, assinatura/provenance, entradas,
hardening, pins, cache, readiness, contratos funcionais, resumos e saúde.
Ferramentas e APIs externas são substituídas nos testes.

Os testes de arquitetura verificam a direção das dependências, os pacotes de
domínio, a descoberta dos testes, a ausência de regras nos adaptadores e a
cobertura dos arquivos movidos pelos filtros de CI.

## Integração

- Os testes do executor compartilhado verificam SHA, conteúdo, inputs, Trivy,
  retenção e os caminhos de scripts usados pelo release publicado. Checkout
  ausente ou divergente falha o check.
- Os adaptadores antigos são executados como CLIs sem `PYTHONPATH`. A API de
  runtime usada pelo workflow compartilhado também é importada em processo real.
- O teste TLS cria certificado e servidor locais e comprova confiança na CA e
  resposta após readiness; requer permissão para abrir uma porta local.
- Certificados executam `scripts/certificates/certificados.sh` de verdade com
  CAs sintéticas, incluindo bundle com múltiplos certificados. `aws` e `curl`
  são substituídos por cópias locais; chaves e saídas temporárias são removidas.

A suíte de certificados exige Bash, OpenSSL com `req -addext`, jq, sha256sum e
GNU date (`gdate` no macOS). Dependência ausente falha explicitamente.
Ela cobre baseline e JSON, checksum repetível, lockfile ausente/relativo/vazio/
duplicado/malformado, rotação bloqueada até pin explícito, PEM sem newline,
metadados divergentes e falha de gravação durante o pin.

`--pin` atualiza checksum e metadados sequencialmente; não é uma transação
atômica. Se o segundo arquivo falhar, a verificação normal bloqueia o par
divergente. Recupere os dois pelo Git ou repita o pin após revisão.

## Contratos de imagens reais

Os [contratos runtime](runtime/README.md) constroem/rodam aplicações reais nas
imagens candidatas e registram execução nativa e emulada. Fazem parte do
pipeline de imagens, não de `make check`.

Testes locais não substituem build Melange/Apko, integração S3/ECR, revisão da
legitimidade de CAs, promoção/recuperação de stable ou validação TLS no
ambiente consumidor. Histórico e aceites pendentes ficam na
[RFC-013](../RFC-013-Image-Base-Completa-com-Mermaid.md).
