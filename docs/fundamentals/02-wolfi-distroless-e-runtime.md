# Marco 02 — Wolfi, Distroless, Runtime e superfície de ataque

> **Origem:** V6, seções **38–54**.
>
> O conteúdo abaixo foi preservado da V6; a divisão em marcos não altera o conteúdo técnico original.

---
# 38. Wolfi: a peça entre a distribuição e a imagem

O segundo vídeo adiciona uma peça importante ao modelo:

```text
Melange
   │
   ▼
Pacotes APK
   │
   ▼
Wolfi
   │
   ▼
apko
   │
   ▼
OCI Image
```

O projeto é chamado oficialmente de **Wolfi**. Em algumas transcrições automáticas ele pode aparecer como “Wolfie”.

Wolfi é descrito como uma **undistro**: uma distribuição pensada especificamente para ambientes de containers, sem a obrigação de funcionar como um sistema operacional tradicional instalado diretamente em uma máquina.

A ideia é fornecer:

```text
package manager
packages
metadata
SBOM
signatures
provenance
```

sem necessariamente carregar tudo que normalmente esperamos de uma distribuição Linux completa.

---
# 39. Por que uma "undistro"?

Um container Linux utiliza o kernel do host.

Conceitualmente:

```text
Host
├── Linux Kernel
│
└── Container Runtime
     │
     ├── Container A
     ├── Container B
     └── Container C
```

Os containers não precisam carregar outro kernel dentro da imagem.

Portanto, para executar uma aplicação, geralmente precisamos apenas de:

```text
application
runtime
libraries
certificates
timezone data
configuration
```

e não de:

```text
kernel
init system completo
package manager
shell
compiler
debug utilities
serviços de sistema
```

Isso explica a ideia do Wolfi como **undistro**.

Ele é orientado ao que será usado dentro da imagem OCI, e não a funcionar como uma distribuição Linux tradicional para desktop ou servidor.

> **Insight:** uma imagem de container não precisa representar um sistema operacional completo. Ela precisa representar o ambiente mínimo e verificável necessário para executar o workload.

---
# 40. Wolfi não é apenas "Alpine menor"

Wolfi utiliza o formato de pacotes APK, o mesmo formato associado ao ecossistema Alpine.

Porém, o conceito importante é:

```text
APK
=
formato / sistema de pacotes
```

e não:

```text
APK
=
Alpine obrigatoriamente
```

Wolfi possui seu próprio conjunto de pacotes e decisões de build.

Isso é importante porque o objetivo não é simplesmente reutilizar uma distribuição pequena.

O objetivo é controlar melhor:

```text
source
build
package
metadata
SBOM
vulnerability lifecycle
```

### Nota atual

Wolfi e Alpine são ecossistemas diferentes. O fato de ambos utilizarem APK não significa que seus repositórios devam ser misturados.

---
# 41. Rolling release e lifecycle de dependências

O vídeo apresenta Wolfi como um modelo de **rolling release**.

Em vez de pensar em:

```text
Distribution 1.0
Distribution 2.0
Distribution 3.0
```

a ideia é manter continuamente versões suportadas dos componentes.

Conceitualmente:

```text
Upstream release
      │
      ▼
Package build
      │
      ▼
Wolfi repository
      │
      ▼
Container rebuild
```

Quando determinado componente deixa de ser suportado upstream, ele deixa de fazer sentido como versão principal mantida dentro desse modelo.

Esse desenho é especialmente interessante para containers porque imagens ficam obsoletas rapidamente.

O objetivo passa a ser:

```text
não manter uma base antiga por anos
```

mas sim:

```text
rebuild frequente
+
dependências suportadas
+
patches atuais
```

---
# 42. Rebuild frequente também é um controle de segurança

Uma imagem mínima pode nascer segura e se tornar vulnerável com o tempo.

Por exemplo:

```text
Dia 1
Image
└── OpenSSL X
      └── sem CVE conhecida

Dia 30
Image
└── OpenSSL X
      └── nova CVE publicada
```

Portanto:

```text
build once
     ≠
secure forever
```

Uma estratégia mais madura é:

```text
Upstream updates
      │
      ▼
Package rebuild
      │
      ▼
Image rebuild
      │
      ▼
Scan
      │
      ▼
Signature
      │
      ▼
Publish
```

O vídeo apresenta rebuilds frequentes das imagens como parte dessa estratégia.

O ponto importante não é simplesmente “rebuildar todos os dias”, mas entender que **o lifecycle da imagem faz parte da segurança**.

---
# 43. APK, resolução de dependências e uma nuance importante

Os vídeos destacam a resolução de dependências do `apk` como uma característica interessante para pipelines automatizados.

Conceitualmente:

```text
Requested packages
       │
       ▼
Dependency resolver
       │
       ├── solução válida
       │       │
       │       ▼
       │    instalação
       │
       └── solução inválida
               │
               ▼
             falha
```

