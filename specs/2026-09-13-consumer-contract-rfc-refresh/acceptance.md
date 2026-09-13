# ACCEPTANCE — P1-09 + P1-10

| ID | Requisito | Critério observável | Validação |
| --- | --- | --- | --- |
| A01 | R1 | RFC representa o comportamento da main identificada | matriz código/docs |
| A02 | R2 | stable, build tag e OCI index digest distintos | contrato canônico |
| A03 | R3 | assinatura com identidade/issuer atuais exatos | policy/script e teste documental |
| A04 | R3 | provenance documentada com origem e limites | gh CLI/script |
| A05 | R3 | SBOM attestation verificada, distinta de provenance | publisher/SPDX/CLI |
| A06 | R4 | evidence disponível não implica enforcement | contrato/RFC |
| A07 | R6 | sandbox separado de ambiente corporativo | tabela externa |
| A08 | R5 | read-back confirma igualdade naquele instante | verify_stable/workflow |
| A09 | R5 | retry mesmo run/digest, sem falha recente do producer | gate/workflow |
| A10 | R5 | Wolfi não alega confiança exclusiva | runbook/spec P1-03 |
| A11 | R6 | nenhum item externo marcado concluído | RFC/handoff |
| A12 | R7 | links/comandos consistentes com código atual | testes documentais/contexto |

## Resultado local
A01–A12: PASS documental/local, conforme a matriz, consultas e checks em
[evidence.md](evidence.md). A03–A05/A12 foram confrontados com código atual,
fontes oficiais e testes estruturais; comandos autenticados de consumo não
foram executados nesta entrega. Revisão independente Opus 5 MAX:
APPROVE WITH MINOR CHANGES; finding LOW corrigido, re-revisão final pendente.

P1-01 hosted PASS decorre da evidence real do run 34768459323, não dos testes
locais. P1-02 e P1-03 continuam PENDING; itens corporativos não são homologados.

## Limites
Verificação estrutural não é execução autenticada contra o ECR. Não se promove
aceite local a hosted PASS. Aceites externos continuam sob seus owners.
