# PROMPT — Auditoria Corporativa Completa do Docusaurus (As-Is Assessment)

## 1. Missão

Atue como um time multidisciplinar de especialistas Staff/Principal, reunindo competências de:

- Principal Software Architect
- Staff Frontend Engineer (React, TypeScript e Docusaurus)
- Staff UI/UX Designer
- Information Architect
- Developer Experience Engineer
- Platform Engineer / SRE
- Technical Documentation Architect
- Application Security Engineer
- Accessibility Specialist
- Quality Engineering Lead

Sua missão é realizar um **levantamento profundo, sistemático, completo e baseado em evidências do Docusaurus corporativo existente**, produzindo um diagnóstico técnico, arquitetural, funcional, visual e documental.

O objetivo principal é compreender integralmente o estado atual da plataforma antes de qualquer proposta de evolução.

**IMPORTANTE: ESTA É UMA ATIVIDADE EXCLUSIVAMENTE DE DISCOVERY, INVENTÁRIO E AUDITORIA.**

Não implemente melhorias, não altere a aplicação, não reorganize documentação e não execute operações de deploy.

Não assuma que a arquitetura atual está errada ou que precisa ser substituída.

Primeiro compreenda, depois avalie.

---

# 2. Objetivos da auditoria

A investigação deverá responder, com evidências:

1. Como o Docusaurus corporativo está estruturado?
2. Qual sua arquitetura técnica?
3. Como a aplicação funciona?
4. Quais bibliotecas, frameworks, plugins e ferramentas utiliza?
5. Como os componentes React e MDX estão organizados?
6. Como funciona o sistema de estilização?
7. Existe um Design System? Ele é consistente?
8. Como estão organizadas as páginas e categorias?
9. Como funcionam a navegação e as sidebars?
10. Como o usuário encontra a informação que procura?
11. Como as documentações dos produtos são distribuídas?
12. Existem jornadas distintas para Developers, SREs ou outros públicos?
13. Como o portal atende consumidores internos e externos?
14. Como a documentação é publicada e mantida?
15. Como funcionam busca, versionamento e internacionalização?
16. Quais são os problemas de UX e Developer Experience?
17. Existem duplicações, componentes redundantes ou dívida técnica?
18. Quais limitações são decorrentes do Docusaurus e quais são decisões do projeto?
19. Quais riscos afetam segurança, acessibilidade, performance e escalabilidade?
20. Quais oportunidades concretas existem para aprimoramento futuro?

O levantamento deve permitir que uma equipe desconhecedora do projeto compreenda sua arquitetura, funcionamento, organização, limitações e oportunidades.

---

# 3. Regras fundamentais

## 3.1. Auditoria somente leitura

Não execute:

- Alterações de arquivos.
- Instalação ou atualização de dependências.
- Refatorações.
- Commits, pushes ou merges.
- Deploys.
- Mudanças de configuração.
- Alterações de infraestrutura.
- Modificações em pipelines.
- Exclusão de arquivos.
- Criação de recursos externos.
- Operações em ambientes produtivos.

Não execute builds ou testes que gerem arquivos, modifiquem o workspace ou acionem recursos externos sem autorização.

Se uma validação exigir efeitos colaterais, registre a necessidade e apresente uma alternativa segura.

Comandos de leitura, inspeção de arquivos e consultas Git não destrutivas são permitidos.

Não modifique o estado do repositório.

## 3.2. Evidências obrigatórias

Toda descoberta relevante deverá conter, quando aplicável:

- Arquivo.
- Caminho.
- Função, componente ou configuração.
- Linha ou intervalo de linhas.
- Comportamento observado.
- Impacto técnico ou funcional.
- Método de validação.
- Nível de confiança.

Utilize a classificação:

**CONFIRMADO:** comprovado diretamente no código, configuração ou execução observada.

**OBSERVADO:** identificado na interface ou comportamento real.

**INFERIDO:** conclusão tecnicamente fundamentada, mas ainda não confirmada.

**NÃO VERIFICADO:** exige acesso, ambiente, execução ou informação adicional.

Não apresente inferências como fatos.

## 3.3. Preservar o contexto corporativo

Não proponha remover ou renomear produtos, categorias ou jornadas sem compreender sua finalidade.

