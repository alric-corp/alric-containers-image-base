# Factory Distroless V1: contrato IAM externo

A identidade operacional central é provisionada fora do Terraform: no LAB,
por operador com a sessão administrativa `Tomas-Instructor`; no corporativo,
pela equipe IAM mediante chamado. Os JSONs abaixo são documentos de referência
para revisão. Nenhum Terraform, workflow ou instalador deste repositório os
aplica ao IAM. Este runbook descreve uma execução posterior à revisão do
contrato; alterar o PR não executa seus comandos.

| Campo | Contrato LAB |
| --- | --- |
| Conta esperada | `712107929769` |
| Role | `itau-github-repo-factory-distroless-v1` |
| ARN | `arn:aws:iam::712107929769:role/itau-github-repo-factory-distroless-v1` |
| Path | `/` |
| MaxSessionDuration | `10800` segundos |
| Única inline policy | `factory-distroless-v1` |
| Customer-managed policies anexadas | Nenhuma |
| Trust | [factory-distroless-v1.trust.json](../policies/aws/factory-distroless-v1.trust.json) |
| Permissões | [factory-distroless-v1.inline-policy.json](../policies/aws/factory-distroless-v1.inline-policy.json) |

## Contrato e limites

A trust preserva o provider OIDC existente e `StringEquals` para audience
`sts.amazonaws.com`, repository ID `1360616627`, owner ID `178685987` e estes
dois subjects completos:

```text
repo:alric-corp@178685987/alric-containers-image-base@1360616627:environment:lab-image-base-infra
repo:alric-corp@178685987/alric-containers-image-base@1360616627:environment:DEV
```

