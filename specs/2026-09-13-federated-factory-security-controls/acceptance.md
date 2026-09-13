# ACCEPTANCE — P1-06

| ID | Requisito | Critério observável | Verificação |
| --- | --- | --- | --- |
| A01 | R1 | Premissa canônica registra origem relatada, sem fabricar documento formal ou reabrir autorização | ADR e referências |
| A02 | R1 | Quatro categorias e limites de autoridade separados; federado não significa OIDC | ADR |
| A03 | R2 | Controles existentes têm fonte executável e limites de evidence | Matriz versus código e specs existentes |
| A04 | R3 | Cinco distinções de scanner preservadas, sem presumir obrigação, dispensa ou homologação | Seção scanner |
| A05 | R4 | Levantamentos não viram requisitos/configuração comprovada; interfaces são condicionais | ADR e nota no histórico |
| A06 | R5 | Matriz atribui manutenção/operação a Containers Products e decisões externas aos respectivos owners | ADR e fontes de responsabilidades |
| A07 | R5 | Perguntas de segunda-feira cobrem somente pendências corporativas | Tabela de perguntas |
| A08 | R6 | Premissa única, referências válidas e nenhum conteúdo interno sensível copiado | Diff e testes documentais |
| A09 | R1/R2 | PROPOSED externo e hosted acceptance existentes preservados | ADR/evidence/handoff |
| A10 | R2/R6 | Somente documentos e teste documental; sem alteração de implementação/policies/workflows | Escopo do diff, testes e lints |

## Negativos e limites

Não criar testes que simulem aprovação corporativa ou interpretem ausência
de decisão como dispensa. Estender validação de links já existente; os gates
e negativos técnicos permanecem na suíte atual. A inspeção semântica exige
revisão independente; teste documental não homologa scanner ou infraestrutura.

## Aceite externo

Registrar respostas, owner, referência autorizada e evidência exigida no
ambiente adequado após validação corporativa. Não publicar anexos restritos
ou identificadores internos no repositório público. Pendente nesta fatia.