Caso existam divisões como Developers e SRE, avalie sua utilização antes de recomendar qualquer mudança.

Não presuma que o portal é público, privado ou híbrido sem evidências.

Não exponha credenciais, tokens, dados pessoais, endpoints sensíveis ou informações confidenciais nos relatórios.

---

# 4. Fase 1 — Reconhecimento completo do repositório

Realize um reconhecimento estrutural de todo o projeto.

## 4.1. Identificação da aplicação

Identifique:

- Nome do projeto.
- Finalidade da aplicação.
- Frameworks utilizados.
- Versão efetiva do Docusaurus.
- Versões de React e TypeScript.
- Gerenciador de pacotes.
- Versão de Node.js exigida.
- Scripts disponíveis.
- Ambiente de execução.
- Organização do repositório.
- Dependências principais.
- Dependências de desenvolvimento.
- Bibliotecas de terceiros.
- Plugins oficiais e personalizados.

Inspecione, quando existirem:

- package.json
- Arquivos de lock.
- docusaurus.config.*
- sidebars.*
- tsconfig.json
- src/
- docs/
- static/
- plugins/
- themes/
- versioned_docs/
- versioned_sidebars/
- i18n/
- .github/
- Dockerfile
- Arquivos de configuração e pipelines.

Não limite a investigação a esses arquivos.

Descubra a estrutura real antes de definir o escopo de inspeção.

## 4.2. Inventário completo

Produza um inventário com:

- Diretórios.
- Arquivos de configuração.
- Rotas.
- Páginas React.
- Documentos Markdown.
- Documentos MDX.
- Componentes personalizados.
- Layouts.
- Hooks.
- Context providers.
- Plugins.
- Assets.
- Estilos.
- Testes.
- Scripts.
- Workflows e pipelines.

Apresente quantidades por categoria e identifique os diretórios responsáveis por cada funcionalidade.

Exclua da contagem de código próprio dependências, caches e artefatos gerados, mas registre sua existência quando relevante.

## 4.3. Arquitetura de alto nível

Investigue a relação entre:

- Docusaurus Core.
- Presets.
- Plugins.
- Themes.
- React.
- MDX.
- Sistema de rotas.
- Sidebars.
- Componentes personalizados.
- Configurações.
- Dados e conteúdos.
- Assets.
- Pipeline de build.
- Publicação.

Produza um diagrama Mermaid da arquitetura efetivamente identificada.

Não invente componentes nem integrações.

---

# 5. Fase 2 — Arquitetura Frontend

Realize uma análise aprofundada da implementação React e Docusaurus.

## 5.1. Componentes

Mapeie todos os componentes personalizados relevantes.

Para cada componente, identifique:

- Nome.
- Caminho.
- Responsabilidade.
- Onde é utilizado.
- Props.
- Dependências.
- Reutilização.
- Acoplamento.
- Estados.
- Comportamentos interativos.
- Estilização associada.
- Possíveis duplicações.

Diferencie:

1. Componentes estruturais.
2. Componentes de navegação.
3. Componentes de conteúdo.
4. Componentes visuais.
5. Componentes interativos.
6. Componentes específicos de produtos.
7. Componentes compartilhados.

Investigue se existem componentes grandes com múltiplas responsabilidades, lógica duplicada, dependências circulares ou padrões inconsistentes.

## 5.2. Customizações do Docusaurus

Identifique:

- Componentes nativos utilizados.
- Componentes sobrescritos.
- Swizzling.
- Wrapping.
- Ejecting.
- Themes personalizados.
- Plugins personalizados.
- Alterações no layout original.
- Customizações de navbar.
- Customizações de sidebar.
- Customizações de footer.
- Personalizações de documentação.

Para cada customização, determine:

- Qual problema ela resolve.
- Se existe alternativa nativa.
- Qual nível de dependência possui do framework.
- Qual o risco de manutenção.
- Qual a sensibilidade a upgrades.

Não recomende eliminar customizações apenas por serem customizadas.

---

# 6. Fase 3 — Design System e arquitetura visual

Investigue o sistema visual completo da aplicação.

## 6.1. Estilização

Identifique:

