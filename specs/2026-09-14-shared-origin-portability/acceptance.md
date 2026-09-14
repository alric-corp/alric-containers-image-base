# ACCEPTANCE — origem compartilhada

| ID | Propriedade | Verificação requerida |
| --- | --- | --- |
| A01 | R1/R2 | Sandbox atual e origem sintética aprovada resolvem origem/SHA e validam checkout pela CLI real; configuração ausente/inválida falha antes de output. |
| A02 | R3 | Reproduzir falsos PASS anteriores; caller/action remanescente, ponto ausente e referência ilegível agora falham. |
| A03 | R4 | SHA curto/malformado/móvel e releases divergentes falham; action distinta dos reusables passa quando consistente, e divergência da action falha. |
| A04 | R5 | Checkout ausente, origem/revisão/bytes divergentes e falha/resposta inválida de Git falham; override de diretório não muda a confiança. |
| A05 | R2/R3/R4 | Referência interna incompatível do release consumido é rejeitada com indicação do ponto. Terceiros continuam aceitos. |
| A06 | R6 | Grupo Dependabot divergente falha; documentos ativos/testes incluem origem e pin corrente, sem reescrever snapshots. |
| A07 | R7 | Contratos reais/adaptadores, permissões e assinatura do produto preservados; nenhuma credencial adicionada. |
| A08 | Todas | Checks locais reais, evidence e sequência de release; sem alegar hosted/private/corporate PASS por fixtures. |

Aceites hospedado e corporativo: NOT RUN / EXTERNAL_PENDING. Se uma nova origem
exigir release compartilhado, sua integração real depende de revisão/publicação
posterior e adoção do SHA real; nenhum pin operacional aponta a fixture.

## Estado corrente — reconciliação de 2026-09-14

O NOT RUN acima é o snapshot anterior à coleta hospedada. Evidência nova em
[evidence.md](evidence.md): runs 34850493723 (merge de teste do PR) e
34852456390 (main integrada), attempt 1, demonstram execução do resolvedor,
outputs, checkout real e lint/contratos posteriores na origem sandbox.

**PASS observado — hosted na origem atual**, para A01 e os caminhos positivos
de A03–A08 descritos na evidence. Negativos/migração sintética continuam provas
locais/fixtures; não há exigência nova de migrar a origem operacional. A02 e
demais negativos não são promovidos a testes operacionais por rodarem no CI.

Migração real a outra origem NOT RUN; acesso privado NOT VERIFIED; corporativo
EXTERNAL_PENDING. A implementação recebeu APPROVE conforme relato do usuário;
a conclusão desta coleta está **PENDING de revisão independente**.
