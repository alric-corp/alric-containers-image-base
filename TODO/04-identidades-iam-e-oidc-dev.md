# M04 — Vincular identidades, IAM e OIDC ao DEV real

**Dependências:** M01 e M02; formato de Environment definido.  
**Tipo de trabalho:** Leitura, alterações locais de configuração e prova de autenticação autorizada; sem provisionamento automático de IAM.

## Objetivo desta sessão

Substituir sentinelas por identidades corporativas verificadas e comprovar autenticação no destino DEV correto.

## Consultar somente

- `policies/release/signing-identities.json` e `policies/aws/github-actions-image-base-trust.json`.
- Trechos de OIDC/Environment dos jobs AWS e contrato de autenticação do `registry.yml` corporativo.
- Testes focados de identidade, verificação de provenance e account/ref guards.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Obtenha repository ID e owner ID reais via acesso autorizado. Se já puder consultá-los em leitura, não os trate como informação que obrigatoriamente depende de outro time. Registre apenas valores não secretos e sua origem.
2. Confirme conta DEV, região, roles e mecanismo corporativo de plan/apply. Não pressupor que o executor de infraestrutura autentica exatamente como o publisher.
3. Confira issuer, audience e subject esperados considerando `environment: dev` e eventuais customizações corporativas. Não fazer substituição cega de `main` por `develop` na trust policy.
4. Preencha apenas os campos verificados. Signing identity/provenance devem preservar a origem real de build em `develop`. Não reutilize IDs do LAB nem torne validações opcionais.
5. Execute testes positivos com valores de teste e negativos para sentinelas, origem/ref/conta incorretas. Falhas não relacionadas devem ser reportadas separadamente, não ocultadas.
6. Depois do provisionamento aprovado por Cloud/IAM, peça uma única prova de autenticação e identidade AWS, sem escrita. Confira `sts get-caller-identity` e o destino esperado; ECR ainda ausente é uma condição possível antes do M06, não motivo para criá-lo aqui.

## Critérios de aceite

- Nenhuma identidade do LAB ou sentinela em um caminho de confiança que será ativado.
- Roles e trust corporativas coerentes com job, Environment e branch.
- Conta/identidade da sessão DEV comprovadas sem divulgar tokens.
- Read-only da certificação é distinguido de permissões de publicação e infraestrutura.

## Quando parar

Conta/ref/identidade divergente, deny de IAM ou valores ausentes. Não editar IAM para “fazer passar” nem imprimir JWT, token ECR ou secrets. Solicite o ajuste específico ao responsável.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
CORPORATE_IDENTITIES =
OIDC_ENVIRONMENT_BINDING =
AWS_ACCOUNT_CONFIRMED =
AUTHENTICATION_PROOF_RUN =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/04-identidades-iam-e-oidc-dev.md.
Execute somente M04. Feche o binding corporativo de identidade e OIDC de DEV com os
valores reais disponíveis. Use testes focados. Não crie roles nem amplie permissões.
Para prova hospedada, solicite autorização de uma execução apenas de
autenticação/leitura.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: seções 13, 16, 17 e Gate 1. Ajustes da revisão: não confundir identidade de assinatura com trust AWS; validar Environment/subject conjuntamente. Este marco é um roteiro; não comprova que as ações já foram realizadas.