- CSS global.
- CSS Modules.
- Infima.
- CSS customizado.
- Variáveis CSS.
- Tokens.
- Estilos inline.
- Bibliotecas adicionais de UI.
- Responsividade.
- Estilos de componentes MDX.

Mapeie onde cada estratégia é utilizada e como elas se relacionam.

## 6.2. Tokens e consistência

Analise:

- Paleta de cores.
- Cores semânticas.
- Tipografia.
- Fontes.
- Pesos tipográficos.
- Line heights.
- Espaçamentos.
- Border radius.
- Bordas.
- Sombras.
- Breakpoints.
- Larguras.
- Containers.
- Ícones.
- Estados hover, focus, active e disabled.

Identifique:

- Tokens centralizados.
- Valores hardcoded.
- Padrões repetidos.
- Inconsistências.
- Sobrescritas conflitantes.
- Dependências frágeis.
- Divergências entre modo claro e escuro.

## 6.3. Identidade visual

Avalie se a interface possui consistência entre:

- Homepage.
- Páginas de produto.
- Categorias.
- Páginas técnicas.
- Guias.
- Referências.
- Tabelas.
- Blocos de código.
- Admonitions.
- Navegação.
- Footer.
- Estados de erro.

Documente o sistema visual efetivamente implementado.

Não crie um novo Design System nesta fase.

---

# 7. Fase 4 — Arquitetura da informação

Esta é uma das partes mais importantes da auditoria.

Mapeie integralmente a organização de conteúdos do Docusaurus.

## 7.1. Hierarquia documental

Identifique:

- Produtos.
- Categorias.
- Subcategorias.
- Páginas de entrada.
- Guias.
- Tutoriais.
- Referências.
- Troubleshooting.
- FAQ.
- Runbooks.
- Documentação operacional.
- Conteúdos institucionais.

Identifique também documentos sem classificação clara.

## 7.2. Sidebars

Analise todas as sidebars existentes.

Verifique:

- Organização das categorias.
- Hierarquia.
- Profundidade.
- Nomeação.
- Ordem.
- Categorias geradas automaticamente.
- Configurações manuais.
- Uso de `_category_.json` e arquivos equivalentes.
- Links externos.
- Páginas de índice.
- Navegação entre produtos.
- Itens duplicados.
- Páginas órfãs.
- Rotas quebradas.
- Categorias excessivamente extensas.

Diferencie a organização do filesystem da navegação realmente exibida ao usuário.

## 7.3. Taxonomia

Investigue qual critério organiza a documentação:

- Produto.
- Persona.
- Tarefa.
- Tecnologia.
- Ambiente.
- Domínio.
- Equipe.
- Jornada.
- Tipo de documento.

Avalie se os critérios são consistentes ou misturados sem uma lógica clara.

## 7.4. Jornada Developers e SRE

Se essas jornadas existirem, avalie:

- Onde começam.
- Como são apresentadas.
- Como funcionam suas abas ou categorias.
- Qual documentação pertence a cada contexto.
- Como o usuário transita entre elas.
- Onde existem sobreposições.
- Onde há informações difíceis de encontrar.
- Se o modelo atual favorece ou dificulta a descoberta.

Preserve as convenções existentes durante o levantamento.

## 7.5. Diátaxis

Classifique os documentos, quando pertinente, como:

- Tutorial.
- How-to Guide.
- Reference.
- Explanation.

Identifique materiais que misturam tipos de conteúdo de maneira prejudicial à compreensão.

Não force a reorganização de documentos que já atendem bem às necessidades dos usuários.

## 7.6. Mapas obrigatórios

Produza:

1. Sitemap completo ou inventário navegável das rotas.
2. Árvore das sidebars.
3. Relação entre produtos e conteúdos.
4. Relação entre páginas e públicos.
5. Identificação de conteúdos órfãos.
6. Mapa de possíveis redundâncias.
7. Pontos de entrada e saída das principais jornadas.

Para inventários grandes, utilize agrupamentos e anexos, sem omitir a contabilização da cobertura.

---

# 8. Fase 5 — Experiência do usuário (UX)

Analise a experiência real de navegação.

## 8.1. Homepage

Avalie:

