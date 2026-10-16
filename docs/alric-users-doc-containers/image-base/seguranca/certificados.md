---
title: Certificados e HTTPS
sidebar_label: Certificados e HTTPS
description: O CA bundle corporativo da base, como cada linguagem lê a confiança TLS e como investigar erros de certificado sem desabilitar validações.
---

Uma **CA** (autoridade certificadora) é uma raiz ou intermediária de confiança usada na validação de certificados. **TLS** protege conexões como HTTPS. O **trust store** é o conjunto de autoridades que o cliente aceita.

## O que a base configura {#trust-store}

A base já inclui o **CA bundle do Itaú**, com as autoridades necessárias às aplicações corporativas: você não precisa configurar certificados manualmente. Isso não significa confiar em qualquer servidor interno: a cadeia apresentada precisa ser válida, corresponder ao hostname e estar coberta pelas autoridades aprovadas.

O bundle fica em `/etc/ssl/certs/ca-certificates.crt`, e os contratos da plataforma validam HTTPS em Java, Go, .NET, Node.js e Python usando a confiança instalada na imagem, sem nenhuma configuração no Dockerfile.

| Linguagem | Onde a confiança é lida |
| --- | --- |
| Go e .NET | Bundle do sistema, indicado por `SSL_CERT_FILE`. |
| Python | A biblioteca padrão (`ssl`, `urllib`) usa o bundle do sistema. Bibliotecas como `requests` usam o pacote `certifi` por padrão: para que usem o bundle da imagem, defina `REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt`. |
| Node.js | Raízes próprias do Node.js somadas ao bundle da imagem, indicado por `NODE_EXTRA_CA_CERTS`. |
| Java | Truststore da JVM em `/etc/ssl/certs/java/cacerts`. |

Não aplique uma única variável de ambiente a todas as linguagens esperando comportamento idêntico. Uma aplicação que configura um trust store próprio, por exemplo com `-Djavax.net.ssl.trustStore`, deixa de usar o da base.

A plataforma integra as CAs aprovadas, em conjunto com a PKI, mas não é a autoridade emissora delas.

## Investigar erros TLS {#diagnostico}

Em erros como `x509: unknown authority` ou equivalentes, confira a cadeia apresentada pelo servidor, o hostname, a validade do certificado, o relógio e qual trust store o seu cliente usa. As mensagens de cada linguagem estão em [Erro de certificado TLS](../troubleshooting/index.md#tls).

**Não use** `curl -k`, `verify=False`, `NODE_TLS_REJECT_UNAUTHORIZED=0` ou callbacks que aceitam qualquer certificado como correção. Para CAs ausentes, acione a plataforma e a PKI.

## mTLS e assinatura de imagem são outros controles {#mtls}

**Certificado cliente e chave privada para mTLS não são CA bundle.** Eles pertencem à configuração segura da aplicação e não devem ser incorporados à base compartilhada. Da mesma forma, a assinatura da imagem e a confiança HTTPS são controles distintos.
