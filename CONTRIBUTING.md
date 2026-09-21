# Contribuição e validação local

Comece pelo [mapa de responsabilidades](docs/repository-architecture.md).
Regras do produto ficam em `scripts/pipeline/`, configuração em `policies/`
e composição de jobs em `.github/workflows/`. Os testes unitários espelham os
domínios; integração e execução real de imagens são camadas separadas.

## Ambiente

Python 3.9 ou superior, Git, Make e OpenSSL executam os testes unitários
(OpenSSL faz parsing da signing key RSA pública; sem Docker ou rede). A dependência
Python da automação é fixada em `requirements-dev.txt`; não entra nas imagens.
Use um ambiente virtual para não modificar o Python do sistema:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
make test-unit lint-local
```

Para integração, instale Bash, OpenSSL com `req -addext`, jq, sha256sum e GNU
date (`gdate` no macOS). O teste TLS abre uma porta local. Certificados são
sintéticos e os downloads são substituídos por fixtures; não usa AWS.
`make lint-workflows` usa actionlint e seu ShellCheck, se disponível. O CI
executa actionlint em uma imagem fixada por digest.

O workflow **CI - Repository checks** é o gate rápido obrigatório em Linux:
testes unitários, integração offline, sintaxe/hardening de GitHub Actions,
governança de dependências imutáveis e contratos do repositório. Não publica
imagens, assume roles AWS de publicação, aplica Terraform nem executa o
golden path hospedado. Windows/Git Bash é uma opção para testes locais de
desenvolvimento; não há CI hospedado Windows. O destino corporativo previsto
é Linux em runners self-hosted efêmeros no Kubernetes, via Actions Runner
Controller (ARC).

Os IDs dos jobs continuam `test` e `lint-workflows`; os nomes exibidos são
`Unit & integration tests` e `Repository & workflow lint`. GitHub usa esses
nomes exibidos nos check runs: a configuração de required checks deve ser
alinhada na entrada aprovada em main, mantendo a exigência dos dois gates.
O analisador `ci_timing` usa os nomes atuais por padrão; para histórico,
informe `--required test,lint-workflows` explicitamente.

## Dependência revisada do executor compartilhado

A origem aprovada de `alric-corp/alric-containers-reusable-workflows` fica em
[policies/governance/reusable-workflows.json](policies/governance/reusable-workflows.json).
`scripts/pipeline/governance/workflow_dependencies.py` confere, só a partir
dos arquivos deste repositório: essa origem, o SHA completo e único
compartilhado pelos dois chamadores (`validate-base-images.yml`,
`test-runtime-images.yml`), ausência de refs móveis, os inputs exatos enviados
pelos chamadores (incluindo `locked-build: true`), o alinhamento da action
Trivy interna entre promoção/recuperação e o grupo do Dependabot. Nada aqui
clona, abre ou lê o repositório compartilhado — `git clone` deste
repositório sozinho já é suficiente para `make check` e `make lint-workflows`
passarem, com Python, dependências de desenvolvimento, Git Bash no Windows,
GNU Make e actionlint instalados. A implementação do executor compartilhado,
seu contrato interno de inputs/outputs,
hardening, actionlint e retenção de artifacts são verificados pelo CI do
próprio `alric-containers-reusable-workflows`
([contrato de reuso](docs/repository-architecture.md#fronteira-entre-produto-e-workflows-compartilhados)),
não duplicados aqui.

## Comandos

| Comando | Escopo |
| --- | --- |
| `make test-unit` | Regras Python, arquitetura e filtros de CI; sem infraestrutura |
| `make test-integration` | Certificados, TLS, adaptadores e retenção dos workflows locais |
| `make lint-local` | Hardening, origem/SHA/inputs/tooling dos chamadores do executor compartilhado, cobertura/consistência dos pins, retenção e lote padrão do catálogo |
| `make lint-workflows` | actionlint nos YAML deste repositório |
| `make check` | `test` + `lint-local` + `lint-workflows` |
| `make list` / `make build FRAMEWORK=...` | Catálogo e build local com Docker |

`PYTHON` e `ACTIONLINT` podem ser sobrescritos para instalações locais.
Os [contratos runtime](tests/runtime/README.md) exigem Docker e artifacts OCI
validados. Eles são executados no pipeline de imagens e não fazem parte do
`make check`.

## Critérios para mudanças

- Altere cada regra em seu módulo canônico; adaptadores não recebem lógica.
- Uma nova dependência entre domínios exige justificar a fronteira e atualizar
  o teste de arquitetura. Não use `sys.path` para contorná-la.
- Preserve os IDs dos jobs e a cobertura dos filtros de build ao mover
  arquivos. Mudança de nome exibido exige alinhar os required checks sem
  remover gates. Novos testes precisam ser descobertos pelo comando do CI.
- Atualize os dois workflows compartilhados juntos, por SHA completo; confira
  também o SHA da action Trivy usado em promoção e recuperação.
- Políticas e pins passam por PR e revisão dos code owners. Não versione
  credenciais, chaves privadas, caches, ambientes virtuais ou saídas de build.
- Registre evidências com commit e escopo da execução. Testes locais não
  equivalem a publicação ECR nem a promoção/recuperação real de stable.
