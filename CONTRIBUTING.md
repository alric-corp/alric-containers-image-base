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

## Checkout da dependência revisada

Os checks de integração leem os workflows compartilhados do **mesmo commit**
usado pelos chamadores, na origem aprovada em
[policies/governance/reusable-workflows.json](policies/governance/reusable-workflows.json).
Prepare um checkout separado do seu trabalho local. O comando `checkout`
valida as referências locais antes de emitir outputs; não faz clone nem
valida os arquivos remotos nessa fase:

```sh
set -eu
python3 -B -m scripts.pipeline.governance.workflow_dependencies checkout
SHARED_REPOSITORY="$(python3 -B -c 'from scripts.pipeline.governance.workflow_dependencies import approved_repository; print(approved_repository())')"
SHARED_REF="$(python3 -B -c 'from scripts.pipeline.governance.workflow_dependencies import dependencies; print(dependencies()[0]["ref"])')"
git clone --no-checkout "https://github.com/${SHARED_REPOSITORY}.git" .reusable-workflows
git -C .reusable-workflows fetch origin "$SHARED_REF"
git -C .reusable-workflows checkout --detach "$SHARED_REF"
make check
```

Se o clone já existe, confira a URL `origin` contra a policy antes do fetch e
execute o checkout somente em uma árvore limpa. Não descarte trabalho existente.
Também é possível exportar `REUSABLE_WORKFLOWS_PATH` apontando para um checkout
existente: a variável escolhe apenas a localização, sem substituir origem ou
pin. `--root` seleciona a árvore de configuração em testes locais; não é um
override da origem por ambiente. No lint, origem divergente, checkout ausente,
SHA divergente ou bytes alterados nos dois YAMLs consumidos falham explicitamente.

A comparação local da URL de fetch, HEAD e conteúdo não prova publicação do
commit ou acesso privado. O resolvedor não fornece credenciais. Configurar o
acesso autorizado e verificar a execução no destino são etapas separadas do
[contrato de reuso](docs/repository-architecture.md#fronteira-entre-produto-e-workflows-compartilhados).

## Comandos

| Comando | Escopo |
| --- | --- |
| `make test-unit` | Regras Python, arquitetura e filtros de CI; sem infraestrutura |
| `make test-integration` | Certificados, TLS, adaptadores e contrato compartilhado |
| `make lint-local` | Hardening dos workflows, cobertura/consistência dos pins e lote padrão do catálogo |
| `make lint-shared` | Origem, SHA, inputs, Trivy, retenção e cron dos executores reais |
| `make lint-workflows` | actionlint nos YAML locais e compartilhados |
| `make check` | Todos os testes e lints acima |
| `make list` / `make build FRAMEWORK=...` | Catálogo e build local com Docker |

`PYTHON` e `ACTIONLINT` podem ser sobrescritos para instalações locais.
Os [contratos runtime](tests/runtime/README.md) exigem Docker e artifacts OCI
validados. Eles são executados no pipeline de imagens e não fazem parte do
`make check`.

## Critérios para mudanças

- Altere cada regra em seu módulo canônico; adaptadores não recebem lógica.
- Uma nova dependência entre domínios exige justificar a fronteira e atualizar
  o teste de arquitetura. Não use `sys.path` para contorná-la.
- Mantenha os nomes dos required checks e a cobertura dos filtros de build ao
  mover arquivos. Novos testes precisam ser descobertos pelo comando do CI.
- Atualize os dois workflows compartilhados juntos, por SHA completo; confira
  também o SHA da action Trivy usado em promoção e recuperação.
- Políticas e pins passam por PR e revisão dos code owners. Não versione
  credenciais, chaves privadas, caches, ambientes virtuais ou saídas de build.
- Registre evidências com commit e escopo da execução. Testes locais não
  equivalem a publicação ECR nem a promoção/recuperação real de stable.