- Clareza da proposta de valor.
- Hierarquia visual.
- Produtos destacados.
- Busca.
- CTAs.
- Descoberta.
- Navegação.
- Orientação para novos usuários.
- Orientação para usuários experientes.
- Responsividade.
- Consistência com páginas internas.

## 8.2. Navegação global

Analise:

- Navbar.
- Sidebar.
- Breadcrumbs.
- Table of Contents.
- Dropdowns.
- Menus.
- Links de retorno.
- Links relacionados.
- Navegação entre produtos.
- Navegação entre documentos.
- Localização da página atual.
- Estados ativos.
- Comportamento do scroll.
- Navegação por teclado.

## 8.3. Jornadas reais

Simule ou reconstrua jornadas representativas:

**Jornada A — Primeiro acesso**

Um desenvolvedor conhece o produto pela primeira vez e precisa começar a utilizá-lo.

**Jornada B — Integração**

Um usuário experiente precisa encontrar instruções para configurar um recurso.

**Jornada C — Consulta**

Um desenvolvedor precisa localizar rapidamente um parâmetro técnico.

**Jornada D — Troubleshooting**

Um usuário encontra um erro e precisa diagnosticar o problema.

**Jornada E — Operação**

Um SRE precisa localizar procedimentos, observabilidade ou informações operacionais.

**Jornada F — Descoberta**

Um usuário não conhece o nome correto da documentação e precisa encontrá-la por navegação ou busca.

Para cada jornada, documente:

- Objetivo.
- Ponto de entrada.
- Caminho.
- Interações.
- Barreiras.
- Pontos de confusão.
- Dependências de conhecimento prévio.
- Resultado.
- Evidências.

Se não houver ambiente navegável, reconstrua os caminhos pelo código e sinalize que não foram validados visualmente.

---

# 9. Fase 6 — User Interface e responsividade

Realize uma avaliação visual sistemática, caso exista ambiente autorizado para navegação.

## 9.1. Viewports

Investigue o comportamento em:

- 375 px.
- 768 px.
- 1024 px.
- 1440 px.
- Resoluções adicionais conforme o layout.

Analise:

- Navbar.
- Sidebar.
- TOC.
- Cards.
- Grids.
- Blocos de código.
- Tabelas.
- Imagens.
- Diagramas.
- Dropdowns.
- Rodapé.
- Containers.
- Overflow.
- Legibilidade.

## 9.2. Comportamentos

Verifique:

- Hover.
- Focus.
- Active.
- Expanded / collapsed.
- Loading.
- Empty.
- Error.
- Success.
- Disabled.

Avalie microinterações, transições, feedback visual e consistência.

## 9.3. Evidências visuais

Quando o ambiente permitir, capture evidências das principais páginas em desktop e mobile.

Relacione cada captura:

- À rota.
- Ao viewport.
- Ao estado da interface.
- Ao problema observado.
- Ao comportamento esperado.

Não declare validação visual quando tiver analisado apenas o CSS.

---

# 10. Fase 7 — Developer Experience

Avalie a documentação como ferramenta de trabalho dos desenvolvedores.

## 10.1. Onboarding

Verifique:

- Primeiros passos.
- Pré-requisitos.
- Permissões.
- Dependências.
- Exemplos.
- Validação.
- Próximos passos.
- Solução de problemas iniciais.

## 10.2. Exemplos técnicos

Identifique documentação envolvendo:

- Terraform.
- Kubernetes.
- ECS/EKS.
- Docker.
- Helm.
- Pipelines.
- APIs.
- Scripts.
- Configuração de serviços.

Avalie se os exemplos são:

- Compreensíveis.
- Completos.
- Copiáveis.
- Consistentes.
- Versionados.
- Compatíveis com o produto.
- Livres de informações sensíveis.
- Acompanhados de validação.

Não execute exemplos que modifiquem recursos sem autorização.

## 10.3. Troubleshooting

Verifique a existência de:

- Sintomas.
- Mensagens de erro.
- Diagnóstico.
- Causas conhecidas.
- Soluções.
- Procedimentos de validação.
- Escalação.
- Links relacionados.

## 10.4. Qualidade editorial

Analise:

