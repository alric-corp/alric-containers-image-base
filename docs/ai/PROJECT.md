# Contexto do produto

## Fontes canônicas

| Tema | Fonte |
| --- | --- |
| Produto e operação | [README](../../README.md) |
| Ambiente e comandos completos | [CONTRIBUTING](../../CONTRIBUTING.md) |
| Domínios e dependências permitidas | [Arquitetura](../repository-architecture.md) |
| Camadas de teste e dependências | [Testes](../../tests/README.md) |
| Regras de catálogo, OCI, release, runtime e governança | [scripts/pipeline](../../scripts/pipeline/) |
| Certificados, aquisição e pins | [scripts/certificates](../../scripts/certificates/) |
| Políticas revisadas | [policies](../../policies/README.md) |
| Decisões pontuais (ADR) e seu estado | [docs/adr](../adr/README.md) |
| Premissa de autoria/sustentação e requisitos da fábrica federada | [ADR-0003 / P1-06](../adr/0003-controles-seguranca-workflows-federados.md) |
| Contrato com a biblioteca | [Workflows reutilizáveis](../m09-m12-reusable-workflows.md) |

Composição fica em frameworks/, distroless/ e melange/. Regras de domínio
ficam nos módulos Python, orquestração em .github/workflows/. Os seis
adaptadores em .github/scripts/ preservam compatibilidade e não recebem lógica.
O lock da triagem de CVEs é gerado pelo compilador; edite a fonte apropriada.
Consulte a arquitetura antes de mudar dependências entre domínios.

## Validar a partir da raiz

```sh
make test-unit lint-local
python3 -B tools/check_ai_context.py
```

Para o conjunto completo, use `make check` após preparar as dependências de
integração e o checkout da biblioteca no SHA dos chamadores, como descrito
em CONTRIBUTING.md. O diretório irmão na main não substitui esse checkout.

Mudanças de runtime exigem os contratos de imagens reais apropriados.
Mudanças em publicação, assinatura, promoção, certificados ou gates exigem
negativos e revisão independente. Execução local não comprova publicação no ECR.

## Manter este contexto

Pins, catálogo e inventários permanecem em suas fontes; não os copie para
instruções de IA. Evidências antigas descrevem somente os commits/runs registrados.
`tools/check_ai_context.py` é tooling de desenvolvimento, sem função no build
das imagens. Sua regressão integra a suíte unitária existente.
