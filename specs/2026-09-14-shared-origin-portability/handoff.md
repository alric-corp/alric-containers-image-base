# HANDOFF — origem compartilhada

## Estado local

Produto sandbox na branch main, base 468cfe0fbde719a63bc94d205a4bbda24ed391f1,
mesma origin/main observada após fetch. Pacote documental incorporado pelo
PR #61. Biblioteca canônica main b574bd487e7c598c12ab6c6e584a523e03caaa45 limpa;
checkout consumido 7a9b055a462eeb8552d3404c26538b44e8ccd83f limpo. Action no pin
independente eea2d2f4c4102ded74204e4131c1417f444ae3fc, sem mudança.

Implementação local concluída, 18 arquivos no produto ainda sem staging/commit/
push/PR; biblioteca sem diff. Lista e resultados em [evidence.md](evidence.md).
T01–T05 concluídas; T06, revisão independente pelo Claude Code, pendente.
Spec técnica separada do pacote documental; snapshots anteriores preservados.

## Entrega para revisão

Origem canônica em [policy](../../policies/governance/reusable-workflows.json),
referências literais conferidas pelo resolvedor, inventário obrigatório
independente da origem encontrada, pins de workflow/action distintos,
Dependabot e documentação ativa coerentes. CLI `checkout` valida referências
locais; `lint` acrescenta origem/HEAD/bytes dos dois YAMLs e contratos internos.
Ver [spec.md](spec.md) e [acceptance.md](acceptance.md), sem auto-aprovação.

Verificação: 350 unitários, 24 integração, lints local/shared/workflows,
check_ai_context e diff check PASS. Os 37 do resolvedor e seis documentais
integram os unitários; quatro negativos de migração parcial executados também
explicitamente. Dois falsos PASS anteriores reproduzidos antes da correção.
Nenhum build do catálogo ou operação AWS foi usado para validar esta fatia.

## Sequência posterior de release

O sandbox atual não precisa de novo release compartilhado para usar o
validador. A biblioteca consumida ainda invoca a action na origem sandbox.
Uma adoção real de outro repositório exige esta ordem, após autorização:

1. Definir origem aprovada e acesso. Confirmar separadamente resolução GitHub
   de workflow/action e checkout/download durante a execução. Visibilidade
   privada/interna e acesso cross-repository são decisões dos administradores.
2. Disponibilizar no destino o commit real aprovado da composite. Preparar na
   biblioteca canônica a referência interna com nova origem e SHA real da action,
   preservando seu contrato; revisar/testar e integrar/publicar esse release.
3. Somente então adotar no produto o SHA real comum dos reusables e o SHA próprio
   da action. Alinhar policy, callers, actions locais, checkout/resolvedor,
   Dependabot e os quatro documentos ativos conforme o [contrato de reuso](../../docs/m09-m12-reusable-workflows.md).
4. Repetir checks locais com checkout da origem/revisão autorizada. Depois da
   revisão/integração autorizadas, observar os checks hospedados normais e
   registrar run, commit, origem, SHAs, resultados e escopo. Não executar
   dispatch operacional para testar esta mudança.

Se faltar acesso, release real ou uma referência divergir, parar a adoção.
Não usar main/tag móvel, fixture SHA, `./actions/setup-trivy`, PAT ou novo secret
para superar a dependência. Reversão por diff coordenado está em [plan.md](plan.md).

## Limites e estados externos

Suporte delimitado a GitHub.com. URL de remote não é prova de publicação ou
autorização; bytes verificados limitam-se aos dois workflows consumidos, não
ao conteúdo integral da biblioteca/action em outro commit. Testes com falha Git
não comprovam negativa de acesso privado. Fixtures não provam integração remota.

INDEPENDENT_REVIEW=PENDING; HOSTED_ACCEPTANCE=NOT RUN;
CORPORATE_ACCEPTANCE=EXTERNAL_PENDING; acesso privado=NOT VERIFIED.
Nenhum novo release compartilhado foi publicado ou adotado. A futura migração
de origem tem essa dependência explícita, sem integração entre repositórios
declarada como concluída. P0-03 operacional e pendências das demais fatias
permanecem abertos; estados específicos preservados na evidence.

Próximo passo desta entrega: revisão independente do diff e dos critérios
locais pelo Claude Code. Este handoff não autoriza staging/publicação Git,
mudança de infraestrutura, acesso corporativo ou operações da fábrica.

## Reconciliação corrente — 2026-09-14

O texto anterior preserva o snapshot pré-publicação. PR #62 integrado em
`8ed8260eba75d4f8b5d856cd1fba37a404a5129a`; main local atualizada por
fast-forward, sem mudanças na biblioteca, checkout consumido ou pins.

Proposta de estado: **HOSTED_ACCEPTANCE = PASS observado na origem sandbox**.
Runs 34850493723/1 (PR, checkout de merge de teste `991b784d…`) e
34852456390/1 (push main `8ed8260…`) comprovam resolver → outputs → checkout
real `7a9b055…` → lint de origem/HEAD/bytes/Trivy → contratos. Evidência e
limites em [evidence.md](evidence.md); revisão independente desta coleta pendente.
APPROVE anterior da implementação, informado pelo usuário, não é aprovação
automática deste encerramento. A API não registra review formal no PR.

Migração real para outra origem NOT RUN; fixture alternativa permanece local;
acesso privado NOT VERIFIED; corporativo EXTERNAL_PENDING. A sequência futura
de release acima continua válida. Próximo passo: revisar esta reconciliação;
não repetir workflows para recriar a evidência já disponível.