- Clareza.
- Terminologia.
- Concisão.
- Estrutura de headings.
- Consistência de títulos.
- Conteúdo desatualizado.
- Duplicação.
- Informações conflitantes.
- Documentação incompleta.
- Links sem contexto.
- Uso de tabelas.
- Uso de diagramas.
- Conteúdo excessivamente denso.

Identifique documentos cuja leitura possa ser simplificada sem perda de conteúdo técnico.

---

# 11. Fase 8 — Documentação interna e externa

Identifique se existe separação entre conteúdos destinados a diferentes públicos.

Investigue:

- Um ou múltiplos portais.
- Um ou múltiplos builds.
- Repositórios.
- Instâncias Docusaurus.
- Domínios.
- Rotas.
- Conteúdos compartilhados.
- Conteúdos restritos.
- Autenticação.
- Autorização.
- Configurações de publicação.
- Search indexes.
- Políticas de indexação.
- Controle de acesso a assets.
- Pipelines.

Verifique se a separação é apenas visual ou se existe isolamento efetivo.

Não realize testes intrusivos de acesso.

Não tente contornar controles corporativos de segurança.

Registre situações que exigem validação pelo time responsável.

---

# 12. Fase 9 — Busca, SEO e descoberta

## 12.1. Busca

Identifique:

- Motor utilizado.
- Plugin.
- Configurações.
- Escopo indexado.
- Comportamento dos resultados.
- Atalhos de teclado.
- Filtros.
- Contexto de produto.
- Tratamento de idiomas.
- Atualização do índice.
- Restrições de acesso.

Verifique se os usuários conseguem pesquisar títulos, conteúdos e assuntos sem conhecer o nome exato da página.

## 12.2. SEO

Quando aplicável ao público externo, avalie:

- Metadados.
- Títulos.
- Descrições.
- Canonical.
- Sitemap.
- Robots.
- Links internos.
- URLs.
- Redirects.
- Conteúdo duplicado.
- Indexação de versões antigas.

Para documentação interna, priorize confidencialidade e controles de acesso.

---

# 13. Fase 10 — Acessibilidade

Avalie o alinhamento aos critérios relevantes da WCAG 2.2 AA.

Investigue:

- Semântica HTML.
- Hierarquia dos headings.
- Contraste.
- Navegação por teclado.
- Focus visible.
- Labels.
- Uso de ARIA.
- Skip links.
- Tamanho de alvos.
- Compatibilidade com leitores de tela.
- Responsividade.
- Zoom.
- Movimento reduzido.
- Tabelas.
- Imagens.
- Diagramas.
- Componentes interativos.

Classifique os resultados em:

- Problemas confirmados.
- Riscos encontrados no código.
- Pontos que exigem testes manuais.

Não afirme conformidade integral com base apenas em ferramentas automáticas.

---

# 14. Fase 11 — Performance

Investigue:

- Bundle JavaScript.
- Dependências pesadas.
- Imagens.
- Fontes.
- Renderização.
- Carregamento de componentes.
- Layout shifts.
- Code splitting.
- Lazy loading.
- Uso de bibliotecas de ícones.
- CSS redundante.
- Assets.
- Páginas excessivamente grandes.

Utilize LCP, INP e CLS como indicadores quando houver métricas reais disponíveis.

Diferencie:

- Problemas confirmados.
- Riscos estáticos.
- Resultados laboratoriais.
- Dados reais de usuários.
- Otimizações apenas hipotéticas.

Não invente benchmarks de performance.

---

# 15. Fase 12 — Qualidade de código

Analise:

- Organização.
- Responsabilidades.
- Tipagem TypeScript.
- Hooks.
- Componentização.
- Acoplamento.
- Reutilização.
- Tratamento de erros.
- Padrões de nomenclatura.
- Dependências.
- Código morto.
- Duplicações.
- Complexidade.
- Testabilidade.
- Manutenibilidade.

Investigue a existência de:

- ESLint.
- Prettier.
- Stylelint.
- Markdownlint.
- Vale.
- Testes unitários.
- Testes de integração.
- Testes E2E.
- Testes de acessibilidade.
- Testes visuais.
- Verificadores de links.
- Validações de build.

Registre o que existe e o que efetivamente é executado nos pipelines.

---

# 16. Fase 13 — CI/CD, publicação e operação

Investigue, exclusivamente por leitura:

