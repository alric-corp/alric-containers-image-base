# SPEC — P1-05 — Sigstore Trust Model ADR

## Objetivo

Formalizar o modelo de confiança realmente usado pela RFC-013 e a decisão
externa necessária antes da adoção corporativa. Esta fatia entrega um ADR
PROPOSED; não muda assinatura, provenance, SBOM ou infraestrutura.

## Requisitos

- R1: descrever separadamente execução/identidade GitHub, CA Fulcio, evidência
  de transparência Rekor, distribuição das raízes, armazenamento ECR e governança Git.
- R2: distinguir assinatura de imagem, provenance e SBOM attestation, seus
  subjects e limites; assinatura não implica segurança, scan ou aprovação humana.
- R3: registrar repository/workflow/ref/issuer e IDs reais do sandbox, separando
  a identidade corporativa ainda não definida e o mecanismo de nomes históricos.
- R4: explicar metadados públicos, conteúdo do artifact e diferenças entre
  envio ao serviço de transparência e conteúdo persistido no log, conforme
  as versões/configurações realmente consumidas.
- R5: diferenciar GitHub attestations de repositório público/privado, raízes
  e transparência; tornar explícito que isso não reconfigura o Cosign direto.
- R6: apontar para o contrato canônico de verificação por OCI index digest,
  distinguindo gates existentes, verificação recomendada e enforcement ausente.
- R7: propor posição para Segurança/AppSec, com alternativas, riscos,
  disponibilidade e condições de revisão; decisão corporativa permanece externa.

## Restrições e invariantes

Código atual vence snapshots. Fontes externas devem ser oficiais e datadas.
Não atribuir SLSA level formal nem aprovação corporativa. Não criar novo
controle, alterar policy ou substituir as decisões anteriores. Private Sigstore
não é requisito automático. Preservar os estados de hosted acceptance existentes.

## Fora do escopo

Workflows, signing/provenance/SBOM, policies, IAM/ECR, PKI, mirror, scanner,
admission, infraestrutura e outros itens da RFC. Sem commit, push ou PR.

## Dependências

Segurança/AppSec decide a aceitação de serviços/metadados públicos; Containers
Products prepara o handoff. A decisão não bloqueia a entrega documental, mas
continua necessária para produção. Revisão arquitetural posterior: Opus 5 MAX.

## Conclusão

Ver [acceptance.md](acceptance.md); verificação local não é auto-aprovação.
