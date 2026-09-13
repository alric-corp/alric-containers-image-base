# ACCEPTANCE — P1-05

| ID | Requisito | Critério observável | Verificação |
| --- | --- | --- | --- |
| A01 | R1–R7 | ADR corresponde aos workflows, helpers e defaults efetivos da baseline | Inspeção das fontes e evidence |
| A02 | R2 | Imagem, provenance e SPDX têm declarações/subjects/limites distintos | Tabela no ADR |
| A03 | R1 | GitHub, Fulcio, Rekor, raízes distribuídas, ECR e governança separados | Trust model e fontes oficiais |
| A04 | R4 | Metadados públicos e payload enviado/persistido corretamente delimitados | Código oficial versionado e documentação |
| A05 | R5 | Público/privado distingue raízes GitHub e comportamento do Cosign direto | Matriz e fontes oficiais |
| A06 | R3 | Identidade sandbox concreta; identidade corporativa não presumida | Policy, API de leitura e teste documental |
| A07 | R6 | ADR aponta para o Consumer Verification Contract existente | Links locais e inspeção |
| A08 | R2/R6 | Evidence não equivale a enforcement; gates atuais não são ampliados | Inspeção de promotion/recovery/consumer |
| A09 | R7 | Private Sigstore não é requisito sem necessidade regulatória/policy explícita | Alternativas e posição proposta |
| A10 | R7 | Decisão corporativa permanece EXTERNAL / PROPOSED, mesmo após eventual merge documental | ADR, índice, RFC e handoff |

## Negativos e limites

Esta fatia não muda controles: usar a suíte existente de assinatura/provenance
e testes documentais de identidade/links/comandos. Não criar assinatura real,
forjar tokens, interromper serviços ou declarar novos negativos hospedados.
Inspeção semântica do ADR não é substituída por testes de palavras-chave.

## Aceite externo

Segurança/AppSec deve aprovar ou rejeitar metadados/serviços públicos, definir
identidades/raízes corporativas e exigir validação no ambiente escolhido.
Isso permanece pendente; não é critério de PASS local nem aprovação implícita
pela revisão documental. Opus 5 MAX fará a revisão arquitetural independente.
