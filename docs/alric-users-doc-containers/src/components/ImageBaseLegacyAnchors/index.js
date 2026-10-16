import { useEffect } from "react";
import { useHistory, useLocation } from "@docusaurus/router";
import { useBaseUrlUtils } from "@docusaurus/useBaseUrl";

/**
 * Âncoras do antigo guia de página única em /image-base e o novo destino de
 * cada seção. O fragmento (#...) não chega ao servidor, então a compatibilidade
 * dos links antigos é feita no navegador, pela página /image-base.
 *
 * As chaves são os ids gerados pelo guia anterior, inclusive os com acento.
 */
export const LEGACY_ANCHORS = {
  solucao: "/image-base/#em-resumo",
  "por-que-usar": "/image-base/por-que-usar",
  glossario: "/image-base/referencia/glossario",
  beneficios: "/image-base/por-que-usar#beneficios",
  "os-termos-de-segurança-sem-complicação": "/image-base/seguranca/validacoes#evidencias",
  responsabilidades: "/image-base/seguranca/responsabilidades",
  catalogo: "/image-base/catalogo",
  "runtime-dev": "/image-base/catalogo/runtime-dev",
  exemplos: "/image-base/como-utilizar/dockerfile",
  dockerfile: "/image-base/como-utilizar/dockerfile",
  atualizacoes: "/image-base/seguranca/atualizacoes",
  "o-novo-build-vai-incorporar-a-correção":
    "/image-base/seguranca/atualizacoes#o-novo-build-incorpora-a-correcao",
  "e-se-a-aplicação-ficar-meses-sem-pr": "/image-base/seguranca/atualizacoes#aplicacao-sem-mudancas",
  certificados: "/image-base/seguranca/certificados",
  arquiteturas: "/image-base/referencia/arquiteturas",
  troubleshooting: "/image-base/troubleshooting",
  "sintomas-e-primeiras-verificações": "/image-base/troubleshooting#sintomas",
  "diagnóstico-interativo": "/image-base/troubleshooting/eks#container-efemero",
  "segurança-da-execução-continua-sendo-configuração-do-workload":
    "/image-base/como-utilizar/eks#security-context",
  faq: "/image-base/referencia/faq",
  suporte: "/image-base/suporte",
  "checklist-de-adoção": "/image-base/suporte#checklist-de-adocao",
  "referências-externas": "/image-base/suporte#referencias-externas",
};

// Navegadores entregam o fragmento percentual-codificado (#seguran%C3%A7a...).
function legacyAnchorId(hash) {
  const fragment = hash.replace(/^#/, "");
  try {
    return decodeURIComponent(fragment);
  } catch {
    return fragment;
  }
}

/** Redireciona links antigos (/image-base#secao) para a página nova da seção. */
export default function ImageBaseLegacyAnchors() {
  const { hash } = useLocation();
  const history = useHistory();
  const { withBaseUrl } = useBaseUrlUtils();

  useEffect(() => {
    const target = LEGACY_ANCHORS[legacyAnchorId(hash)];
    if (target) {
      history.replace(withBaseUrl(target));
    }
  }, [hash, history, withBaseUrl]);

  return null;
}
