ATUALIZE OS ROTEIROS CORPORATIVOS EM TODO/, SEM ALTERAR O PRODUTO DO LAB.

Estamos no repositório pessoal alric-containers-image-base.

A pasta TODO/ contém os roteiros usados posteriormente no repositório
corporativo itau-corp/itau-xj7-container-image-base.

No corporativo, o trabalho já avançou até M04. Isso não significa que todos
os itens de M00–M04 estejam concluídos: o PROGRESSO.md corporativo preenchido
é a fonte de verdade sobre estados, evidências e bloqueios.

Esta tarefa é DOCUMENTAÇÃO APENAS.

OBJETIVO

Preservar os marcos M00–M13 e incorporar a separação entre:

1. governança de PR/merge;
2. Terraform plan;
3. Terraform apply e read-back;
4. primeira execução da Factory;
5. operação recorrente por schedule.

Não criar uma nova sequência paralela de marcos.

LIMITES

- Alterar somente Markdown em TODO/.
- Não alterar workflows, scripts, policies executáveis, Terraform ou IAM.
- Não alterar o funcionamento do LAB.
- Não mudar a default branch do LAB.
- Não fazer substituição global de main por develop no repositório.
- Não executar build, apply, publicação, promoção ou certificação.
- Não disparar workflows nem alterar Settings.
- Não fazer commit, push ou merge automaticamente.
- Não copiar dados internos corporativos para o repositório público.

LEITURA INICIAL

Leia:
- TODO/README.md
- TODO/CONTEXTO.md
- TODO/prompt.md
- TODO/PROGRESSO.md
- os marcos M01, M04, M05, M06, M07, M08, M09 e M10.

Consulte outros documentos somente se forem dependências concretas.

Não reconstrua a arquitetura inteira nem releia todos os relatórios históricos.

1. CORRIGIR OS CAMINHOS DOS PROMPTS

Os documentos estão diretamente em TODO/.

Corrija referências operacionais que ainda apontem para TODO/marcos-dev/.
Não mova os documentos para outra pasta.

Preserve referências históricas somente quando forem claramente necessárias,
sem deixá-las como instrução de execução atual.

2. PRESERVAR O CHECKPOINT CORPORATIVO

Não substitua nem zere um PROGRESSO.md preenchido.

A versão do LAB pode ser um template; não a preencha como se tivesse
executado os marcos corporativos.

Documente no README que, ao atualizar os roteiros no trabalho:
- preservar PROGRESSO.md e as evidências corporativas existentes;
- reconciliar alterações locais dos documentos antes de substituí-los;
- não importar o template vazio por cima do progresso real.

3. INCORPORAR AS DECISÕES CORPORATIVAS

Branch model:
- develop = DEV e default branch corporativa;
- staging = HOM, fora desta primeira ativação;
- main = PROD futuro, inativo nesta fase;
- stable independente por ambiente.

Configuração:
- a conta AWS é obtida pelo contrato do iupipes.yml/.iupipes.yml;
- a role é resolvida/construída dinamicamente pelo mecanismo corporativo;
- confirmar o nome real do arquivo e os campos no ambiente corporativo;
- não inventar o esquema do iupipes;
- não duplicar conta/role em GitHub Environments por conveniência.

GitHub Environment:
- não é obrigatório apenas para armazenar conta/role;
- não remover um Environment existente sem avaliar seus controles e efeitos
  sobre OIDC;
- seguir o contrato corporativo efetivo.

Runners:
- Linux self-hosted ARC/EKS;
- variáveis corporativas RUNNER_EKS_OD_* aprovadas;
- nenhum fallback para runner público;
- capacidades e tamanho avaliados por job;
- reusable consumido por SHA imutável com a migração ARC presente.

4. GOVERNANÇA DE DEVELOP

Documentar:
- alterações normais entram por PR;
- push direto, force push e exclusões são controlados pelas regras efetivas;
- CI obrigatório e plan obrigatório quando houver impacto de Infra;
- confirmar regras de branch protection e rulesets, sem inferir ausência
  apenas por HTTP 404;
- preservar políticas corporativas existentes e exigir autorização para
  alterações em Settings.

Os required checks devem usar os nomes/contextos reais dos jobs emitidos.

