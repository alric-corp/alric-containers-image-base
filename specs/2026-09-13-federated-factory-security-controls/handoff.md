# HANDOFF — P1-06

- Baseline: main `a5f1c435eab545b28bf37f445ddd11c3ff5b3ff7`.
- Objetivo/limites: [spec.md](spec.md); estratégia: [plan.md](plan.md).
- Estado: documentação implementada e verificada localmente; resultados em [evidence.md](evidence.md).
- Próximo passo: revisão independente posterior e validação corporativa das pendências.
- Autorizações: somente documentos/spec/ADR e testes documentais; sem Git remoto.

Não converter a conclusão local em homologação de controles ou infraestrutura.
Confirmar Git e diff antes de prosseguir.

Verificação: 300 testes unitários, 24 de integração, seis documentais,
lint-local, lint-shared, lint-workflows, check_ai_context e diff --check PASS.
São 15 arquivos da fatia, sem staging, commit, push ou PR.

## Fonte canônica e escopo

[ADR-0003 / P1-06](../../docs/adr/0003-controles-seguranca-workflows-federados.md)
é a fonte da premissa; não criar nova pergunta de autorização ou documento
concorrente. A matriz separa implementação, requisitos a confirmar e
dependências externas. O estado PROPOSED refere-se aos aceites externos.

Esta entrega não é integração com workflow governado. Trivy continua gate
implementado, sem presumir homologação para a fábrica. Veracode SCA descrito
no levantamento não é obrigatório nem dispensado por inferência. A política
das aplicações consumidoras continua separada.

## Revisão e validação corporativa

Revisão independente ainda não realizada nesta fatia. Validar no ADR as
seis perguntas de segunda-feira e registrar posteriormente respostas/owners
e referências permitidas. Não publicar os levantamentos integrais ou dados
internos no repositório público. Nenhum novo requisito pode ser presumido
dos defaults observados em outro workflow.

Containers Products sustenta o produto; AppSec/Segurança decide requisitos
sob sua competência; Cloud/IAM/Network/PKI responde pelos recursos/acessos;
times consumidores respondem pelos builds e controles das suas aplicações.
Os detalhes permanecem na matriz canônica do ADR.

P1-01 hosted PASS; P1-02/P1-03 PENDING preservados. Primeiro aceite corporativo
não executado. Não fazer commit, push, PR, alteração de scanner/gates ou
infraestrutura sem instrução posterior que autorize a ação correspondente.
