---
title: Perguntas frequentes
sidebar_label: Perguntas frequentes
description: Respostas rápidas sobre consumo, runtime, diagnóstico, segurança e atualizações de Image Base.
---

## Consumo {#consumo}

### Preciso conhecer como as imagens base são construídas? {#preciso-conhecer-a-construcao}

Não. Para consumir, use a imagem correspondente no Dockerfile e siga o [fluxo de uso](../como-utilizar/dockerfile.mdx).

### Preciso da imagem `-dev` se meu pipeline já compila? {#dev-com-pipeline}

Não necessariamente. Você pode copiar o artefato pronto para o runtime, desde que ele seja compatível com a versão, o sistema, as bibliotecas e a arquitetura de destino.

### Uso `:stable` nos dois estágios? {#stable-nos-dois-estagios}

Sim. Se você compila com a `-dev` no estágio de build, use `stable` nele e no runtime, sempre da mesma família e versão.

### Posso usar a `-dev` como imagem final? {#dev-como-final}

Não. A `-dev` é usada somente no estágio de build, e a imagem final da aplicação usa sempre a variante runtime. A `-dev` traz toolchain e shell, que não devem chegar à produção. Ela também não serve para contornar a ausência de ferramentas no runtime: `-dev` descreve a função da imagem, não um ambiente.

### A imagem vem com todas as bibliotecas da minha aplicação? {#bibliotecas-da-aplicacao}

Não. Spring, dependências npm, Python e NuGet e bibliotecas internas pertencem à aplicação. A base não é um ambiente de desenvolvimento completo.

## Runtime e diagnóstico {#runtime}

### Posso fazer `RUN apk add`, `apt-get` ou instalar Bash no runtime? {#instalar-pacotes}

Não conte com esses comandos na imagem final: o runtime não tem shell nem gerenciador de pacotes. Uma dependência adicional de sistema precisa ser avaliada no contrato da base. Não use a `-dev` como runtime para contornar a ausência de ferramentas.

### Por que não consigo abrir um shell no container? {#shell}

Porque o runtime não tem shell, por design. Use logs e eventos e, quando autorizado, um [container efêmero no EKS](../troubleshooting/eks.md#container-efemero) ou o [ECS Exec](../troubleshooting/ecs.md#ecs-exec) com binários existentes na imagem.

## Segurança e atualizações {#seguranca}

### O scan aprovado da base dispensa o scan da minha imagem final? {#scan-da-imagem-final}

Não. Seu código, suas dependências e seus arquivos acrescentam conteúdo que não existia na base. A assinatura da base também não comprova a segurança desse conteúdo.

### Atualizar a tag da base e reiniciar o Pod corrige tudo? {#reiniciar-corrige}

Não. É necessário reconstruir a aplicação com a base corrigida, testar e fazer deploy da nova imagem final. Veja [Atualizações e CVEs](../seguranca/atualizacoes.md).

### Preciso configurar os certificados corporativos? {#cas-corporativas}

Não. A base já inclui o CA bundle com as autoridades necessárias às aplicações corporativas. Veja [Certificados e HTTPS](../seguranca/certificados.md#trust-store).
