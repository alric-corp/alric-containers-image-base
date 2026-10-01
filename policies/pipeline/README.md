# Configuração da Factory

A fonte da verdade fica nos três JSONs versionados desta pasta. Cada workflow
lê a revisão em execução. Repository Variables e Environment Variables do
GitHub não participam da resolução desses valores.

| Arquivo | Responsabilidade |
| --- | --- |
| [`config.json`](config.json) | Repositório, branch, identidade OIDC, contas, regiões, roles, buckets de releases e backend Terraform |
| [`promote-dev.json`](promote-dev.json) | Habilitação, frameworks elegíveis e soak de candidate validado até DEV `stable` |
| [`promote-hom.json`](promote-hom.json) | Habilitação, frameworks elegíveis e soak de DEV `stable` até HOM `stable` |

## Políticas de promoção

Os dois arquivos usam o mesmo formato:

```json
{
  "schema_version": 1,
  "enabled": true,
  "frameworks": ["go1-26", "go1-26-dev"],
  "soak_hours": 0
}
```

| Política inicial | Habilitada | Frameworks | Soak |
| --- | --- | --- | --- |
| DEV | `true` | `go1-26`, `go1-26-dev` | `0` horas após concluir validações, trust e testes consumidores |
| HOM | `false` | `go1-26`, `go1-26-dev` | `6` horas após confirmar todas as tags DEV `stable` |

`frameworks` é a lista de imagens elegíveis para promoção naquele destino.
Ela deve conter nomes existentes no catálogo, sem repetições, e pares
runtime/`-dev` completos, inclusive Node. Python é singleton. Todos os membros
do manifesto precisam estar na lista; o promotor nunca recorta uma release.
DEV e HOM podem ter listas diferentes.

O lote diário atual constrói o par Go 1.26. O dispatch de certificação constrói
as 16 imagens. Para promover esse manifesto completo, as duas políticas
precisam autorizar seus 16 membros. Caso contrário, o candidate validado fica
persistido aguardando uma política compatível, sem atualizar `stable`.

`soak_hours` aceita horas inteiras ou fracionárias finitas: DEV permite zero;
HOM mantém o mínimo de seis horas. O limite máximo é um ano. Retenção de
artifacts continua sendo uma restrição independente: DEV expira builds após
sete dias e uma release expirada falha fechado na verificação.

### Retomada do soak DEV

Depois dos gates, a Factory persiste o candidate e as evidências em
`releases/r<RUN>-a<ATTEMPT>/candidate.json` no bucket DEV, por escrita imutável.
Com soak zero e escopo autorizado, pode atualizar DEV `stable` no mesmo run.
Com soak pendente, habilitação desligada ou escopo incompatível, registra
`WAITING` e encerra o job. `dev-stable.yml` agenda uma nova seleção no minuto
7 de cada hora. Não existe runner aguardando o tempo de soak.

Ao retomar, usa os mesmos digests e evidências, repete trust, scan e read-back,
respeita pausas e a maior release já promovida e só então grava o manifesto
`DEV_STABLE`. Nesse momento começa o relógio independente de HOM. O cron HOM
continua no minuto 17. Ambos também aceitam dispatch por release exata.

```sh
gh workflow run dev-stable.yml --ref develop -f release=r123456-a1
```

Uma escrita DEV interrompida mantém todos os membros pausados. Depois da
triagem da evidência, o dispatch com release explícita e
`-F resume-automation=true` permite repetir todos os gates e reconciliar a
release. O schedule não remove essa pausa. Recovery HOM continua disponível
por dispatch mesmo quando a promoção HOM está desabilitada.

## Identidades e infraestrutura

Os ARNs são derivados de conta e nome da role em `config.json`. Os GitHub
Environments `DEV`, `HOM` e `lab-image-base-infra` continuam impondo os limites
de execução, revisão e OIDC. Credenciais e tokens ficam em OIDC ou secrets.

`infra.plan_enabled=false` preserva a desativação indicada pela ausência da
antiga variável `INFRA_PLAN_ROLE_ARN`. Sua habilitação exige concluir a retirada
dos caminhos históricos de Infra PR descrita no runbook. Alterar um JSON não
provisiona recursos nem muda trust IAM automaticamente.

O carregador `scripts.pipeline.governance.configuration` valida os arquivos
antes de emitir outputs/env para o job. Arquivo ausente, chave duplicada, campo
desconhecido, booleano textual, conta inválida, framework fora do catálogo ou
par incompleto interrompem a execução. Não há fallback para variáveis externas
ou arquivos antigos.

```sh
python3 -B -m scripts.pipeline.governance.configuration --scope DEV
python3 -B -m scripts.pipeline.governance.configuration --scope HOM
python3 -B -m scripts.pipeline.governance.configuration --scope INFRA_PLAN
```

## Habilitar HOM e alterar políticas

Altere `enabled` para `true` em `promote-hom.json` por PR. Modificações em
frameworks, soak e identidades também são mudanças de configuração da Factory
revisadas em PR. O lifecycle normal de cada release continua automático,
sem PR e sem rebuild. Runs históricos conservam a configuração da revisão
original; para bloquear também reexecuções históricas em uma emergência,
use o controle IAM da role.

## Migração das variáveis existentes

Primeiro integre os workflows deste PR em `develop`. Até isso ocorrer, a versão
publicada ainda depende das variáveis antigas. Depois do merge, elas podem ser
removidas de Settings → Secrets and variables → Actions e dos Environments:

- Repositório: `AWS_ACCOUNT_ID`, `AWS_REGION`, `AWS_ROLE_ARN`, `DEV_ACCOUNT_ID`,
  `DEV_REGION`, `DEV_ROLE_ARN`, `HOM_ACCOUNT_ID`, `HOM_REGION`, `HOM_ROLE_ARN`,
  `INFRA_PLAN_ROLE_ARN`, `INFRA_APPLY_ROLE_ARN`, `INFRA_BACKEND_REGION`,
  `INFRA_TF_STATE_BUCKET`, `STABLE_PROMOTION_AUTHORIZED`.
- Environments DEV/HOM: `AWS_ACCOUNT_ID`, `AWS_REGION`, `AWS_ROLE_ARN`,
  `RELEASE_BUCKET`.

`infra/lifecycle/configure_github.py` configura as proteções dos Environments e
da branch, sem recriar essas variáveis. O read-back compara os três JSONs com
os documentos publicados em `develop`.
