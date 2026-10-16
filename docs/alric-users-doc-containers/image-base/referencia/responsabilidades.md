---
title: Responsabilidades
sidebar_label: Responsabilidades (RACI)
description: O que o Containers Products mantém, o que continua com a squad e a matriz RACI completa do consumo de Image Base.
---

> **A plataforma cuida da base; a squad cuida da aplicação.** Uma correção disponibilizada na base só chega ao serviço quando a aplicação incorpora essa base, é reconstruída, testada e implantada.

## Em resumo {#resumo}

**O Containers Products mantém:**

- o catálogo e a composição das bases;
- a atualização de runtimes e pacotes, incorporando as correções disponíveis;
- a integração das CAs aprovadas, em conjunto com a PKI;
- o scan e o tratamento de findings dos componentes da base;
- os testes, a publicação, a assinatura, o SBOM e a provenance da base;
- a tag `stable` e a comunicação de mudanças relevantes.

**Sua squad mantém:**

- a escolha da base compatível com a aplicação;
- o código e as dependências da aplicação;
- o scan e o tratamento de vulnerabilidades da imagem final;
- o rebuild com a base atualizada e os testes de compatibilidade;
- o deploy, o rollback, os secrets e as permissões do workload;
- a operação da aplicação e o reporte de falhas reproduzíveis relacionadas à base.

## Matriz RACI {#raci}

**R:** executa a atividade. **A:** responde pelo resultado. **C:** é consultado. **I:** é informado. **R/A:** reúne execução e responsabilidade pelo resultado.

A matriz resume as responsabilidades no consumo das imagens base. Não substitui as atribuições formais de Segurança, PKI, Cloud ou dos responsáveis pelo ambiente de execução.

| Atividade | Containers Products | Pipelines Core (Artifactory) | Squad da aplicação |
| --- | :---: | :---: | :---: |
| Manter o catálogo e a composição das bases | **R/A** | — | I |
| Atualizar runtimes e pacotes da base, incorporando correções disponíveis | **R/A** | — | I |
| Integrar CAs aprovadas ao contrato técnico da base, em conjunto com PKI | **R/A** | — | I |
| Executar o scan e tratar findings dos componentes da base | **R/A** | — | C |
| Testar e publicar novas versões da base | **R/A** | — | I |
| Produzir assinatura, SBOM e provenance da base | **R/A** | — | I |
| Disponibilizar a tag `stable` e comunicar mudanças relevantes da base | **R/A** | — | I |
| Manter a infraestrutura do Artifactory e o armazenamento das imagens compiladas pós-build | C | **R/A** | I |
| Escolher a base compatível com a aplicação | C | — | **R/A** |
| Manter código e dependências da aplicação | C | — | **R/A** |
| Escanear e tratar vulnerabilidades da imagem final da aplicação | C | — | **R/A** |
| Incorporar a base atualizada e reconstruir a aplicação | I | — | **R/A** |
| Testar compatibilidade, funcionalidade e desempenho após a atualização | C | — | **R/A** |
| Fazer deploy e rollback da aplicação | I | — | **R/A** |
| Configurar secrets e permissões do workload | C | — | **R/A** |
| Operar a aplicação e comunicar falhas reproduzíveis relacionadas à base | C | — | **R/A** |

A plataforma integra certificados aprovados; não se torna a autoridade emissora das CAs. Exceções de segurança e prazos de correção seguem a governança corporativa aplicável.
