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
