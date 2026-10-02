# Fechamento das lacunas de pipeline health e promoção DEV/HOM

> **Estado em 02/10/2026:** decisões do owner incorporadas ao plano. FULL é o baseline corporativo permanente de 16 imagens, PAT é o mecanismo cross-repo e GitHub Actions é o canal oficial de alerta desta fase. Custo/capacidade dos runners estão resolvidos. As pendências são de implementação, documentação e evidência; este registro local não comprova alterações externas.

## Decisões confirmadas pelo owner

- O próprio time é owner da solução.
- O catálogo FULL, com 16 imagens, é o baseline corporativo permanente e não depende de reaprovação periódica.
- Go-only pertence ao histórico de validação do LAB.
- Custo e capacidade dos runners estão resolvidos.
- A leitura cross-repo será feita por PAT do GitHub; GitHub App está fora do desenho disponível.
- GitHub Actions, por meio de `pipeline-health.yml` e seu resumo, é o canal operacional atual.
- `channel.external_destination = null` é intencional nesta fase.
- `develop` é a branch default; os modelos de `stable` DEV e promoção DEV → HOM estão definidos.

Escopo FULL, referência documental e canal de alertas deixam de ser decisões arquiteturais abertas. A implementação deve refletir essas decisões, preservando as verificações de integridade e os gates técnicos de promoção. Modelo definido não substitui evidência de uma execução real.

---

## 1. Leitura cross-repo dos pins do reusable

### Contexto

O `pipeline-health.yml` usa `github.token` do próprio repositório para chamar o checker de pins.

Oito referências apontam para o mesmo commit:

```text
b8cf9a4d444231e3db1850c7a923796c3cab56ab
```

no repositório:

```text
itau-corp/itau-xj7-reusable-workflows-containers-products
```

O `uses:` desses workflows/actions resolve em tempo de execução do GitHub Actions, mas isso **não concede ao `github.token` permissão REST** para consultar:

```text
repos/{owner}/{repo}/commits/{sha}
```

no outro repositório.

Por isso, o checker reporta o pin como **não verificado**, e não como ausente.

### Implementação com PAT

A decisão do owner é utilizar PAT para este monitor. Atualizar a orientação anterior do projeto para refletir esse mecanismo e seu escopo específico.

- O token deve ser armazenado em **Actions Secrets**, e não em GitHub Variables.
- Utilizar **PAT fine-grained**, emitido por uma conta com acesso ao reusable, com resource owner `itau-corp` e acesso selecionado somente a:

  ```text
  itau-xj7-reusable-workflows-containers-products
  ```

- Permissão mínima:

  ```text
  contents: read
  ```

- Configurar o secret `REUSABLE_READ_TOKEN` no repositório corporativo da Factory. Sua existência e seu funcionamento ainda precisam ser comprovados.
- Registrar titular, validade, responsável pela renovação e procedimento de revogação junto à configuração operacional, sem registrar o valor do token.
- Usar o PAT somente nas consultas cross-repo do checker, preservando `github.token` para consultas do próprio produto. Não substituir globalmente a credencial do job.
- Token ausente, vencido ou sem acesso deve resultar em `unverified` e falha explícita do health.

