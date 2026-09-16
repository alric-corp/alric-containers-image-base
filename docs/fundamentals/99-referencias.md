# Referências — V6

> Referências e observações preservadas do documento V6 original.

---
## Referências dos vídeos

### Vídeo 1 — apko + Melange

Pontos principais discutidos aproximadamente em:

- **03:39–07:25** — conceito do apko e visibilidade para scanners;
- **07:30–10:40** — SBOM, imagens mínimas e redução de tamanho;
- **10:39–11:31** — imagens sem shell e debugging;
- **13:49–16:24** — comparação com Distroless;
- **38:50–40:50** — estrutura declarativa do apko;
- **41:39–46:43** — funcionamento do pipeline do Melange;
- **47:08–59:34** — criação, assinatura e uso dos APKs;
- **59:55–1:04:15** — secure software factory, CI/CD e repositórios;
- **1:09:50–1:12:34** — assinatura, Sigstore, `scratch` e scanners.


### Vídeo 2 — Wolfi / Software Supply Chain

Pontos adicionais discutidos aproximadamente em:

- **06:47–09:31** — limitações conceituais do Dockerfile e comandos arbitrários;
- **09:38–11:11** — `ko`, Jib e Bazel como alternativas;
- **11:17–12:28** — conceito de Distroless;
- **12:34–14:21** — Wolfi como *undistro*, rolling release, APK e SBOM;
- **14:26–15:43** — características do APK e resolução de dependências;
- **16:03–19:54** — scanners, quantidade de pacotes, CVEs e superfície de ataque;
- **20:00–22:37** — pacotes Wolfi, builds declarativos e reprodutíveis;
- **22:42–26:30** — imagens como substituição de runtime, rootless e variantes de desenvolvimento;
- **26:43–29:42** — apko + Melange, SBOM por pacote e composição final da imagem.

> Os números de tamanho, quantidade de pacotes e vulnerabilidades apresentados nos vídeos devem ser interpretados como resultados das demonstrações daquele momento, e não como benchmarks universais.


### Vídeo 3 — Trust, SBOM, Signing e Custom Distroless

Pontos adicionais discutidos aproximadamente em:

- **01:02–05:34** — conteúdo real de uma imagem e árvores de dependências;
- **05:39–07:25** — supply chain attacks, typosquatting e dependency confusion;
- **07:25–09:58** — diferença entre assinatura, confiança e SBOM;
- **10:06–14:12** — Dockerfile imperativo, layers e composição declarativa;
- **16:31–20:27** — base images, multi-stage e limitações de distroless genérico;
- **20:38–24:50** — apko, APK e Wolfi como base para custom distroless;
- **24:56–30:56** — freshness, timezone data, CA bundles e trust-manager;
- **31:03–32:15** — aplicação própria como pacote Melange;
- **34:13–40:51** — assinatura, build environment e composição com apko;
- **44:04–47:26** — SBOM associada ao artefato e dependências dentro do binário;
- **47:33–48:23** — assinatura e transparency log.

### Nota técnica sobre o conteúdo do vídeo 3

O vídeo apresenta a ideia de que APK não permitiria scripts arbitrários durante instalação. Essa formulação é ampla demais: o ecossistema APK suporta scripts como `pre-install`, `post-install`, `pre-upgrade`, `post-upgrade`, `pre-deinstall` e `post-deinstall`.

O princípio que permanece válido para nosso material é que **apko não oferece um `RUN` arbitrário em sua configuração de composição**, o que reduz lógica imperativa e favorece builds declarativos e reprodutíveis.

Também evitamos depender dos detalhes específicos mostrados no vídeo sobre como SBOMs eram anexadas ao registry, porque os mecanismos OCI, Cosign e registry attachment evoluíram desde então. O conceito durável é associar SBOM, provenance e assinatura ao digest do artefato.


## Documentação oficial incorporada na V4