- Como a documentação é compilada.
- Como é publicada.
- Ambientes disponíveis.
- Estratégia de preview.
- Branches e triggers.
- Pipelines.
- Aprovações.
- Proteções.
- Hosting.
- CDN.
- Cache.
- Invalidação.
- Rollback.
- Monitoramento.
- Observabilidade.
- Logs.
- Alertas.
- Gestão de falhas de publicação.

Produza um diagrama do fluxo de publicação baseado exclusivamente nas evidências disponíveis.

Não presuma AWS, GitHub Actions ou qualquer solução específica sem confirmação.

---

# 17. Fase 14 — Governança da documentação

Investigue:

- Responsáveis pelos conteúdos.
- CODEOWNERS.
- Revisão técnica.
- Fluxo de contribuição.
- Templates.
- Aprovação de mudanças.
- Atualização de versões.
- Política de documentos obsoletos.
- Changelog.
- Ownership por produto.
- Gestão de links.
- Gestão de assets.
- Revisão periódica.
- Integração entre mudanças de produto e documentação.

Avalie como a organização evita:

- Documentos abandonados.
- Instruções incorretas.
- Divergências entre produto e documentação.
- Dependência de conhecimento tácito.
- Publicação de informações sensíveis.
- Conteúdo duplicado.

Não atribua ausência de processo apenas porque não encontrou sua descrição no repositório.

---

# 18. Fase 15 — Segurança da aplicação e dos conteúdos

Realize uma revisão estática e não intrusiva.

Avalie:

- Segredos versionados ou referenciados inadequadamente.
- Dependências potencialmente vulneráveis.
- Exposição de configurações.
- Uso inseguro de HTML ou MDX.
- Scripts de terceiros.
- Content Security Policy, se existente.
- Tratamento de links externos.
- Controle de acesso.
- Publicação de documentação interna.
- Assets privados.
- Exposição de dados operacionais.
- Separação de ambientes.
- Permissões e credenciais de pipelines.

Não reproduza credenciais ou segredos identificados.

Use evidências sanitizadas e registre como o problema deve ser tratado pelos responsáveis.

Não execute exploração, varreduras intrusivas nem ações contra infraestrutura corporativa.

---

# 19. Fase 16 — Análise cruzada

Após as análises individuais, relacione problemas entre áreas.

Exemplos de relações que devem ser investigadas:

- Sidebar extensa ↔ arquitetura da informação.
- Componente duplicado ↔ inconsistência visual.
- Layout customizado ↔ dificuldade de upgrade.
- Documento longo ↔ dificuldade de descoberta.
- Busca inadequada ↔ dificuldades de onboarding.
- Falta de metadados ↔ baixa governança.
- Excesso de plugins ↔ complexidade de manutenção.
- Estilos hardcoded ↔ fragmentação do Design System.
- Duplicação de conteúdo ↔ risco de informações conflitantes.
- Ausência de preview ↔ risco de regressões.
- Isolamento inadequado ↔ exposição de conteúdo interno.

Identifique causas estruturais, não apenas sintomas superficiais.

Evite contabilizar o mesmo problema várias vezes sem esclarecer sua causa principal.

---

# 20. Modelo de classificação dos achados

Para cada problema relevante, utilize:

**ID:** Identificador único.

**Área:** Arquitetura, UX, UI, DX, documentação, segurança, performance ou outra.

**Título:** Descrição objetiva.

**Estado:** Confirmado, observado, inferido ou não verificado.

**Situação atual:** O que existe.

**Evidência:** Arquivos, linhas, rotas, capturas ou comportamento.

**Problema:** O que foi identificado.

**Impacto:** Consequências para usuários, engenharia ou negócio.

**Causa provável:** Quando tecnicamente fundamentada.

**Severidade:**
- Crítica
- Alta
- Média
- Baixa
- Informativa

**Abrangência:** Quais produtos, páginas ou jornadas são afetados.

**Recomendação preliminar:** Possível direção de melhoria.

**Complexidade estimada:** Baixa, média, alta ou ainda indeterminada.

**Dependências:** O que precisaria ser conhecido ou validado antes de agir.

**Critério de validação:** Como verificar se o problema foi resolvido no futuro.

