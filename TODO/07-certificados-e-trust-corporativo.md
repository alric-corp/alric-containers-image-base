# M07 — Fechar certificados e confiança corporativa

**Dependências:** M03; acesso S3/PKI autorizado quando necessário.  
**Tipo de trabalho:** Revisão de trust, aquisição autorizada e alteração local; nenhum build/publicação automático.

## Objetivo desta sessão

Substituir fixtures quando exigido e provar a confiança necessária sem remover raízes válidas nem desligar TLS.

## Consultar somente

- `TODO/adjust-certificates.md`, alvo de certificados no `Makefile` e `scripts/certificates/`.
- `melange/certificates/` e `melange/image-base-ca-certificates.yaml`.
- Contratos TLS existentes e instrução corporativa de PKI fornecida pelo responsável.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Declare o aceite pretendido: smoke técnico com fixture ou imagem corporativa consumível. Este marco só é concluído para trust real quando há evidência com CAs aprovadas; fixture não prova distribuição PKI.
2. Mapeie origem dos certificados, bucket/chave quando aplicável, versão/hash, proprietário e destinos TLS que precisam ser confiáveis. Não inventar endpoints de teste ou buckets.
3. Inspecione `certificados.sh` e o alvo `make certificates` antes de executá-los. Baixar script de S3 e executá-lo exige origem/integridade e autorização claras; não confiar apenas no nome do arquivo.
4. Diferencie os trust stores do runner/daemon/ferramentas daqueles da imagem final. Não assumir um único mecanismo para Java, .NET, Go, Node e Python.
5. Revise a duplicação do bundle Mozilla, sem interpretar o TODO como ordem de remover todas as raízes públicas. Preserve o conjunto de confiança exigido pela política corporativa.
6. Faça a aquisição/geração autorizada, revise o diff e execute os testes focados de certificados. Certificados públicos só podem ser versionados conforme a política local; chaves privadas, tokens e credenciais nunca entram no Git ou no relatório.
7. Exija TLS positivo e negativo correspondentes ao mecanismo exercitado. Não usar `-k`, `verify=False`, callbacks que aceitam tudo ou supressão de erro de certificado.

## Critérios de aceite

- Origem e integridade dos insumos PKI aprovadas.
- Fixture e material real claramente separados.
- Trust do ambiente de build e do runtime tratados onde necessário.
- Sem retirada indiscriminada de raízes ou enfraquecimento da validação TLS.

## Quando parar

PKI/origem desconhecida, chave privada inesperada, execução remota de script não aprovada ou teste negativo aceito indevidamente. Smoke pode ser registrado como parcial, nunca como trust corporativo concluído.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
TRUST_ACCEPTANCE_SCOPE =
PKI_SOURCE_VERIFIED =
RUNNER_TRUST_RESULT =
RUNTIME_TRUST_RESULT =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/07-certificados-e-trust-corporativo.md.
Execute somente M07. Revise e execute apenas o trabalho de certificados autorizado.
Separe runner de imagem, fixture de PKI real e remoção de redundância de remoção de
raízes públicas. Preserve TLS estrito e pare se a origem dos insumos não estiver
comprovada.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: seções 14, 16, 17 e Gate 3. Ajustes da revisão: separar trust do runner e da imagem, fixture e PKI real, duplicação e remoção de raízes. Este marco é um roteiro; não comprova que as ações já foram realizadas.
