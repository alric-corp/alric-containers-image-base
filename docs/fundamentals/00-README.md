# V6 — Marcos de Estudo e Consolidação

> Fonte de verdade: `container-image-security-wolfi-apko-melange-v6.md`.
>
> Os arquivos abaixo preservam integralmente as seções da V6. A divisão apenas separa o documento em faixas contíguas para facilitar trabalho em modelos de contexto longo.

**Material de estudo do ecossistema, não documentação deste produto.**
Cobre o modelo geral do Chainguard/Wolfi/apko/Melange/Sigstore, incluindo
componentes que este produto não implementa (ex.: Policy Controller e
enforcement de admission no Kubernetes, `DEFERRED` por decisão registrada —
ver "Nível de maturidade" na
[RFC-013](../../RFC-013-Image-Base-Completa-com-Mermaid.md)). Para o que a
fábrica de fato implementa e comprova, use a RFC e os
[ADRs](../adr/README.md); use este material para contexto de fundamentos,
não como referência do estado atual do produto.

## Como usar no projeto

1. Adicione todos os arquivos `.md` ao projeto.
2. Use este `00-README.md` como mapa.
3. Peça ao modelo para ler todos os arquivos, mas executar **um marco por vez**.
4. Para consolidação final, peça uma revisão cruzada de todos os marcos.

## Prompt recomendado

```text
Os arquivos deste projeto formam uma única fonte de verdade dividida em marcos.

Leia o README e considere todos os marcos como partes do mesmo material.
Ao trabalhar em um marco, preserve a consistência com os demais.
Não descarte conceitos por aparecerem novamente em marcos posteriores: use as versões posteriores como refinamentos da evolução do material.

Execute somente o marco solicitado.
Antes de reescrever, identifique redundâncias internas, dependências conceituais e possíveis pontos que precisam ser movidos ou consolidados.
Não invente fatos que não estejam nas fontes do projeto.
```

## Visão geral original da V6

# Container Image Security — Wolfi, apko, Melange, OIDC, Sigstore Policy Controller e Verifiable Software Supply Chain

## 📋 Visão Geral

Este material consolida os vídeos analisados e a documentação oficial do ecossistema Chainguard sobre construção de imagens de container com foco em:

- segurança;
- rastreabilidade;
- redução de superfície de ataque;
- composição declarativa;
- geração de artefatos verificáveis;
- melhor visibilidade para scanners de vulnerabilidade;
- integração com SBOM e assinatura de artefatos;
- enforcement de políticas no admission do Kubernetes.

Os principais componentes discutidos são:

- **Wolfi** — uma *undistro* voltada ao ecossistema de containers e à software supply chain;
- **Melange** — transforma código-fonte em pacotes APK versionados e assinados;
- **apko** — compõe imagens OCI declarativas, reproduzíveis e normalmente de camada única (*single-layer*) a partir desses pacotes APK.
- **Sigstore Policy Controller** — transforma assinaturas, attestations e políticas em decisões de admissão no Kubernetes.

A ideia central não é apenas criar imagens menores.

> O objetivo é construir imagens em que seja possível saber exatamente o que existe dentro delas, de onde cada componente veio e como ele foi produzido.

---

## Ordem dos marcos

| Marco | Arquivo | Seções V6 | Tema |
|---:|---|---:|---|
| 01 | `01-fundamentos-container-e-supply-chain.md` | 1–37 | Fundamentos: Dockerfile, apko, Melange, SBOM e Software Supply Chain |
| 02 | `02-wolfi-distroless-e-runtime.md` | 38–54 | Wolfi, Distroless, Runtime e superfície de ataque |
| 03 | `03-trust-sbom-provenance-e-freshness.md` | 55–80 | Trust, SBOM, Provenance, assinatura e Freshness |
| 04 | `04-apko-melange-reprodutibilidade.md` | 81–100 | apko, Melange, reprodutibilidade, lockfiles e multi-arch |
| 05 | `05-sbom-vex-attestations.md` | 101–123 | SBOM avançada, Attestations, VEX e supply chain verificável |
| 06 | `06-oidc-octo-sts-renovate.md` | 124–141 | OIDC, Octo STS, identidade de workload e Renovate |
| 07 | `07-wolfi-apk-oci-package-engineering.md` | 142–167 | Wolfi package engineering, APK, versionamento e OCI |
| 08 | `08-cosign-sigstore-airgap.md` | 168–203 | Cosign, Sigstore, Fulcio/Rekor, bootstrap trust e Air-gap |
| 09 | `09-policy-controller-admission-core.md` | 204–229 | Policy Controller: assinatura, SBOM, CVEs e Admission |
| 10 | `10-policy-engineering-runtime-fulcio-rekor.md` | 230–263 | Policy engineering, runtime security, Fulcio e Rekor |
| 11 | `11-arquitetura-checklists-conclusao.md` | 264–272 | Arquitetura final, checklists e conclusão V6 |

## Arquivo de referências

`99-referencias.md` contém as referências de vídeos, documentação oficial e observações históricas da V6.

## Cobertura

Todos os capítulos numerados de **1 a 272** aparecem exatamente uma vez entre os marcos.