Isso ajuda a tornar a composição mais previsível.

Para CI/CD queremos:

```text
determinismo
+
falha rápida
+
ambiente previsível
```

## Importante: APK pode executar scripts

Uma afirmação do terceiro vídeo precisa ser tratada com cuidado: o formato/ecossistema APK **pode possuir scripts de instalação e remoção**, incluindo:

```text
pre-install
post-install
pre-upgrade
post-upgrade
pre-deinstall
post-deinstall
```

Portanto, não devemos resumir a vantagem como:

```text
"APK nunca executa scripts"
```

O ponto mais sólido do modelo é outro:

> **apko não possui uma instrução equivalente a `RUN` para executar comandos arbitrários durante a composição da imagem.**

Assim, a configuração do apko descreve o estado desejado principalmente em termos de pacotes e metadata, reduzindo bastante a quantidade de lógica imperativa dentro do processo de composição.

---
# 44. SBOM por pacote e o conceito de "dark matter"

Um dos melhores complementos trazidos pelo segundo vídeo é o conceito de registrar os arquivos que entram no pacote.

Ele chama de **dark matter** os componentes que podem acabar presentes em um artefato sem ficarem óbvios para quem olha apenas para as dependências declaradas.

Exemplo:

```text
Python package
     │
     ├── dependency A
     │
     ├── dependency B
     │
     ├── generated files
     │
     ├── runtime files
     │
     └── transitive content
```

Se registrarmos apenas:

```text
dependency A
dependency B
```

podemos perder parte do que realmente foi colocado no artefato.

A abordagem mostrada procura manter um tipo de:

```text
receipt
```

do conteúdo produzido.

Podemos pensar assim:

```text
Build
  │
  ├── input
  ├── dependency
  ├── generated file
  ├── installed file
  └── package
       │
       ▼
      SBOM
```

Esse conceito melhora a resposta para:

> "Como esse arquivo chegou dentro da imagem?"

---
# 45. Superfície de ataque não deve ser medida somente em MB

Uma comparação especialmente interessante do vídeo é a quantidade de pacotes.

No exemplo mostrado:

```text
Imagem upstream
≈ 435 packages

Imagem minimalista apresentada
≈ 45 packages
```

Os números pertencem à demonstração específica do vídeo e não devem ser tratados como benchmark universal.

O princípio é o que importa:

```text
mais componentes
      │
      ├── mais código
      ├── mais dependências
      ├── mais possíveis CVEs
      ├── mais atualização
      └── maior superfície de ataque
```

Portanto, quando avaliamos uma imagem, vale olhar para:

```text
image size
package count
dependency count
known CVEs
shell/tools presentes
users
capabilities
SBOM completeness
```

e não somente:

```text
image size
```

---
# 46. CVE count também não deve ser a única métrica

O vídeo demonstra um scanner encontrando centenas de vulnerabilidades em uma imagem upstream e nenhuma vulnerabilidade conhecida na imagem Wolfi usada naquele momento.

Isso deve ser interpretado como uma **fotografia daquele build**, e não como garantia permanente.

Uma imagem com:

```text
0 known CVEs
```

não significa:

```text
0 vulnerabilities
```

Ela significa:

```text
0 vulnerabilidades conhecidas
dentro da cobertura atual
do scanner + SBOM + base de dados
```

Por isso devemos combinar:

```text
CVE count
     +
package count
     +
SBOM
     +
provenance
     +
patch cadence
     +
runtime controls
```

---
# 47. Rootless por padrão

O segundo vídeo também reforça um princípio que já aparecia nas boas práticas:

```text
non-root não deveria ser exceção
```

A abordagem apresentada utiliza imagens configuradas para executar como usuário não-root por padrão.

Isso altera a mentalidade de:

```dockerfile
FROM image

# aplicação roda como root até alguém lembrar de mudar
```

para:

```text
rootless by default
```

Quando uma aplicação realmente precisa de privilégio, isso passa a ser uma exceção explícita.

---
# 48. Development image vs Runtime image

Outro padrão útil mostrado no vídeo é manter variantes diferentes.

Exemplo conceitual:

```text
python:dev
│
├── shell
├── package manager
├── build tooling
└── debugging tools


python:runtime
│
├── interpreter
├── application
└── runtime dependencies
```

Isso resolve uma tensão comum:

> "Se eu remover shell e ferramentas, como vou desenvolver ou fazer troubleshooting?"

A resposta é:

```text
não use a mesma imagem para todas as fases
```

Podemos ter:

```text
Development Image
      │
      ▼
Build
      │
      ▼
Runtime Image
```

e, em Kubernetes:

```text
Runtime Image
      +
Ephemeral Debug Container
```

---
# 49. Ferramentas específicas por linguagem criam fragmentação

O vídeo também compara alternativas ao Dockerfile.

Exemplos mencionados:

```text
Go
└── ko

Java
└── Jib

Cross-language
└── Bazel
```