O endpoint `GET /repos/{owner}/{repo}/commits/{sha}` suporta PAT fine-grained com `Contents: read`. Fontes: [permissões da API](https://docs.github.com/en/rest/commits/commits#get-a-commit) e [configuração de PATs](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).

---

## 2. Escopo operacional corporativo

O catálogo FULL, composto pelas 16 imagens da Factory, é o baseline operacional do ambiente corporativo.

O escopo Go-only pertenceu ao modelo de validação do LAB e não constitui exceção ou estágio operacional do ambiente corporativo.

**A operação corporativa não depende de revisão periódica para permanecer em FULL.** Revisões futuras de capacidade, custo ou saúde da plataforma não alteram esse baseline automaticamente.

### Implementação e documentação

- Manter `policies/operations/health.json`, em `execution_scope.current`, alinhado às 16 imagens do catálogo corporativo.
- Remover do corporativo a semântica de exceção temporária herdada do recorte Go-only do LAB.
- Alinhar motivo, ADR e documentação: Go-only como histórico do LAB e FULL como comportamento padrão corporativo. Preservar o histórico das decisões.
- Atualizar os testes e o monitor para que FULL não dependa de renovação de uma autorização temporária.

### Tratamento de review_by

A data `2026-09-30` vencida foi registrada no checkpoint anterior. O fechamento deve corrigir a semântica do controle, em vez de apenas adiar a data.

- Se `execution_scope.review_by` existir exclusivamente para expirar a exceção de escopo, remover essa exigência, seu campo e sua lógica de alerta no corporativo, ajustando schema, testes e documentação correspondentes.
- Se houver uma revisão periódica operacional independente, seu significado deve ser revisar saúde, custo ou capacidade. Ela pode gerar acompanhamento operacional, mas não revoga o baseline FULL nem exige nova permissão para continuar com as 16 imagens.
- Uma próxima data de revisão não é pré-requisito para autorizar FULL. A configuração e o monitor precisam refletir essa decisão.

Esse ajuste permanece pendente no código corporativo. O documento registra a decisão; a integração deve eliminar o alerta legado conforme o contrato atualizado.

---

## 3. Canal operacional

Nesta fase, o `pipeline-health.yml` e o respectivo resumo do GitHub Actions constituem o mecanismo oficial de alerta operacional da Factory. O próprio time owner acompanha esse canal.

Não será configurado um destino externo nesta etapa. **`channel.external_destination = null` é intencional e significa não aplicável nesta fase por decisão do owner.** A documentação e o monitor devem reconhecer esse estado, sem apresentar a ausência de destino externo como lacuna ou condição para health verde.

Uma integração com Microsoft Teams, por exemplo através de Power Automate, poderá ser adicionada futuramente caso a experiência operacional demonstre necessidade de notificação fora do GitHub:

```text
GitHub Actions → Power Automate → Microsoft Teams
```

Essa integração é uma possibilidade futura, sem tarefa de implantação nesta etapa. Confirmação de recebimento e escalonamento externos também não são requisitos do fechamento atual.

---

## 4. Integração da correção local do diagnóstico de pins

### Contexto

A correção local diferencia os seguintes cenários:

#### `available=false` / `mismatch`

A origem respondeu corretamente, mas o valor encontrado não corresponde ao esperado.

#### `available=null` / `unverified`

Pode representar:

- erro HTTP;
- timeout;
- falta de permissão;
- resposta inválida.

Esse cenário **não comprova ausência do pin**.

A implementação também:

- preserva diagnóstico sanitizado;
- registra HTTP status no JSON/Markdown;
- reutiliza a resposta quando vários arquivos utilizam o mesmo commit.

### Implementação necessária

- Revisar e integrar as alterações locais em `develop` pelo fluxo combinado, com CI Linux/ARC.
- Preservar a falha do health para `unverified` e `mismatch`.
- Cobrir autenticação negada, 404, timeout, rate limit, resposta inválida e SHA divergente.
- Reutilizar a consulta do mesmo repositório/SHA dentro da execução, mantendo o resultado individual das oito referências.
- O time owner acompanha o próximo run real e registra as evidências.

A correção do diagnóstico pode ser integrada antes da configuração do PAT. Ela deve eliminar a classificação falsa de ausência independentemente da credencial. HTTP 404 isolado continua inconclusivo, pois o GitHub pode utilizá-lo para ocultar recursos privados sem acesso. Fonte: [diagnóstico da API](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api#404-not-found-for-an-existing-resource).

---

## 5. Pendências de validação operacional

Estas verificações precisam ser observadas em execução real depois da integração das correções e da configuração do PAT.

### 5.1 Promoção DEV

Confirmar que o próximo health reconhece a promoção:

```text
DEV #243
```

com run/attempt, membros efetivamente promovidos, digests, read-backs e timestamp utilizado para:

```text
stable_age_hours
```

Os alertas anteriores só devem desaparecer para imagens cuja evidência e idade satisfaçam a política. Um run verde ou um membro `skipped` não renova automaticamente a idade de todas as imagens.

Comprovar separadamente DEV FULL: as 16 imagens da release certificada, sua promoção e seus read-backs, vinculados ao run/attempt correspondente. Reconhecer DEV #243 no health não dispensa essa verificação de cobertura.

### 5.2 Checker de pins

Confirmar que o PAT permite consultar o SHA esperado e que as oito referências ficam verificadas. A ausência falsa é resolvida pela correção do diagnóstico; o PAT resolve o acesso.

Caso a consulta continue sem acesso, o resultado deve permanecer `unverified` e o health deve falhar.

### 5.3 Promoção HOM

Integrar a correção do seletor e confirmar a próxima seleção/promoção HOM. Exigir fonte DEV elegível, soak efetivamente integrado, identidade exata da release e read-back dos mesmos 16 digests. Health verde não substitui essa evidência.

### 5.4 Testes Linux/ARC

Repetir no CI Linux/ARC os testes que atualmente falham localmente devido a diferenças de:

- caminho;
- privilégios;
- criação/utilização de symlink no Windows.

---

## Estado atual recomendado

A decisão de usar PAT, o baseline FULL permanente e o canal GitHub Actions já foram definidos pelo owner. Restam a credencial funcional, a integração das correções, a adequação de configuração/documentação e as evidências de execução.

O `pipeline-health` deve continuar falhando para problemas reais, como pins `unverified`/`mismatch` ou evidências de promoção que não satisfaçam o contrato. A lógica corporativa deve deixar de exigir renovação de FULL ou destino externo de alertas. Corrigir configuração e acesso deve permitir que ele fique verde com evidência real.

A falha do health é o mecanismo de alerta implementado. Este documento não comprova uma dependência que bloqueie DEV/HOM; qualquer afirmação sobre gate de promoção precisa corresponder aos workflows efetivos.

---

## Decisões fechadas

Os estados abaixo registram as decisões e informações fornecidas pelo owner, sem substituir read-back ou evidência de execução.

| Item | Estado |
| --- | --- |
| Escopo FULL corporativo | Decidido: baseline permanente de 16 imagens |
| Capacidade/custo dos runners | Resolvido |
| PAT como mecanismo cross-repo | Decidido |
| Canal de alerta GitHub Actions | Decidido; destino externo não aplicável nesta fase |
| develop como default | Confirmado pelo owner |
| stable em DEV | Modelo definido |
| Promoção DEV → HOM | Modelo definido, mesmo artifact sem rebuild |

## Pendências de implementação e evidência

| Item | Estado | Critério de conclusão |
| --- | --- | --- |
| Configurar `REUSABLE_READ_TOKEN` real | Pendente | Secret funcional, acesso restrito ao reusable e renovação registrada |
| Integrar correção `mismatch` × `unverified` | Pendente | Diagnóstico e reutilização de consultas integrados, sem tratar erro inconclusivo como sucesso |
| Integrar correção do seletor HOM | Pendente | Seleção distingue fonte inelegível de evidência ausente/corrompida conforme o contrato |
| Atualizar `health.json` e seu consumidor para FULL permanente | Pendente | Catálogo de 16 imagens, sem expiração de autorização FULL; `external_destination = null` reconhecido como intencional |
| Remover semântica de exceção Go-only do corporativo | Pendente | Schema, testes, ADR e documentação distinguem histórico LAB de baseline corporativo |
| Rodar CI/testes no Linux/ARC real | Pendente | Testes relevantes aprovados na revisão integrada |
| Validar os oito pins via PAT | Pendente | Consulta autenticada do SHA esperado e resultado individual das oito referências |
| Validar health lendo DEV #243 | Pendente | Run/attempt, membros e timestamps corretos no cálculo de idade |
| Comprovar DEV FULL | Pendente | Promoção e read-backs das 16 imagens vinculados à release certificada |
| Executar promoção HOM FULL | Pendente | Fonte DEV elegível, soak integrado e cópia dos mesmos artifacts, sem rebuild |
| Comprovar read-back/digests em HOM | Pendente | 16/16 destinos confirmados iguais aos digests da fonte DEV aprovada |

## Critério para considerar o health saudável

O health somente deve ser considerado efetivamente saudável quando:

- os pins cross-repo puderem ser verificados de forma autorizada;
- a configuração e seus validadores refletirem FULL permanente, sem reaprovação periódica do escopo;
- GitHub Actions for reconhecido como canal oficial desta fase, com destino externo intencionalmente nulo;
- alertas de promoção DEV/HOM estiverem coerentes com o estado real;
- o checker distinguir corretamente `mismatch` de `unverified`;
- os testes relevantes estiverem validados no ambiente real de CI.

## Critério para fechar o fluxo corporativo

```text
PAT funcional
    + correções integradas
    + CI Linux/ARC verde
    + health coerente
    + DEV FULL comprovado
    + HOM FULL promovido com os mesmos artifacts
    + read-back e igualdade de digests 16/16
    = fluxo corporativo fechado
```

Esse é o critério conjunto de aceite operacional; não declara uma nova dependência entre jobs. **Health verde sozinho não substitui a evidência de promoção HOM dos mesmos 16 digests.**
