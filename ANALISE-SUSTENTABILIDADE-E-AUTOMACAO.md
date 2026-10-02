# Sustentabilidade e automação da Factory Distroless

Registro da análise em **2 de outubro de 2026**, com base no checkpoint corporativo de **1 de outubro de 2026**, na inspeção do laboratório Alric e nas referências oficiais consultadas durante a análise.

Este documento avalia a manutenção da Factory a longo prazo, o tratamento de CVEs, o papel do Dependabot e as oportunidades de automação da atualização e entrega das imagens. As recomendações são propostas de evolução; seu registro não altera políticas, workflows ou autorizações de execução.

## Avaliação geral

A arquitetura pode ser sustentável a longo prazo. Pelo checkpoint, a operação ainda exige intervenção humana demais para entregar atualizações com previsibilidade.

A recomendação é preservar `develop` como fonte do código, build único por artifact, promoção por digest, assinatura, SBOM e certificação dos consumidores. As maiores melhorias estão no tratamento de CVEs, na seleção de releases e na recuperação após falhas.

O checkpoint corporativo registra publicação de 16 candidates e certificação de 18 execuções, mas ainda não comprova a promoção FULL DEV/HOM daquele ciclo. Health e recovery também têm pendências. Esses registros não confirmam o que os agendamentos executaram posteriormente.

As verificações locais deste documento dizem respeito ao laboratório Alric. Configurações encontradas aqui não devem ser atribuídas automaticamente ao repositório corporativo.

## Decisões corporativas confirmadas em 2 de outubro

O usuário confirmou que o próprio time é owner da solução, **FULL é o baseline operacional permanente do corporativo, composto pelas 16 imagens**, e custo/capacidade dos runners estão resolvidos. Esses pontos deixam de ser decisões abertas.

Go-only pertence ao histórico de validação do LAB. FULL não é uma exceção temporária no corporativo e não depende de reaprovação periódica. Uma lógica de `execution_scope.review_by` cuja finalidade seja renovar essa exceção deve ser removida do desenho corporativo. Uma revisão futura de saúde, custo ou capacidade pode existir separadamente, sem alterar ou suspender automaticamente o baseline FULL.

Para a leitura cross-repo do monitor, o caminho escolhido é **PAT do GitHub**. GitHub App está fora do desenho disponível. O trabalho restante é configurar o secret, separar o token usado nas consultas cross-repo, integrar as correções e verificar a operação real.

O **`pipeline-health.yml` e seu resumo no GitHub Actions constituem o canal oficial de alerta operacional nesta fase**. `channel.external_destination = null` é intencional e significa que um destino externo não se aplica à fase atual. Integração com Microsoft Teams, por exemplo via Power Automate, permanece como evolução futura caso a experiência operacional demonstre essa necessidade.

O plano concreto está em [DUVIDAS-PIPELINE-HEALTH.md](DUVIDAS-PIPELINE-HEALTH.md). Estas confirmações registram decisões do owner; não comprovam instalação de credenciais, atualização da configuração corporativa, CI ou promoção.

## Correção de CVEs

A correção é parcialmente manual, dependendo da disponibilidade do patch e de como a dependência foi declarada.

| Situação | Tratamento esperado |
| --- | --- |
| Pacote corrigido disponível no mirror e aceito pela receita atual | Novo build automático pode incorporar a correção sem mudança no Git |
| Correção exige alterar versão fixada, receita Apko/Melange ou dependência | Bot pode abrir PR; CI valida e revisão autoriza a mudança |
| Correção publicada upstream, mas ausente no mirror ou em uma arquitetura | Acompanhar disponibilidade e resolver sincronização; repetir o build não resolve a ausência |
| Ainda não existe correção | Triagem, mitigação ou exceção com responsável e prazo de revisão |

Boa parte desse trabalho pode ser automatizada. O checkpoint ainda não demonstra o ciclo completo abaixo funcionando de forma rotineira:

```text
Detectar CVE
    → identificar imagens e aplicações afetadas
    → obter correção disponível nas origens aprovadas
    → gerar nova release
    → validar e promover
    → atualizar aplicações
    → comprovar a resolução
```

**Uma correção de CVE gera um novo artifact. Esse artifact continua sendo construído uma vez e promovido sem rebuild entre DEV e HOM.** A necessidade de uma nova release para corrigir uma vulnerabilidade é compatível com a preservação do mesmo digest durante sua promoção.

