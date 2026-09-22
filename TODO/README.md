# Marcos pequenos — Factory Distroless no DEV corporativo

**Uso:** um marco por sessão do Claude Code.  
**Escopo:** conectar e comprovar a implementação existente no DEV, sem refazer a Factory nem antecipar HOM/PROD.  
**Base:** análise compartilhada sobre `develop@2801363` e os ajustes discutidos em seguida. Este pacote não representa revalidação do repositório.

## Como colocar no projeto

Copie esta pasta para:

```text
itau-xj7-container-image-base/
└── TODO/
    └── marcos-dev/
```

O ZIP foi montado com `TODO/marcos-dev/` na raiz. Ele contém somente os novos Markdown; não substitui `adjust-branches.md`, `adjust-certificates.md` ou os documentos de arquitetura existentes. Revise arquivos de mesmo nome antes de extrair por cima de uma versão editada.

Arquivos apenas locais não aparecerão em outro clone. Versione pelo processo de documentação do projeto quando desejar compartilhar o pacote; este pacote não fez commit, push ou upload ao repositório.

## Os três arquivos de apoio

- [CONTEXTO.md](CONTEXTO.md): contexto curto e limites comuns. Evita repetir o histórico em cada tarefa.
- [PROGRESSO.md](PROGRESSO.md): estado, bloqueios e checkpoint para a sessão seguinte.
- Este índice: escolha do próximo marco. Não precisa ser relido integralmente a cada execução.

## Índice de execução

| Marco | Trabalho | Fronteira principal |
|---|---|---|
| M00 | [Registrar a baseline e o escopo de DEV](00-baseline-e-escopo.md) | Baseline em leitura |
| M01 | [Fechar Settings, variáveis e aprovações do GitHub](01-github-settings-e-variaveis.md) | Settings / inventário |
| M02 | [Provar checkout e acesso ao reusable no ARC](02-arc-checkout-e-reusable.md) | Smoke leve no ARC |
| M03 | [Provar capacidades de build e rede do ARC](03-arc-ferramentas-arquiteturas-e-rede.md) | Capacidades e conectividade |
| M04 | [Vincular identidades, IAM e OIDC ao DEV real](04-identidades-iam-e-oidc-dev.md) | Identidade e autenticação |
| M05 | [Revisar o plano de infraestrutura DEV](05-terraform-plan-dev.md) | Plan, sem apply |
| M06 | [Aplicar e verificar infraestrutura DEV](06-terraform-apply-e-readback-dev.md) | Apply autorizado |
| M07 | [Fechar certificados e confiança corporativa](07-certificados-e-trust-corporativo.md) | PKI / trust |
| M08 | [Publicar o primeiro candidate Go em DEV](08-candidate-go-dev.md) | Publicação de candidate Go |
| M09 | [Promover e verificar o primeiro stable DEV](09-primeiro-stable-dev.md) | Primeiro stable DEV |
| M10 | [Ativar e observar a operação agendada](10-schedules-e-saude-operacional.md) | Operação periódica |
| M11 | [Certificar o catálogo completo em DEV](11-certificacao-full-do-catalogo.md) | Candidates FULL |
| M12 | [Executar aplicações consumidoras nas duas arquiteturas](12-apps-consumidoras-multiarch.md) | Apps, ECR somente leitura |
| M13 | [Validar recovery DEV e fechar o aceite](13-recovery-dev-e-fechamento.md) | Recovery e limites de aceite |

## Ordem e dependências

```text
M00 → M01 → M02 → M03
              └→ M04 → M05 → M06
                    M03 → M07

M03 + M04 + M06 + M07
              ↓
             M08 → M09 → M10
                      └→ M11 → M12

M09 + destino anterior aprovado + controles revisados
              ↓
             M13
```

M03 e M04 podem avançar em sessões separadas sem se sobrepor. M07 pode avançar enquanto o provisionamento é tratado. Isso não autoriza duas sessões a modificar os mesmos arquivos ou executar operações AWS em paralelo.

M10 pode ser observado enquanto M11/M12 são planejados, com custo e autorizações separados. M12 não depende de stable: consome candidates publicados por digest. A ordem não obriga encerrar uma janela de observação inteira antes de escrever o plano do próximo marco.

## Prompt de início

Comece por M00:

```text
Leia apenas TODO/marcos-dev/CONTEXTO.md,
TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/00-baseline-e-escopo.md.

Execute somente M00. Não implemente outros marcos.
Não faça push, merge, dispatch ou mudanças externas.
Use o formato curto de entrega e atualize PROGRESSO.md.
```

Os demais arquivos também têm um prompt específico no final. Em uma sessão nova, forneça os três caminhos correspondentes; não recoloque toda a análise nem a conversa.

## Como economizar contexto sem enfraquecer validação

Leia só os caminhos do marco. Para arquivo grande, leia primeiro as funções/jobs relevantes. Expanda quando uma dependência concreta exigir. Não execute uma busca global de cada termo em toda sessão.

Faça uma tarefa de cada vez: diagnóstico, correção local ou execução aprovada. Salve run IDs, SHAs, caminhos de evidência e o próximo passo no checkpoint. Relatórios de mil linhas não precisam voltar para o chat.

Para mudanças locais, use testes focados. Para PRs, preserve os checks exigidos. Para documentação, prefira verificação de links/diff existente. Evite executar unit/integration repetidamente por alvos que já os incluem. Nenhuma economia de tokens autoriza marcar teste não executado como PASS.

## Aprovação para operações externas

Os arquivos são roteiros, não autorizações de escrita. Primeiro o agente apresenta a ação e seus destinos. Para M06/M08/M09/M11/M13, use uma autorização objetiva, por exemplo:

```text
AUTORIZO Mxx: <ação exata>.
Ambiente: DEV. Conta/região: <valores verificados>.
Revisão/plano/run/digests: <identidade aprovada>.
Limite: uma execução pelo mecanismo corporativo previsto.
Não autorizo retry automático, alteração de outro ambiente ou bypass de gates.
```

Para M09/M13, registre também o estado esperado de stable antes/depois e o procedimento de concorrência/fechamento do controle. Para M12, autorize apenas teste consumidor com leitura do ECR e imagens derivadas locais.

## Pontos corrigidos em relação ao plano original

ECR provisionado não implica `STABLE_PROMOTION_AUTHORIZED=true`. Environment/variáveis e OIDC precisam combinar no ponto real de consumo. Runner selecionado não prova Docker/QEMU/egress. Remover redundância de certificados não significa remover raízes públicas. Um App Certification FULL não deve receber inventário só de Go. Recovery individual não deve ser chamado de recuperação coordenada do par.

## Fora do escopo inicial

Implementar promoção DEV → HOM, ativar `main`/PROD, importar infraestrutura/state do LAB, trocar a arquitetura dos reusables ou transformar o schedule V1 em FULL automaticamente. Esses itens exigem tarefas e aceite próprios.

**Concluído significa:** o critério do marco foi comprovado na revisão e no ambiente registrados, não apenas que o YAML correspondente existe.