- apko overview — https://edu.chainguard.dev/open-source/build-tools/apko/overview/
- apko FAQs — https://edu.chainguard.dev/open-source/build-tools/apko/faq/
- Getting started with apko — https://edu.chainguard.dev/open-source/build-tools/apko/getting-started-with-apko/
- Troubleshooting apko builds — https://edu.chainguard.dev/open-source/build-tools/apko/troubleshooting/
- Bazel rules for apko — https://edu.chainguard.dev/open-source/build-tools/apko/bazel-rules/
- melange overview — https://edu.chainguard.dev/open-source/build-tools/melange/overview/
- Getting started with melange — https://edu.chainguard.dev/open-source/build-tools/melange/getting-started-with-melange/
- Troubleshooting melange builds — https://edu.chainguard.dev/open-source/build-tools/melange/troubleshooting/
- melange FAQs — https://edu.chainguard.dev/open-source/build-tools/melange/faq/
- What is an SBOM? — https://edu.chainguard.dev/open-source/sbom/what-is-an-sbom/
- What makes a good SBOM? — https://edu.chainguard.dev/open-source/sbom/what-makes-a-good-sbom/
- Getting started with OpenVEX and vexctl — https://edu.chainguard.dev/open-source/sbom/getting-started-openvex-vexctl/
- What is OpenVEX? — https://edu.chainguard.dev/open-source/sbom/what-is-openvex/
- SBOMs and attestations — https://edu.chainguard.dev/open-source/sbom/sboms-and-attestations/

### Observação sobre exemplos e versões

Os exemplos de comandos, versões de ferramentas e formatos apresentados na documentação podem evoluir. Neste guia, os conceitos duráveis são priorizados:

```text
declarative composition
locked inputs
trusted repositories
signed packages
build-time SBOM
SBOM quality
attestation
VEX
artifact identity by digest
policy enforcement
```


## Documentação oficial incorporada na V5

### Octo STS

- Octo STS overview — https://edu.chainguard.dev/open-source/octo-sts/overview/
- Octo STS FAQ — https://edu.chainguard.dev/open-source/octo-sts/faq/
- Updating container images with Renovate (and no PATs!) — https://edu.chainguard.dev/open-source/octo-sts/updating-container-images-with-renovate/

### Wolfi

- Wolfi overview — https://edu.chainguard.dev/open-source/wolfi/overview/
- Building a Wolfi package — https://edu.chainguard.dev/open-source/wolfi/building-a-wolfi-package/
- Wolfi FAQs — https://edu.chainguard.dev/open-source/wolfi/faq/
- Why apk — https://edu.chainguard.dev/open-source/wolfi/apk-package-manager/
- Creating Wolfi images with Dockerfiles — https://edu.chainguard.dev/open-source/wolfi/wolfi-with-dockerfiles/
- Package version selection — https://edu.chainguard.dev/open-source/wolfi/apk-version-selection/

### OCI

- What is the Open Container Initiative? — https://edu.chainguard.dev/open-source/oci/what-is-the-oci/
- What are OCI artifacts? — https://edu.chainguard.dev/open-source/oci/what-are-oci-artifacts/

### Cosign / Sigstore

- How to keyless sign a container image with Sigstore — https://edu.chainguard.dev/open-source/sigstore/how-to-keyless-sign-a-container-with-sigstore/
- An introduction to Cosign — https://edu.chainguard.dev/open-source/sigstore/cosign/an-introduction-to-cosign/
- How to install Cosign — https://edu.chainguard.dev/open-source/sigstore/cosign/how-to-install-cosign/
- How to sign a container with Cosign — https://edu.chainguard.dev/open-source/sigstore/cosign/how-to-sign-a-container-with-cosign/
- How to sign blobs and standard files with Cosign — https://edu.chainguard.dev/open-source/sigstore/cosign/how-to-sign-blobs-with-cosign/
- How to sign an SBOM with Cosign — https://edu.chainguard.dev/open-source/sigstore/cosign/how-to-sign-an-sbom-with-cosign/
- How to verify file signatures with Cosign — https://edu.chainguard.dev/open-source/sigstore/cosign/how-to-verify-file-signatures-with-cosign/
- Verifying signatures in air-gapped environments — https://edu.chainguard.dev/open-source/sigstore/cosign/verifying-in-air-gapped-environments/