Essas ferramentas podem resolver muito bem seus respectivos problemas.

Porém, em uma organização poliglota podemos acabar com:

```text
Go pipeline
Java pipeline
Python pipeline
Node pipeline
Rust pipeline
```

cada um seguindo um modelo diferente de construção de imagens.

Do ponto de vista de platform engineering, isso cria desafios para:

```text
governança
políticas
security gates
SBOM
signing
provenance
suporte
developer experience
```

Um insight interessante do modelo Wolfi + Melange + apko é tentar criar uma camada mais uniforme para a composição final dos artefatos.

---
# 50. Separação de responsabilidades

O segundo vídeo deixa ainda mais clara a filosofia Unix:

> cada ferramenta deve fazer uma coisa bem.

Podemos dividir assim:

```text
Melange
└── construir pacote


Wolfi
└── fornecer ecossistema de pacotes


apko
└── compor imagem OCI


Scanner
└── identificar vulnerabilidades


Cosign / Sigstore
└── verificar identidade e assinatura


Registry
└── armazenar/distribuir


Admission Controller
└── decidir se pode executar
```

Isso evita colocar todas essas responsabilidades dentro de:

```text
Dockerfile
```

---
# 51. Arquitetura completa com Wolfi

Com os dois vídeos combinados, podemos montar um fluxo mais completo:

```text
                   SOURCE CODE
                       │
                       ▼
                 ┌────────────┐
                 │  Melange   │
                 └─────┬──────┘
                       │
                       ▼
                  Signed APK
                       │
                       ▼
              ┌─────────────────┐
              │ Wolfi packages  │
              └────────┬────────┘
                       │
                       ▼
                  ┌────────┐
                  │  apko  │
                  └────┬───┘
                       │
                       ▼
                   OCI Image
                       │
          ┌────────────┼─────────────┐
          │            │             │
          ▼            ▼             ▼
        SBOM          Scan       Provenance
          │            │             │
          └────────────┼─────────────┘
                       │
                       ▼
                    Sign
                       │
                       ▼
                   Registry
                       │
                       ▼
               Admission Policy
                       │
                       ▼
                   Runtime
```

---
# 52. Métricas melhores para avaliar imagens

Depois dos dois vídeos, uma avaliação de imagem poderia utilizar algo semelhante a:

| Métrica | Pergunta |
|---|---|
| Tamanho | Quanto precisa ser transferido/armazenado? |
| Número de pacotes | Quantos componentes estamos carregando? |
| Número de dependências | Qual é a complexidade da cadeia? |
| CVEs conhecidas | Quais vulnerabilidades já são conhecidas? |
| Idade do build | Há quanto tempo essa imagem não é reconstruída? |
| SBOM | Sabemos exatamente o que está dentro? |
| Provenance | Sabemos de onde veio? |
| Assinatura | Conseguimos verificar quem publicou? |
| Usuário | Executa como root ou non-root? |
| Shell | Existe ferramenta interativa desnecessária? |
| Capabilities | Quais privilégios Linux estão disponíveis? |
| Reprodutibilidade | Conseguimos reconstruir o mesmo artefato? |

Essa tabela representa melhor a postura de segurança do que simplesmente:

```text
Image Size = 50 MB
```

---
# 53. Checklist prático

Para uma imagem de aplicação:

```text
[ ] Utiliza somente dependências necessárias
[ ] Possui SBOM
[ ] Dependências possuem versões identificáveis
[ ] Imagem é reconstruída regularmente
[ ] Vulnerabilidades são escaneadas
[ ] Artefatos possuem provenance
[ ] Imagem é assinada
[ ] Executa como non-root
[ ] Não possui shell quando não necessário
[ ] Não possui compiler no runtime
[ ] Não possui package manager quando não necessário
[ ] Não contém secrets
[ ] Possui versão/tag imutável ou digest pinado
[ ] Possui política de admission antes do runtime
```

Para imagens de troubleshooting:

```text
[ ] Ferramentas existem por necessidade explícita
[ ] Acesso é controlado
[ ] RBAC é mínimo
[ ] IAM é mínimo
[ ] Capabilities são limitadas
[ ] Uso é auditável
[ ] Imagem é assinada
[ ] Imagem é escaneada
```

---
# 54. Novo modelo mental

Com os dois vídeos juntos, a evolução pode ser vista assim:

```text
"Como escrevo um Dockerfile?"
            │
            ▼
"Como faço uma imagem menor?"
            │
            ▼
"Como removo ferramentas desnecessárias?"
            │
            ▼
"Como sei o que existe na imagem?"
            │
            ▼
"Como sei de onde cada componente veio?"
            │
            ▼
"Como provo quem construiu?"
            │
            ▼
"Como mantenho tudo atualizado?"
            │
            ▼
"Como impeço uma imagem não confiável de executar?"
            │
            ▼
Secure Software Supply Chain
```

Esse é provavelmente o principal insight combinado dos dois conteúdos.

---