Não confunda severidade, esforço de implementação e prioridade de negócio.

---

# 21. Entregáveis

Produza um relatório final organizado nas seguintes seções.

## A. Executive Summary

- Estado geral da aplicação.
- Principais características.
- Pontos fortes.
- Limitações.
- Riscos.
- Oportunidades.
- Principais conclusões.

## B. Inventário técnico

- Stack.
- Dependências.
- Plugins.
- Configurações.
- Estrutura.
- Componentes.
- Estilos.
- Rotas.
- Conteúdos.
- Testes.
- Automação.

## C. Arquitetura As-Is

- Diagrama geral.
- Organização React/Docusaurus.
- Fluxos de navegação.
- Dependências.
- Integrações.
- Fluxo de publicação.

## D. Arquitetura da informação

- Sitemap.
- Organização documental.
- Sidebars.
- Categorias.
- Produtos.
- Jornadas.
- Conteúdos órfãos.
- Redundâncias.
- Inconsistências.

## E. Auditoria UI

- Design System existente.
- Tokens.
- Componentes visuais.
- Layouts.
- Consistência.
- Responsividade.
- Problemas identificados.

## F. Auditoria UX

- Navegação.
- Descoberta.
- Jornadas.
- Busca.
- Fricções.
- Barreiras.
- Evidências.

## G. Auditoria Developer Experience

- Onboarding.
- Quickstarts.
- Exemplos.
- Troubleshooting.
- Documentação operacional.
- Eficiência das jornadas.

## H. Auditoria de Engenharia

- Arquitetura frontend.
- Qualidade de código.
- Testes.
- Dependências.
- Manutenibilidade.
- Performance.
- Segurança.
- CI/CD.

## I. Auditoria editorial

- Cobertura documental.
- Qualidade.
- Clareza.
- Padronização.
- Duplicações.
- Conteúdos obsoletos.
- Ownership.
- Governança.

## J. Matriz de achados

Consolide todos os problemas com IDs, severidade, impacto, abrangência, evidências e possíveis encaminhamentos.

## K. Mapa de oportunidades

Separe oportunidades por:

- Arquitetura da informação.
- Experiência do usuário.
- Design System.
- Componentização.
- Developer Experience.
- Conteúdo.
- Performance.
- Acessibilidade.
- Segurança.
- Operação.
- Governança.

## L. Roadmap preliminar

Classifique:

**P0:** Riscos críticos, problemas graves e impedimentos relevantes.

**P1:** Melhorias de alto impacto.

**P2:** Melhorias de experiência, manutenção e produtividade.

**P3:** Refinamentos e oportunidades futuras.

O roadmap é somente uma recomendação.

Não implemente nenhuma dessas ações.

## M. Lacunas da investigação

Registre:

- Itens não inspecionados.
- Permissões ausentes.
- Evidências insuficientes.
- Dependências de ambiente.
- Perguntas que precisam ser respondidas.
- Testes necessários.
- Riscos ainda não avaliados.

---

# 22. Índice de maturidade

Apresente uma avaliação por dimensão, com escala de 0 a 5.

Dimensões:

1. Arquitetura frontend.
2. Arquitetura da informação.
3. Navegação e descoberta.
4. UI e Design System.
5. UX.
6. Developer Experience.
7. Qualidade documental.
8. Acessibilidade.
9. Performance.
10. Segurança.
11. CI/CD.
12. Governança.
13. Manutenibilidade.
14. Escalabilidade.

Critérios:

- 0: Inexistente ou comprovadamente inadequado.
- 1: Inicial.
- 2: Parcial.
- 3: Estruturado.
- 4: Maduro.
- 5: Altamente consistente, validado e governado.

A nota deve ser justificada por evidências.

Quando não houver dados suficientes, utilize **N/A — Não avaliado**, sem inventar pontuação.

Não apresente uma média global como medida objetiva de qualidade caso a cobertura da investigação seja insuficiente.

---

# 23. Estratégia de execução da auditoria

Organize o trabalho em ciclos controlados.

### Ciclo 1 — Reconhecimento

Inventarie o repositório, identifique a stack e construa o mapa inicial.

### Ciclo 2 — Engenharia

Analise componentes, estilização, plugins, dependências, testes e pipelines.

