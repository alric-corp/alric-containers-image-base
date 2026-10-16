---
title: Certificados e HTTPS
sidebar_label: Certificados e HTTPS
description: Como a base configura a confiança TLS em cada linguagem, a situação das CAs corporativas e como investigar erros de certificado sem desabilitar validações.
---

Uma **CA** (autoridade certificadora) é uma raiz ou intermediária de confiança usada na validação de certificados. **TLS** protege conexões como HTTPS. O **trust store** é o conjunto de autoridades que o cliente aceita.

## O que a base configura {#trust-store}

A base traz um bundle de CAs em `/etc/ssl/certs/ca-certificates.crt`, e os contratos da plataforma validam HTTPS em Java, Go, .NET, Node.js e Python usando a confiança instalada na imagem, sem nenhuma configuração no Dockerfile. Um servidor com CA desconhecida deve ser rejeitado.

| Linguagem | Onde a confiança é lida |
| --- | --- |
| Go e .NET | Bundle do sistema, indicado por `SSL_CERT_FILE`. |
| Python | A biblioteca padrão (`ssl`, `urllib`) usa o bundle do sistema. Bibliotecas como `requests` usam o pacote `certifi` por padrão: para que usem o bundle da imagem, defina `REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt`. |
| Node.js | Raízes próprias do Node.js somadas ao bundle da imagem, indicado por `NODE_EXTRA_CA_CERTS`. |
| Java | Truststore da JVM em `/etc/ssl/certs/java/cacerts`. |

Não aplique uma única variável de ambiente a todas as linguagens esperando comportamento idêntico. Uma aplicação que configura um trust store próprio, por exemplo com `-Djavax.net.ssl.trustStore`, deixa de usar o da base.

## CAs corporativas {#cas-corporativas}

:::warning Situação atual
As imagens publicadas confiam nas autoridades **públicas** do bundle padrão. A base já tem o mecanismo para incluir CAs corporativas aprovadas, mas a fonte e a lista corporativas ainda dependem de aprovação de PKI e Segurança. Até lá, uma aplicação que chama serviços com certificado emitido por CA corporativa pode falhar na validação TLS: valide antes de migrar e, se for o seu caso, [acione o suporte](../suporte.md).
:::

A plataforma integra CAs aprovadas, mas não é a autoridade emissora delas. Incluir uma CA não faz o cliente confiar em qualquer servidor interno: a cadeia apresentada precisa ser válida, corresponder ao hostname e estar coberta pelas autoridades aprovadas.

## Investigar erros TLS {#diagnostico}

Em erros como `x509: unknown authority` ou equivalentes, confira a cadeia apresentada pelo servidor, o hostname, a validade do certificado, o relógio e qual trust store o seu cliente usa. As mensagens de cada linguagem estão em [Erro de certificado TLS](../troubleshooting/index.md#tls).

**Não use** `curl -k`, `verify=False`, `NODE_TLS_REJECT_UNAUTHORIZED=0` ou callbacks que aceitam qualquer certificado como correção. Para CAs ausentes, acione a plataforma e a PKI.

## mTLS e assinatura de imagem são outros controles {#mtls}

**Certificado cliente e chave privada para mTLS não são CA bundle.** Eles pertencem à configuração segura da aplicação e não devem ser incorporados à base compartilhada. Da mesma forma, a assinatura da imagem e a confiança HTTPS são controles distintos.