## Dependabot e atualização de dependências

No laboratório, o arquivo [`.github/dependabot.yml`](.github/dependabot.yml) configura atualizações semanais para dependências Python e GitHub Actions, incluindo reusable workflows. Essa inspeção não confirma a configuração corporativa.

Dependabot também suporta referências Docker, mas não oferece cobertura nativa de receitas Apko/Melange e seus pacotes Wolfi. Sua presença não comprova que todos os componentes das imagens estão sendo atualizados. Fonte: [ecossistemas suportados pelo Dependabot](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories).

| Necessidade | Recomendação |
| --- | --- |
| Atualizar Python e Actions | Manter Dependabot |
| Incorporar patches já permitidos pelas receitas | Build agendado e/ou disparado pela disponibilidade de atualização |
| Atualizar versões fixadas em formatos próprios | Avaliar Renovate |

Renovate possui datasource APK com suporte documentado a Wolfi e permite criar leitores para formatos próprios. Uma integração com Apko/Melange exigiria configuração e testes, incluindo o mirror corporativo e as arquiteturas utilizadas. Fontes: [APK e Wolfi](https://docs.renovatebot.com/modules/datasource/apk/) e [custom managers](https://docs.renovatebot.com/modules/manager/regex/).

## Gaps e evolução recomendada

### Seleção e identidade da release

O checkpoint descreve DEV selecionando candidates por imagem, certificação vinculada a uma publicação específica e HOM exigindo um lote coerente. A descoberta também percorre runs antigos, incluindo execuções sem promoção. Essa combinação permite que existam 16 imagens certificadas sem que a seleção consiga formar a release promovível.

A recomendação é iniciar a promoção a partir de um **manifesto imutável da release certificada**, contendo todos os digests e vínculos com as evidências. As transições DEV/HOM devem gerar recibos persistentes, inclusive para retomada após falha.

O histórico de Actions continua sendo evidência de execução. A identidade e o estado da release devem ser explícitos, sem depender de reconstruir seu significado a partir de nomes de jobs e buscas no histórico. As verificações de integridade, origem, run, attempt e digest permanecem obrigatórias.

### Vigilância das imagens já entregues

O checkpoint comprova scans durante o pipeline. Não comprova reavaliação contínua dos digests atualmente consumidos. Uma imagem aprovada pode receber uma CVE posteriormente, sem alteração nos seus bytes.

A recomendação inicial é executar Trivy periodicamente sobre os digests de HOM, nas duas arquiteturas, com deduplicação e acompanhamento dos achados.

Se a organização já utiliza Amazon Inspector, ECR enhanced scanning oferece monitoramento contínuo e eventos de findings. É uma alternativa a avaliar dentro da operação existente, com cobertura e janela de monitoramento configuradas. Fonte: [ECR enhanced scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html).

### Atualização das aplicações consumidoras

Mover `HOM:stable` não atualiza aplicações já construídas. O checkpoint não comprova um mecanismo que relacione o digest vulnerável da base às aplicações afetadas e acompanhe seu rebuild e deploy.

```text
Digest vulnerável da base
    → aplicações afetadas
    → rebuild com a base corrigida
    → deploy confirmado
```

Para Go, uma correção no toolchain pode exigir recompilar a aplicação com a imagem `-dev` corrigida. A publicação de uma nova base não modifica um binário estático já construído.

A métrica recomendada inclui o **tempo até a aplicação corrigida estar implantada**, além do tempo até publicar a base.

### Recovery e retenção

O checkpoint registra zero ensaios de recovery e limitações na coordenação dos pares DEV. Também descreve retenção de builds de sete dias. É necessário verificar se as regras efetivas preservam releases anteriores recuperáveis e suas evidências pelo período necessário.

A retenção deve considerar manifests, imagens, assinaturas, attestations e SBOMs. Não basta conservar apenas o digest em um documento se o artifact ou sua evidência já tiver expirado.

Uma barreira de validação antes das escritas não torna as alterações de 16 tags ECR transacionais. A evolução deve incluir estado explícito de falha parcial, retomada idempotente e prevenção de repromoção de artifacts retirados. Recovery precisa ser ensaiado com destinos aprovados e read-back independente.

### Evidência durante o soak

Se o soak apenas espera cinco horas, seu benefício operacional é limitado. É necessário confirmar que atividades ocorrem durante esse período.

A recomendação é associar o soak a execuções de aplicações representativas, verificações periódicas e resultados observáveis. O início de cada intervalo deve usar um timestamp persistente da transição correspondente, evitando depender apenas de `updated_at` do workflow.

No checkpoint, a decisão mais recente de **5h DEV + 1h HOM** ainda estava implementada localmente, enquanto outras seções descreviam políticas anteriores. O valor efetivo deve vir da configuração integrada e ser registrado na evidência da execução. Esta análise não altera o soak.

### Acoplamento do catálogo completo

Certificar todo o catálogo é útil. Exigir que todas as linguagens avancem juntas pode atrasar uma correção de Java por um problema independente de Node.

FULL é o baseline corporativo permanente. Como possibilidade futura de mudança do contrato, caso o acoplamento passe a atrasar correções, pode-se avaliar:

- certificação FULL periódica;
- releases por framework ou par coerente;
- verificação FULL para mudanças compartilhadas.

Essa possibilidade não é pré-requisito para fechar as lacunas atuais nem exige reavaliar periodicamente a autorização de FULL. Uma mudança desse contrato precisaria de decisão explícita. O lote atual continua sujeito ao contrato FULL vigente, sem combinar evidências incompatíveis ou reduzir seu escopo para contornar um bloqueio.

### Health e tratamento operacional de CVEs

Health com falhas e metadados de revisão vencidos foram registrados no checkpoint. As decisões atuais encerram as dúvidas de escopo, custo/capacidade e canal: FULL é permanente, os runners estão resolvidos e o GitHub Actions é o mecanismo oficial de alerta nesta fase. O trabalho restante é ajustar a implementação e a documentação corporativas, incluindo remover a semântica de exceção Go-only e sua exigência de renovação em `execution_scope.review_by`.

O acesso aos pins será tratado com PAT, enquanto as correções devem distinguir `mismatch` de `unverified` e manter a falha quando a origem não puder ser verificada. O monitor precisa reconhecer as promoções efetivas e calcular corretamente a idade por imagem. A ausência de destino externo não deve gerar pendência ou falha de health nesta fase; outras verificações continuam obrigatórias.

O fechamento técnico está detalhado em [DUVIDAS-PIPELINE-HEALTH.md](DUVIDAS-PIPELINE-HEALTH.md): PAT funcional, correções integradas, CI Linux/ARC aprovado, health coerente, DEV FULL comprovado e HOM FULL promovido com os mesmos artifacts e read-back dos 16 digests. Health verde sozinho não comprova a promoção HOM. Esses critérios são requisitos de evidência, não resultados já obtidos por este registro.

No laboratório, o [gate Trivy](scripts/pipeline/artifacts/scan_images.py) utiliza `--ignore-unfixed`, e existe um [relatório separado de CVEs sem correção](scripts/pipeline/release/report_unfixed_cves.py), de caráter informativo. Essa configuração local não comprova a política corporativa efetiva.

**Sem correção disponível não significa risco aceito.** Achados relevantes precisam de responsável, acompanhamento e decisão rastreável. Uma falha na coleta da visibilidade também precisa ser distinguida da ausência de vulnerabilidades.

## Prioridades propostas

O trabalho imediato é concluir os ajustes e reunir as evidências do plano de [fechamento corporativo](DUVIDAS-PIPELINE-HEALTH.md). As prioridades abaixo tratam da evolução de longo prazo; não reabrem decisões de escopo, runners ou canal já encerradas pelo owner.

| Ordem | Entrega | Evidência de conclusão |
| --- | --- | --- |
| 1 | Estabilizar a entrega de releases | Manifesto explícito, promoção retomável, health funcional e recovery ensaiado |
| 2 | Automatizar o ciclo de CVEs | Re-scan, classificação, acompanhamento de patches e geração de nova release validada |
| 3 | Fechar a atualização dos consumidores | Relação entre base e aplicações, rebuild e deploy rastreáveis |

## Conclusão

A recomendação é manter a Factory e investir primeiro em tornar atualizações e falhas comuns previsíveis. Dependabot, atualização automática de pacotes e scans contínuos podem cobrir partes diferentes do trabalho.

A sustentabilidade deve ser avaliada pela capacidade de detectar, corrigir, entregar e comprovar a adoção de uma atualização com pouca intervenção, preservando a possibilidade de recuperar uma release anterior. A confiabilidade da entrega depende dos contratos executáveis da Factory.