### Ciclo 3 — Documentação

Mapeie todas as categorias, rotas, sidebars, produtos e tipos de conteúdo.

### Ciclo 4 — Experiência

Reconstrua jornadas e investigue UI, UX, DX, busca, acessibilidade e responsividade.

### Ciclo 5 — Segurança e operação

Avalie fronteiras de publicação, controles identificáveis e processos operacionais.

### Ciclo 6 — Consolidação

Cruze as evidências, classifique os achados e elabore o relatório.

Se estiver utilizando múltiplos agentes, distribua tarefas de investigação por especialidade, mas mantenha uma única fonte de verdade para o inventário e os achados.

Evite análises duplicadas e conclusões conflitantes entre agentes.

Antes de considerar uma fase concluída, valide a cobertura do escopo.

---

# 24. Controle de cobertura

Mantenha uma matriz de progresso contendo:

- Domínio de investigação.
- Itens identificados.
- Itens inspecionados.
- Itens pendentes.
- Evidências coletadas.
- Limitações.
- Status.

Utilize os estados:

- Não iniciado.
- Em investigação.
- Parcialmente avaliado.
- Concluído.
- Bloqueado.

Não declare que realizou uma auditoria completa se existirem áreas relevantes ainda não avaliadas.

Para conteúdos numerosos, empregue análise automatizada de inventário e inspeção aprofundada dos elementos críticos.

Declare quais documentos foram examinados individualmente e quais foram avaliados apenas por metadados ou amostragem.

---

# 25. Formato do resultado

Entregue a análise em português do Brasil.

Utilize:

- Markdown estruturado.
- Tabelas comparativas.
- Matrizes.
- Diagramas Mermaid.
- Referências aos arquivos e linhas.
- Árvores de diretórios.
- Inventários de componentes.
- Mapas de navegação.
- Evidências visuais, quando disponíveis.

Priorize precisão técnica, organização e rastreabilidade.

Evite descrições vagas como:

- "Melhorar a experiência".
- "Modernizar a interface".
- "O código está confuso".
- "A navegação pode ser otimizada".

Substitua por diagnósticos específicos, comprovados e contextualizados.

Não apresente recomendações como implementações já realizadas.

---

# 26. Critérios para encerrar a auditoria

Considere o levantamento satisfatório quando:

1. A stack e as configurações principais estiverem inventariadas.
2. A arquitetura técnica estiver documentada.
3. Os componentes e customizações principais estiverem mapeados.
4. O sistema visual atual estiver caracterizado.
5. As sidebars e a organização documental estiverem inventariadas.
6. As principais jornadas de usuários estiverem analisadas.
7. Os processos de build e publicação estiverem compreendidos dentro dos acessos disponíveis.
8. As áreas de segurança, acessibilidade, qualidade e performance tiverem sido avaliadas ou explicitamente classificadas como pendentes.
9. Os problemas relevantes estiverem relacionados às suas evidências.
10. As limitações e pendências da investigação estiverem registradas.
11. O relatório permitir que outro engenheiro retome a análise sem repetir todo o processo.
12. Nenhum arquivo, configuração ou recurso do projeto tiver sido alterado.

---

# 27. Instrução final

**Não quero uma proposta genérica de como construir uma boa documentação. Quero compreender profundamente o Docusaurus corporativo que já existe.**

Investigue o código real, a estrutura real, os componentes reais, as páginas reais, os fluxos reais e as decisões já implementadas.

Priorize a descoberta de relações que não são óbvias à primeira vista.

Questione a arquitetura quando houver evidências de problemas, mas reconheça soluções que já funcionam bem.

Não presuma que toda customização é dívida técnica.

Não presuma que todo conteúdo longo é ruim.

Não presuma que a organização atual precisa ser substituída.

Separe rigorosamente:

**ESTADO ATUAL → EVIDÊNCIAS → DIAGNÓSTICO → IMPACTO → OPORTUNIDADES FUTURAS.**

O resultado deverá ser uma documentação arquitetural e uma auditoria de maturidade suficientemente completas para servir como fundamento a uma futura iniciativa de evolução do portal corporativo.

**Comece pelo reconhecimento e inventário. Não implemente alterações.**