Não configurar como obrigatório um check que desaparece em PRs sem impacto
de Infra. Se houver execução condicional, prever um resultado final
obrigatório e previsível:
- sem impacto comprovado: não aplicável;
- com impacto: plan deve concluir;
- falha, cancelamento ou ausência inesperada: não aprovar.

Não implementar essa governança no LAB; apenas atualizar o roteiro.

5. CRIAR UM DOCUMENTO TRANSVERSAL

Criar:
TODO/CONTRATO-INFRA-E-FACTORY.md

Conteúdo:
- fonte da configuração corporativa;
- matriz de eventos e ações;
- primeiro provisionamento versus operação recorrente;
- definição de INFRA_READY;
- fronteira entre build/validação e publicação;
- dependências, concorrência e falhas;
- links para M05, M06, M08 e M10.

Não duplicar o manual completo da Factory.

6. PRIMEIRO PROVISIONAMENTO

Documentar esta ordem:

M05:
plan DEV revisado, sem apply.

M06:
apply autorizado pelo mecanismo corporativo e read-back.

M07:
certificados/trust concluídos, podendo ser preparados em paralelo ao
provisionamento sem mutações concorrentes conflitantes.

M08:
primeiro candidate Go depois de satisfeitos os pré-requisitos aplicáveis
de ARC, identidade, Infra e certificados.

M09:
primeiro stable com autorização e gates próprios.

M06 não autoriza automaticamente M08 ou M09.

Antes de um merge que dispara apply, identificar também os demais workflows
que esse merge pode disparar. A primeira ativação não deve publicar imagens
antes do aceite dos seus pré-requisitos.

7. OPERAÇÃO RECORRENTE

Registrar a matriz desejada:

PR para develop:
- CI;
- plan quando houver impacto de Infra;
- validação da Factory conforme impacto;
- nenhum apply/publicação.

Merge em develop somente de Infra:
- apply pelo mecanismo corporativo;
- read-back;
- não exigir build de imagem sem impacto na Factory.

Merge somente de Factory:
- nenhum apply;
- preflight do destino;
- build, gates e publicação.

Merge com impacto em Infra e Factory:
- inicialmente executar apply/read-back antes de iniciar o engine;
- não deixar dois workflows independentes correrem sem coordenação;
- paralelizar build sem AWS com apply é uma otimização futura, não requisito
  deste primeiro E2E.

Schedule de build:
- executa na develop/default;
- não executa Terraform apply;
- usa Infra já provisionada;
- executa preflight, build, gates e publicação.

Schedule de promoção:
- não executa apply nem rebuild;
- respeita soak, seleção, quarentena, trust, scan, pair binding,
  controle operacional e read-back.

8. DEFINIR INFRA_READY

INFRA_READY não pode ser apenas uma variável estática dizendo true.

A prova deve considerar:
- conta/região/destino corretos;
- repositórios solicitados existentes;
- configuração ECR exigida pelo contrato;
- autenticação adequada à operação;
- nenhuma alteração concorrente incompatível dos mesmos destinos.

Após apply:
read-back comprova a Infra criada/alterada.

Sem alteração de Infra, inclusive schedule:
preflight comprova o destino existente.

Ausência ou configuração inválida:
falhar fechado; o publisher não cria nem repara ECR.

Preflight não equivale a transação nem impede sozinho uma alteração concorrente.
A coordenação com mutações dos mesmos destinos deve ser explicitada.

9. DEPENDÊNCIAS ENTRE JOBS E WORKFLOWS

Explicar que needs conecta jobs da mesma execução.

Não sugerir needs apontando para um job de outro workflow independente.

Se a plataforma oferecer reusables compatíveis, documentar a possibilidade de
um caller orquestrar:
infra -> read-back -> build/publish.

Se o executor corporativo já controlar essa sequência, usar seu contrato real.

Não inventar workflow_call, inputs, outputs, gates ou locks que ainda não existem.

Para caminhos sem alteração de Infra:
- apply pode não ser necessário;
- publicação deve depender de readiness comprovada;
- skip legítimo de apply não pode ser confundido com falha;
- apply necessário que falhou/cancelou deve bloquear a publicação.

Não usar always() isoladamente como autorização para publicar.
Não confundir concurrency com garantia de ordem Infra antes de Build.

10. ATUALIZAR M05

