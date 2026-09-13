# SPEC — P1-06 — Controles de segurança da fábrica em workflows federados

## Objetivo

Documentar controles existentes, responsabilidades e requisitos corporativos
a confirmar, preservando a arquitetura própria. A premissa de autoria e
sustentação deve ter uma fonte canônica no ADR desta fatia, com origem no
relato do responsável pelo projeto e limites explícitos.

## Requisitos

- R1: separar autoria/sustentação, implementação atual, requisitos a confirmar
  e dependências externas. Não reabrir a autorização de workflows próprios
  nem interpretá-la como federação OIDC ou dispensa de controles corporativos.
- R2: mapear controles à implementação/evidence existente, sem prometer
  homologação corporativa, cobertura total ou novos gates.
- R3: diferenciar Trivy implementado, Trivy observado no levantamento de
  build/publicação e Veracode SCA descrito no levantamento de segurança.
  Aplicabilidade à fábrica e política das aplicações são questões separadas.
- R4: tratar os levantamentos como referências de interfaces/práticas,
  sem importar thresholds, bypasses, cache, destinos ou convenções.
- R5: registrar responsáveis e perguntas para a validação corporativa,
  limitadas às decisões pendentes. Containers Products mantém e opera a fábrica.
- R6: preservar dados internos e snapshots históricos; outros documentos
  apontam para a premissa canônica, sem duplicá-la nos adaptadores de IA.

## Restrições e invariantes

ADR PROPOSED refere-se às decisões externas abertas; não invalida a premissa
de autoria já informada. Preservar Apko/Melange, scans, contratos, mesmo OCI,
assinatura/provenance/SBOM, promoção/read-back, retry e recovery.
Não inventar ticket, documento formal, homologação de scanner ou hosted PASS.

## Fora do escopo

Código/gates, workflows, policies, integração Veracode, mudança de scanner,
IAM, PKI, rede, ECR e infraestrutura; auditoria geral; commit, push ou PR.

## Dependências

AppSec/Segurança confirma requisitos aplicáveis; Cloud/IAM/Network/PKI fornece
infraestrutura/acessos e seus aceites. Esses itens não impedem a entrega
documental, mas continuam pendentes para operação corporativa.

## Conclusão

Ver [acceptance.md](acceptance.md). Revisão independente posterior, sem auto-aprovação.
