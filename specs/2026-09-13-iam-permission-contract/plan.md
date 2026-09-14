# PLAN — P1-04

1. Conferir PR #59 e remotes, avançar main limpa por fast-forward; ler fontes
   atuais e evidências pertinentes, sem consultar policies reais restritas.
2. Rastrear operações AWS explícitas e das ferramentas; conferir actions,
   recursos e claims em documentação oficial atual. Pesquisa auxiliar somente
   leitura não constitui revisão independente.
3. Criar contrato canônico e inventário estruturado em diretório de propostas
   sob policies/aws, sem substituir o trust ativo. Templates de identity para
   runtime e provisionamento, e trust corporativo proposto; renderização local
   explícita com parâmetros sintéticos, sem cliente AWS ou aplicação automática.
4. Explicitar limite PutImage/stable, alternativa pré-provisionada condicionada,
   fronteiras de autorização e plano futuro isolado para Cloud/IAM.
5. Acrescentar testes estruturais/negativos e referências mínimas; executar
   make check, documentais, check_ai_context e diff --check. Registrar resultados
   novos, limitações e handoff para revisão independente.

## Riscos e reversão

Uma policy pode parecer restrita e ainda permitir retag de stable, mudança
de mutabilidade ou ampliação por outras policies. Documentar o alcance;
não contornar essas limitações. Reversão desta entrega remove somente novos
artefatos locais e referências, sem afetar IAM. Rollback remoto futuro exige
plano específico e autorização; nenhum recurso é criado nesta sessão.