Incluir:
- verificar o gatilho real: PR, push feature ou exigência da plataforma;
- evitar plan duplicado em push feature + PR sem necessidade;
- usar executor corporativo e configuração iupipes;
- identificar backend/state efetivos, sem importar os do LAB;
- considerar cancelamentos deliberados como tais;
- verificar efeitos parciais apenas se uma operação de apply chegou a iniciar;
- revisar creates/updates/destroys/replacements;
- tratar detailed-exitcode 2 como plano com mudanças, não falha;
- não executar apply.

Não presumir que todo plan é absolutamente livre de efeitos: identificar
bootstrap de backend/locking realizado pela plataforma e a autorização
necessária, sem criar um mecanismo alternativo.

11. ATUALIZAR M06

Incluir:
- exigir o plano e a revisão aprovados;
- merge aprovado que dispara apply conta como a execução autorizada;
- não fazer outro dispatch automaticamente depois do merge;
- se houver replan, validar correspondência com o escopo aprovado;
- manter a aplicação pelo mecanismo corporativo;
- read-back e plano posterior quando aplicável;
- nenhum disparo adicional da Factory ou promoção neste marco;
- preservar evidência de execução parcial em caso de falha.

12. ATUALIZAR M08 EM DUAS FASES

PREPARAR:
- revisar encadeamento e triggers relevantes;
- confirmar M03/M04/M06/M07 aplicáveis;
- resolver apenas diferenças pendentes;
- verificar preflight e comportamento em falha/skip;
- identificar exatamente qual execução será disparada.

EXECUTAR:
- somente com autorização de uma publicação;
- usar o engine existente e o par Go;
- não executar apply;
- verificar artifacts, contratos, publicação e evidências por digest;
- não mover stable.

Não substituir o engine por uma Factory paralela.

13. ATUALIZAR M10 EM DUAS FASES

PREPARAR:
- conferir default branch develop, cron, health e escopo;
- provar que o caminho schedule não alcança apply;
- manter coordenação com mudanças de Infra;
- distinguir autorização de build e autorização de promoção.

ATIVAR/OBSERVAR:
- somente após os aceites e autorização operacional;
- observar execuções reais e registrar checkpoints;
- não manter agente esperando indefinidamente;
- nenhuma promessa de execução pontual do cron;
- nenhuma expansão automática para FULL.

FULL permanece uma mudança de rollout posterior à certificação pertinente.

14. TRANSFORMAR PROMPT.MD EM INICIADOR REUTILIZÁVEL

Usar campos:
MARCO
FASE = PREPARAR | EXECUTAR
ARQUIVO_DO_MARCO
AUTORIZACAO_EXTERNA

O iniciador deve:
- ler CONTEXTO.md, PROGRESSO.md e apenas o marco selecionado;
- consultar CONTRATO-INFRA-E-FACTORY.md quando necessário;
- preservar marcos anteriores;
- ampliar leitura somente por dependência concreta;
- parar ao concluir/bloquear o marco;
- exigir autorização específica para ações externas.

Não deixar M00 fixo como início obrigatório de toda sessão.

15. VALIDAÇÃO E ENTREGA

- Verificar links relativos e git diff --check.
- Não executar builds nem suítes pesadas por mudança documental.
- Não alterar statuses para PASS apenas porque o roteiro foi atualizado.
- Conferir que somente arquivos Markdown de TODO/ foram alterados.
- Listar arquivos alterados e diferenças principais.
- Mostrar o prompt exato para iniciar M05 no corporativo.

Relatório final:

ESCOPO = DOCUMENTACAO_CORPORATIVA_NO_LAB
MARCOS_M00_M13 = PRESERVADOS
CAMINHOS_TODO = CORRIGIDOS
CHECKPOINT_CORPORATIVO = NAO_SOBRESCRITO
CONTRATO_INFRA_FACTORY = DOCUMENTADO
SCHEDULE_EXECUTA_APPLY = NAO_NO_DESENHO_PROPOSTO
CONFIGURACAO_CONTA_ROLE = IUPIPES_E_MODELO_DINAMICO
PRODUTO_LAB_ALTERADO = NAO
ACOES_EXTERNAS = NENHUMA
PROXIMO_MARCO_CORPORATIVO = M05_CONFORME_CHECKPOINT_REAL