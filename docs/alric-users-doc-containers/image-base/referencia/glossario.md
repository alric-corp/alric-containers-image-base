---
title: Glossário
sidebar_label: Glossário
description: Termos usados na documentação de Image Base, sem exigir conhecimento da implementação interna da plataforma.
---

| Termo | Significado |
| --- | --- |
| **amd64 / arm64** | Arquiteturas x86-64 e ARM de 64 bits. As imagens do catálogo são publicadas para `linux/amd64` e `linux/arm64`. |
| **Assinatura** | Evidência verificável associada à identidade que assinou o artefato. |
| **Build tag** | Tag imutável que identifica uma publicação da base, no formato `<ddmmaa>-<hhmm>-r<execução>-a<tentativa>`. Pode expirar com a política de retenção. |
| **CA** | Autoridade certificadora: raiz ou intermediária de confiança usada na validação de certificados TLS. |
| **CVE** | Identificador de uma vulnerabilidade conhecida. |
| **`-dev`** | Variante destinada ao estágio de construção, com ferramentas como SDK, JDK, compilador ou npm, conforme a família. Nunca é a imagem final. |
| **Digest** | Identificador do conteúdo de uma imagem (`sha256:...`). O digest do índice identifica exatamente o artefato multiarch. |
| **Distroless** | Imagem orientada ao runtime, sem ferramentas gerais desnecessárias à execução, como shell e gerenciador de pacotes. |
| **Hardened** | Imagem mantida com foco em redução de superfície de ataque, conteúdo controlado, tratamento de vulnerabilidades, manutenção e evidências verificáveis de supply chain. |
| **Multi-stage** | Dockerfile com mais de um estágio: um para construir a aplicação e outro, mínimo, para executá-la. |
| **Multiarch** | Disponibilização da mesma referência de imagem para diferentes arquiteturas. |
| **OCI Image Index** | Índice que reúne as versões de uma imagem para cada plataforma; o cliente escolhe a versão da sua arquitetura. |
| **Provenance** | Evidência verificável sobre a origem e o processo usado para produzir o artefato. |
| **Referência principal** | Par de imagens com publicação e promoção contínuas: hoje, Go 1.26 (`go1-26` e `go1-26-dev`). |
| **Runtime** | Imagem destinada à execução da aplicação, sem o toolchain de desenvolvimento. |
| **SBOM** | Inventário dos componentes presentes no artefato publicado. O SBOM da base não lista o que a aplicação acrescenta. |
| **Scratch** | Ponto de partida vazio para uma imagem OCI: tudo o que a aplicação precisa deve ser fornecido explicitamente. |
| **Slim** | Variante reduzida de uma imagem convencional. Indica menos conteúdo, mas não define sozinha controles de segurança, manutenção ou supply chain. |
| **`stable`** | Tag móvel que aponta para a versão atualmente disponibilizada pelo Containers Products para aquela família e versão. |
| **Sem suporte upstream** | Série que o fornecedor da linguagem deixou de corrigir. Continua no catálogo até decisão do owner, mas não deve ser usada em novas adoções. |
| **TLS** | Protocolo que protege conexões como HTTPS. |
| **Trust store** | Conjunto de autoridades certificadoras que um cliente TLS aceita. |
| **UID/GID 10000** | Identificador numérico do usuário e do grupo não-root com que as imagens rodam (`spring` no Java, `appuser` nas demais). |