### Policy Controller / Admission / Fulcio / Rekor

- Sigstore Policy Controller — documentação atual — https://docs.sigstore.dev/policy-controller/overview/
- Sigstore Policy Controller — instalação atual — https://docs.sigstore.dev/policy-controller/installation/
- Enforce SBOM attestation with Policy Controller — https://edu.chainguard.dev/open-source/sigstore/policy-controller/policies/enforce-sbom-attestation-with-policy-controller/
- Disallowing non-default capabilities — https://edu.chainguard.dev/open-source/sigstore/policy-controller/policies/disallowing-non-default-capabilities-with-policy-controller/
- Disallowing privileged pods — https://edu.chainguard.dev/open-source/sigstore/policy-controller/policies/disallowing-privileged-containers-with-policy-controller/
- Disallowing run as root user — https://edu.chainguard.dev/open-source/sigstore/policy-controller/policies/disallowing-run-as-root-user-with-policy-controller/
- Maximum container image age — https://edu.chainguard.dev/open-source/sigstore/policy-controller/policies/maximum-image-age-policy-controller/
- Disallowing unsafe sysctls — https://edu.chainguard.dev/open-source/sigstore/policy-controller/policies/disallowing-unsafe-sysctls-with-policy-controller/
- Verify signed Chainguard Containers — https://edu.chainguard.dev/open-source/sigstore/policy-controller/policies/using-policy-controller-to-verify-signed-chainguard-images/
- Limit high or critical CVEs in your image workloads — https://edu.chainguard.dev/open-source/sigstore/policy-controller/policies/critical-cve-policy/
- Rego policies — https://edu.chainguard.dev/open-source/sigstore/policy-controller/policies/chainguard-enforce-rego-policies/
- Example policies — https://edu.chainguard.dev/open-source/sigstore/policy-controller/policies/chainguard-enforce-policy-examples/
- An introduction to Fulcio — https://edu.chainguard.dev/open-source/sigstore/fulcio/an-introduction-to-fulcio/
- How to generate a Fulcio certificate — https://edu.chainguard.dev/open-source/sigstore/fulcio/how-to-generate-a-fulcio-certificate/
- How to inspect and verify Fulcio certificates — https://edu.chainguard.dev/open-source/sigstore/fulcio/how-to-inspect-and-verify-fulcio-certificates/
- An introduction to Rekor — https://edu.chainguard.dev/open-source/sigstore/rekor/an-introduction-to-rekor/
- How to install the Rekor CLI — https://edu.chainguard.dev/open-source/sigstore/rekor/how-to-install-rekor/
- How to query Rekor — https://edu.chainguard.dev/open-source/sigstore/rekor/how-to-query-rekor/
- How to sign and upload metadata to Rekor — https://edu.chainguard.dev/open-source/sigstore/rekor/how-to-sign-and-upload-metadata-to-rekor/
- How to set up an instance of Rekor locally — https://edu.chainguard.dev/open-source/sigstore/rekor/install-a-rekor-instance/

### Observação sobre documentação histórica

Alguns tutoriais incorporados foram originalmente escritos para versões antigas de Cosign/Sigstore e são preservados por valor educacional.

Nesta V6, comandos antigos não são tratados como orientação normativa atual. Os conceitos duráveis priorizados são:

```text
OIDC identity
short-lived credentials
keyless signing
artifact digest
signature verification
SBOM attestation
transparency
air-gapped trust roots
artifact metadata preservation
```

Para implementação real, use a documentação correspondente à versão atual das ferramentas.
