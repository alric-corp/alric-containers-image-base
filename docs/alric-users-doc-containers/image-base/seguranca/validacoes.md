---
title: Validações e garantias
sidebar_label: Validações e garantias
description: O que significa hardened, o que a plataforma valida antes de publicar cada imagem e o que assinatura, provenance e SBOM provam e não provam.
---

## Hardened não é o mesmo que Distroless {#hardened-distroless}

**Distroless** descreve o perfil mínimo do runtime: sem shell, gerenciador de pacotes ou ferramentas gerais desnecessárias à execução. **Hardened** acrescenta controles sobre conteúdo, manutenção, vulnerabilidades, testes e verificabilidade. Uma imagem Distroless não é automaticamente hardened, e uma imagem pequena, sozinha, não é garantia de segurança.

## O que é validado antes da publicação {#o-que-e-validado}

| Controle | O que verifica |
| --- | --- |
| **Composição declarativa** | A imagem é montada a partir de pacotes assinados do Wolfi, sem Dockerfile de base e sem shell nem gerenciador de pacotes no runtime. |
| **Scan de vulnerabilidades** | O Trivy analisa cada arquitetura. Uma vulnerabilidade com correção disponível bloqueia a publicação. |
| **Contratos de execução** | Em amd64 e arm64: usuário não-root (UID `10000`), raiz somente leitura com `/tmp` gravável, versão do runtime, fuso horário e HTTPS com o trust store da imagem, rejeitando servidores com CA desconhecida. |
| **Aplicações de referência** | Aplicações da família são construídas com a base e executadas nas duas arquiteturas antes da promoção para `stable`. |
| **Evidências publicadas** | Cada índice publicado recebe assinatura, SBOM (SPDX) e provenance (SLSA v1). |

## Assinatura, provenance e SBOM {#evidencias}

| Evidência | O que prova | O que não prova |
| --- | --- | --- |
| **Assinatura** | Que o índice foi publicado pela identidade do workflow de publicação da plataforma. | Que a imagem está livre de vulnerabilidades ou que houve aprovação humana. |
| **Provenance** | De qual repositório, workflow e commit a imagem veio. | Que o código é seguro ou que todos os controles foram executados. |
| **SBOM** | Quais componentes estão na **base** publicada. | O que sua aplicação acrescenta: suas dependências não aparecem no SBOM da base. |

Essas evidências se referem ao **digest do índice da base**, não à imagem final da sua aplicação. Scan, SBOM e assinatura da imagem final são feitos pela esteira da squad.

Se a política do seu time exige consumo auditado, verifique a assinatura e a provenance do digest antes de usá-lo e fixe esse mesmo digest no build. O [exemplo de consumo auditado](https://github.com/alric-corp/alric-containers-image-base/tree/develop/examples/audited-consumer) mostra o fluxo completo em uma esteira.

**CVE** é o identificador de uma vulnerabilidade conhecida. **Trivy** é o scanner: identifica vulnerabilidades segundo a política configurada, mas não aplica correções. Outros termos estão no [glossário](../referencia/glossario.md).

## Limites {#limites}

- Não há promessa de zero CVE, compatibilidade universal ou prazo de correção que não esteja formalizado.
- O scan trata separadamente vulnerabilidades que ainda não têm correção disponível. Scan aprovado não significa ausência de todas as vulnerabilidades conhecidas.
- A base não substitui código seguro, o scan da imagem final nem a configuração segura do ambiente: raiz somente leitura, capabilities e rede são definidas no workload.
- Ganhos de tamanho, desempenho e quantidade de vulnerabilidades devem ser medidos na aplicação migrada.