Não há subject de PR, branch/ref alternativo ou wildcard. Restrições de branch,
revisores e demais controles dos Environments continuam sendo controles
separados; os JSONs não os configuram nem comprovam seu estado aplicado.
Os IDs são chaves suportadas na [referência OIDC do IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html#condition-keys-wif).

A inline policy tem onze statements. Seus escopos são os revisados no HEAD
`7781a53ab0d8f937cd3f729c811d28a0072d0e25` do PR #119, com a remoção exclusiva
de `ecr:ListImageReferrers`: é uma operação de API cuja permissão é
[`ecr:BatchGetImage`](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_ListImageReferrers.html),
preservada nos mesmos ARNs. Não foi adicionada permissão compensatória.

| Responsabilidade | Statements | Limite |
| --- | --- | --- |
| Terraform | `EnsureExactBackendBucket`, `ExactDefaultWorkspaceState`, `ExactDefaultWorkspaceLock`, `ReadOnlyRegionalRepositoryInventory`, `ExactSbomAnalyticsBucket` | Backend LAB em `us-east-2`, state e lock exatos do workspace default; inventário regional ECR e administração do bucket SBOM exato |
| ECR | `ExactCatalogEcr`, `RegistryAuthentication` | Vinte ações de infraestrutura/leitura/publicação no catálogo exato; token de registry limitado a `us-east-1` |
| Release Store DEV | `DevReleaseInventory`, `DevReleaseRecords` | Listagem do bucket DEV e GetObject/PutObject dos registros; sem exclusão |
| SBOM Analytics | `SbomSnapshotObjects`, `SbomSnapshotListing` | PutObject/GetObject/GetObjectVersion em `sbom-analytics/poc-v1/snapshots/*`; statement de listagem com esse prefixo |

O único DeleteObject permitido é o `.tflock` exato. Não há permissões IAM
administrativas, Athena, Glue, KMS ou acesso ao prefixo de resultados de queries.
As duas permissões ECR com `Resource: "*"` são inventário regional de repositórios
e obtenção de token; writes ECR permanecem no catálogo. A administração S3 já
revisada exige `s3:ListBucket` no bucket SBOM, portanto o statement de listagem
de snapshots **não restringe a listagem efetiva do bucket inteiro**. Escrita
condicional dos snapshots é responsabilidade da bucket policy existente;
esta identity policy não substitui esse controle.

A policy compactada ocupa **4.740 caracteres**. A quota de inline policies de
uma role é agregada: [10.240 caracteres, sem whitespace](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html).
Por isso o read-back também exige uma única inline policy e nenhuma managed
policy anexada. Os testes offline verificam ações, ARNs, condições, nomes,
inventário e tamanho; não comprovam permissões efetivas, OIDC ou enforcement
aplicado na AWS.

```sh
python3 -B -m unittest discover -s infra/tests -p test_external_iam_contract.py -v
```

## 1. Fixar a revisão aprovada e confirmar a sessão

O operador registra o commit aprovado e usa um checkout desse commit, sem
alterações nos JSONs. Não usar automaticamente a ponta mais recente. A CLI AWS
já deve estar autenticada fora do repositório; não criar profiles, usuários,
access keys ou registrar credenciais neste procedimento. IAM é global; a
região abaixo seleciona endpoints da CLI e do Access Analyzer, sem mudar a
região do backend Terraform.

Os blocos são passos manuais separados. Interromper após qualquer erro;
preservar respostas e stderr em diretório privado fora do Git. Não continuar
porque um comando subsequente teve sucesso.

```sh
factory_approved_sha="<commit aprovado na revisão do PR #119>"
factory_contract_root="$(pwd)"
factory_iam_evidence="$(mktemp -d)"
chmod 700 "$factory_iam_evidence"
factory_role_name="itau-github-repo-factory-distroless-v1"
factory_inline_policy_name="factory-distroless-v1"
test "$(git rev-parse HEAD)" = "$factory_approved_sha"
test -z "$(git status --porcelain -- policies/aws/factory-distroless-v1.trust.json policies/aws/factory-distroless-v1.inline-policy.json)"
shasum -a 256 policies/aws/factory-distroless-v1.trust.json policies/aws/factory-distroless-v1.inline-policy.json
aws sts get-caller-identity --region us-east-1 --output json --no-cli-pager \
  > "$factory_iam_evidence/session.json" 2> "$factory_iam_evidence/session.stderr"
python3 -B - "$factory_iam_evidence/session.json" <<'PY'
import json
import sys
identity = json.load(open(sys.argv[1]))
if (identity.get("Account") != "712107929769" or
        identity.get("Arn") != "arn:aws:iam::712107929769:user/Tomas-Instructor"):
    raise SystemExit("STOP: conta ou principal diferente da sessão LAB autorizada")
print("LAB account and Tomas-Instructor confirmed")
PY
```

Registrar commit, hashes, identidade e timestamp da operação. Uma identidade
diferente exige sua própria autorização; não derivar a conta esperada do STS.
No corporativo, anexar os documentos ao chamado com conta, provider OIDC e
ARNs aprovados pela equipe IAM. Os identificadores LAB não são configuração
corporativa e não autorizam acesso entre contas ou migração de HOM.

Validar os JSONs com [ValidatePolicy](https://docs.aws.amazon.com/access-analyzer/latest/APIReference/API_ValidatePolicy.html)
sem criar um analyzer ou policy IAM. A CLI mantém paginação habilitada:

```sh
aws accessanalyzer validate-policy --region us-east-1 \
  --policy-document "file://$factory_contract_root/policies/aws/factory-distroless-v1.trust.json" \
  --policy-type RESOURCE_POLICY --validate-policy-resource-type AWS::IAM::AssumeRolePolicyDocument \
  --output json --no-cli-pager > "$factory_iam_evidence/trust-validation.json"
aws accessanalyzer validate-policy --region us-east-1 \
  --policy-document "file://$factory_contract_root/policies/aws/factory-distroless-v1.inline-policy.json" \
  --policy-type IDENTITY_POLICY --output json --no-cli-pager \
  > "$factory_iam_evidence/inline-validation.json"
```

Erros, findings ou falha de acesso ficam registrados para revisão; não ampliar
a policy para satisfazer o validador. ValidatePolicy não prova que o contrato
foi aplicado nem que a role poderá ser assumida.

## 2. Conferir colisão do nome

```sh
aws iam get-role --role-name "$factory_role_name" --region us-east-1 \
  --output json --no-cli-pager > "$factory_iam_evidence/preexisting-role.json" \
  2> "$factory_iam_evidence/preexisting-role.stderr"
factory_lookup_exit=$?
```

Resultado 0: a role existe; interromper, registrar o read-back e revisar seu
ownership. Não adotar, atualizar, recriar ou anexar policies automaticamente.
Somente o erro explícito `NoSuchEntity` de GetRole confirma ausência.
AccessDenied, timeout ou erro operacional não significam nome disponível.
Mesmo depois de NoSuchEntity, `EntityAlreadyExists` de CreateRole é colisão e
interrompe a operação; não converter a criação em atualização.

## 3. Criar a role e a única inline policy

Executar somente depois de confirmar revisão, identidade e ausência. Estes
são os únicos dois comandos de mutação previstos, executados pelo operador
fora de Terraform e dos workflows:

```sh
aws iam create-role --role-name "$factory_role_name" --path / \
  --assume-role-policy-document "file://$factory_contract_root/policies/aws/factory-distroless-v1.trust.json" \
  --max-session-duration 10800 --region us-east-1 --output json --no-cli-pager \
  > "$factory_iam_evidence/created-role.json" 2> "$factory_iam_evidence/create-role.stderr"
```

Antes de PutRolePolicy, reler GetRole e as duas listagens do passo 4: conferir
o mesmo RoleId retornado por CreateRole, trust aprovada, MaxSessionDuration,
ausência de permissions boundary, inline policies e attachments. Essa
conferência evita aplicar o documento a uma role preexistente ou a uma criação
parcial cuja origem não tenha sido reconciliada. A sequência manual não é uma
transação IAM; concorrência administrativa divergente exige interrupção.

```sh
aws iam put-role-policy --role-name "$factory_role_name" \
  --policy-name "$factory_inline_policy_name" \
  --policy-document "file://$factory_contract_root/policies/aws/factory-distroless-v1.inline-policy.json" \
  --region us-east-1 --no-cli-pager \
  > "$factory_iam_evidence/put-policy.json" 2> "$factory_iam_evidence/put-policy.stderr"
```

PutRolePolicy pode substituir uma policy do mesmo nome; não usá-lo para
reconciliar uma role existente. Se uma resposta se perder ou houver falha
parcial, reler e registrar o estado antes de decidir a retomada. Não apagar
role/policy, não mudar trust e não sobrescrever configuração divergente.
Não criar usuário, access keys, provider OIDC, managed policies ou state.

## 4. Read-back IAM e relatório

Após as escritas aprovadas, recuperar todas as respostas pela API. Manter a
paginação da CLI ativa e verificar o exit code de cada leitura:

```sh
aws iam get-role --role-name "$factory_role_name" --region us-east-1 \
  --output json --no-cli-pager > "$factory_iam_evidence/role.json"
aws iam get-role-policy --role-name "$factory_role_name" --policy-name "$factory_inline_policy_name" \
  --region us-east-1 --output json --no-cli-pager > "$factory_iam_evidence/inline-policy.json"
aws iam list-role-policies --role-name "$factory_role_name" --region us-east-1 \
  --output json --no-cli-pager > "$factory_iam_evidence/inline-inventory.json"
aws iam list-attached-role-policies --role-name "$factory_role_name" --region us-east-1 \
  --output json --no-cli-pager > "$factory_iam_evidence/attachments.json"
```

Comparar JSON desserializado, sem depender de whitespace ou ordem de chaves
e listas. Os documentos esperados continuam sendo os JSONs do commit aprovado.
Qualquer outra transformação que esta comparação conservadora não reconheça
exige revisão; não tratar policies diferentes como equivalentes por nome/Sid.
O exemplo recebe somente arquivos locais já obtidos; não chama AWS:

```sh
python3 -B - "$factory_contract_root" "$factory_iam_evidence" <<'PY'
import datetime
import json
from pathlib import Path
import sys

root, evidence = map(Path, sys.argv[1:])
def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result
def read(path):
    return json.loads(path.read_text(), object_pairs_hook=unique_object)
def normalized(value):
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items()}
    if isinstance(value, list):
        return sorted((normalized(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    return value

trust = read(root / "policies/aws/factory-distroless-v1.trust.json")
policy = read(root / "policies/aws/factory-distroless-v1.inline-policy.json")
session = read(evidence / "session.json")
created = read(evidence / "created-role.json")["Role"]
role = read(evidence / "role.json")["Role"]
inline = read(evidence / "inline-policy.json")
size = len(json.dumps(inline["PolicyDocument"], separators=(",", ":")))
checks = {
    "account": session.get("Account") == "712107929769",
    "principal": session.get("Arn") == "arn:aws:iam::712107929769:user/Tomas-Instructor",
    "role_name": role.get("RoleName") == "itau-github-repo-factory-distroless-v1",
    "role_arn": role.get("Arn") == "arn:aws:iam::712107929769:role/itau-github-repo-factory-distroless-v1",
    "created_role_id": role.get("RoleId") == created["RoleId"],
    "path": role.get("Path") == "/",
    "duration": role.get("MaxSessionDuration") == 10800,
    "no_permissions_boundary": "PermissionsBoundary" not in role,
    "trust": normalized(role.get("AssumeRolePolicyDocument")) == normalized(trust),
    "inline_role": inline.get("RoleName") == role.get("RoleName"),
    "inline_name": inline.get("PolicyName") == "factory-distroless-v1",
    "inline_document": normalized(inline["PolicyDocument"]) == normalized(policy),
    "single_inline": read(evidence / "inline-inventory.json").get("PolicyNames") == ["factory-distroless-v1"],
    "no_attachments": read(evidence / "attachments.json").get("AttachedPolicies") == [],
    "inline_quota": size < 10240,
}
report = {
    "schema_version": 1, "account": session["Account"], "role_arn": role.get("Arn"),
    "policy_name": inline.get("PolicyName"), "policy_character_count": size,
    "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "checks": checks, "result": "PASS" if all(checks.values()) else "FAIL",
    "oidc_assumption": "NOT_PROVEN", "cutover_executed": False,
}
(evidence / "readback-report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
raise SystemExit(0 if all(checks.values()) else 1)
PY
```

As respostas de API da CLI representam os policy documents como JSON. Para
clientes que devolvam o documento URL-encoded, decodificar conforme
[GetRolePolicy](https://docs.aws.amazon.com/IAM/latest/APIReference/API_GetRolePolicy.html)
antes da comparação; não comparar uma string encoded com um documento.
Preservar evidências mesmo quando o resultado for FAIL. Falha de leitura ou
de parsing interrompe o procedimento e não aprova configuração ausente.
O relatório registra configuração observada, não uma prova de OIDC ou de
operações ECR/S3. Guardar commit/hashes/revisão junto dele, fora do Git público.

## 5. Cutover posterior

O próximo PR somente referencia o ARN após existência e read-back aprovados.
Todos os fluxos elegíveis LAB/DEV usarão essa role; certificação DEV mantém
session policy somente leitura e checks de PR ficam sem AWS privilegiada.
Criar uma referência de role operacional separada da identidade legada:
`DEV.role_name` ainda alimenta `infra/lifecycle/main.tf` e não pode ser
alterado diretamente durante esse cutover. Atualizar o resolvedor e seus
testes no incremento separado. HOM é outra conta e exige decisão específica.

As roles legadas e seus endereços Terraform permanecem integralmente
preservados. Não executar destroy, import ou comandos de alteração de state
para esta identidade externa. Aposentadoria de roles antigas fica para depois
da comprovação do cutover. Ingestão real SBOM vem depois; Athena/Glue somente
após autorização de seus escopos. Este contrato não ativa HGC-04, stable,
promoção, uploads de snapshots ou consultas.
