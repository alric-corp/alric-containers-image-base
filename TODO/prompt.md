Vamos executar a adaptação corporativa por marcos pequenos, um por sessão.

MARCO DESTA SESSÃO: M00
ARQUIVO: TODO/marcos-dev/00-baseline-e-escopo.md

Leia inicialmente apenas:
1. TODO/marcos-dev/CONTEXTO.md
2. TODO/marcos-dev/PROGRESSO.md
3. TODO/marcos-dev/00-baseline-e-escopo.md

Execute somente M00, respeitando o escopo e os critérios do documento.

FORMA DE TRABALHO

- Não reconstrua toda a arquitetura nem releia a conversa anterior.
- Não leia todos os arquivos de TODO/, a RFC ou o repositório inteiro.
- Consulte outros arquivos apenas quando uma dependência concreta do marco
  exigir; leia primeiro o trecho relevante.
- Não crie subagentes nem tarefas paralelas nesta sessão.
- Use comandos de leitura autorizados sem pedir confirmação a cada comando.
- Se uma ferramenta negar acesso, não contorne a restrição.

EXECUÇÃO DO M00

- Confirme o repositório, a branch atual e o SHA completo.
- Confira git status --short, git branch --show-current,
  git rev-parse HEAD e git worktree list.
- Registre alterações locais e trabalhos paralelos sem interferir neles.
- Não deduza que uma sessão está ativa apenas porque existe um worktree.
- Confirme o escopo descrito nos documentos:
  develop = DEV;
  staging = HOM, fora desta ativação;
  main = PROD futuro, inativo;
  stable independente por ambiente.
- Registre o último resultado de CI com SHA/run somente se houver
  evidência acessível. Caso contrário, marque NÃO_VERIFICADO.
- O commit 2801363 é uma referência histórica, não uma exigência de checkout.

LIMITES

Neste marco, não altere código, branch, worktrees ou Settings.
Não faça commit, push, PR, merge, dispatch ou mudanças em AWS.
Não execute build, publicação, promoção, apply ou suíte pesada.
Não use reset, stash, prune ou exclusão de arquivos.
A única alteração autorizada é o registro em PROGRESSO.md.

Se houver conflito, autoria desconhecida de alterações ou informação
indispensável indisponível, preserve tudo e registre o bloqueio exato.
Pergunte somente o que não puder verificar com o acesso permitido.

ENCERRAMENTO

Atualize em PROGRESSO.md apenas:
- baseline;
- linha do M00;
- bloqueios ativos;
- checkpoint curto;
- próxima ação única.

Preserve os registros dos outros marcos.
Não copie logs extensos para o checkpoint.

Responda no formato curto definido em CONTEXTO.md, incluindo os campos
específicos do M00.

Use CONCLUIDO, PARCIAL ou BLOQUEADO conforme a evidência.
Não marque teste não executado como PASS.

Pare ao concluir ou bloquear M00. Não avance automaticamente para M01.