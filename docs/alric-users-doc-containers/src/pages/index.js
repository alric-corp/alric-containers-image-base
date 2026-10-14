import Link from "@docusaurus/Link";
import Layout from "@theme/Layout";
import React, { useId, useState } from "react";

import styles from "./index.module.css";

/**
 * Modelo de dados dos produtos.
 *
 * Cada produto tem um cabeçalho fixo (Região A) e duas jornadas: `developers`
 * e `sre`. Apenas uma jornada é exibida por vez, conforme o seletor global.
 *
 * Observações sobre links (ver diagnóstico):
 * - Os "acessos rápidos" preservam os rótulos existentes. No portal atual eles
 *   eram apenas rótulos decorativos (não eram links reais), portanto são
 *   mantidos como rótulos sem destino inventado (`href` ausente) para não criar
 *   rotas fictícias.
 * - O rodapé usa somente destinos reais existentes. Hoje apenas Image Base tem
 *   uma rota (`/image-base`). EKS e ECS ainda não possuem página de destino, por
 *   isso o rodapé desses produtos fica informativo (sem link fictício).
 */
const AUDIENCES = [
  { id: "developers", label: "Developers" },
  { id: "sre", label: "SRE" },
];

const DEFAULT_AUDIENCE = "developers";

const products = [
  {
    id: "imageBase",
    name: "Image Base",
    subtitle: "Imagens corporativas hardened",
    journeys: {
      developers: {
        title: "Começar Agora",
        description:
          "Guia completo para usar imagens base hardened e distroless no Dockerfile da sua aplicação.",
        quickLinks: [
          { label: "Como usar" },
          { label: "Catálogo" },
          { label: "Runtime x -dev" },
          { label: "FAQ" },
        ],
      },
      sre: {
        title: "Entenda a Solução",
        description:
          "Conheça os benefícios, responsabilidades e o modelo de manutenção das imagens base corporativas.",
        quickLinks: [
          { label: "Por que usar?" },
          { label: "Benefícios" },
          { label: "Troubleshooting" },
        ],
      },
    },
    // Único destino real existente para a documentação completa.
    docs: { label: "Explorar Image Base", href: "/image-base" },
  },
  {
    id: "eks",
    name: "EKS",
    subtitle: "Kubernetes gerenciado",
    journeys: {
      developers: {
        title: "Jornada de Aplicação",
        description:
          "Publique suas aplicações em clusters Kubernetes usando GitOps, Helm ou kubectl.",
        quickLinks: [{ label: "GitOps" }, { label: "Helm" }, { label: "Kubectl" }],
      },
      sre: {
        title: "Jornada Operacional",
        description:
          "Crie e opere clusters EKS pelo Innersource, do primeiro deploy à atualização de versão.",
        quickLinks: [{ label: "Innersource EKS" }, { label: "Innersource Genos" }],
      },
    },
    // Sem rota de destino existente ainda (ver diagnóstico/limitações).
    docs: { label: "Explorar EKS" },
  },
  {
    id: "ecs",
    name: "ECS",
    subtitle: "Orquestração de containers AWS",
    journeys: {
      developers: {
        title: "Jornada de Aplicação",
        description:
          "Publique suas aplicações em tasks ECS usando CodeDeploy ou workers assíncronos.",
        quickLinks: [{ label: "CodeDeploy" }, { label: "Worker" }],
      },
      sre: {
        title: "Jornada Operacional",
        description:
          "Crie e opere clusters ECS pelo Innersource ECS Cluster, do primeiro deploy à evolução da infra.",
        quickLinks: [{ label: "Innersource ECS Cluster" }],
      },
    },
    // Sem rota de destino existente ainda (ver diagnóstico/limitações).
    docs: { label: "Explorar ECS" },
  },
];

function Chevron() {
  return <span className={styles.chevron} aria-hidden="true" />;
}

/** Detecta se um href aponta para fora do portal. */
function isExternalHref(href) {
  return typeof href === "string" && /^(https?:)?\/\//.test(href);
}

// Glifos oficiais AWS recoloridos com o accent de cada card via máscara CSS,
// mantendo o mesmo estilo visual entre os três produtos.
// Image Base usa o ícone do Amazon ECR (onde as imagens base são publicadas).
const PRODUCT_ICONS = {
  imageBase: "/img/ecr-glyph.svg",
  eks: "/img/eks-glyph.svg",
  ecs: "/img/ecs-glyph.svg",
};

function ProductIcon({ productId }) {
  return (
    <span className={styles.serviceIcon} aria-hidden="true">
      <span
        className={styles.maskedGlyph}
        style={{ "--glyph": `url(${PRODUCT_ICONS[productId]})` }}
      />
    </span>
  );
}

/** Região C — um acesso rápido (link real ou rótulo preservado sem destino). */
function QuickLink({ item }) {
  const external = isExternalHref(item.href);

  if (item.href) {
    return (
      <Link
        className={styles.quickLink}
        to={item.href}
        {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      >
        <span className={styles.quickLinkLabel}>{item.label}</span>
        {external ? (
          <span className={styles.externalIcon} aria-label="(abre em nova aba)" role="img">
            ↗
          </span>
        ) : (
          <span className={styles.quickLinkArrow} aria-hidden="true" />
        )}
      </Link>
    );
  }

  // Preserva o rótulo existente sem inventar um destino.
  return (
    <span className={styles.quickLinkStatic}>
      <span className={styles.quickLinkLabel}>{item.label}</span>
    </span>
  );
}

/** Região D — rodapé de documentação completa. */
function ProductDocsFooter({ docs }) {
  if (docs?.href) {
    const external = isExternalHref(docs.href);
    return (
      <Link
        className={styles.docsLink}
        to={docs.href}
        {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      >
        {docs.label}
        <span className={styles.docsArrow} aria-hidden="true" />
      </Link>
    );
  }

  // Sem destino real: mantém a ação visível porém informativa (não é um link falso).
  return (
    <span className={styles.docsLinkDisabled} aria-disabled="true">
      {docs.label}
      <span className={styles.docsSoon}>em breve</span>
    </span>
  );
}

function ProductCard({ product, audience }) {
  const journey = product.journeys[audience];

  return (
    <article className={`${styles.productCard} ${styles[product.id]}`}>
      {/* Região A — Cabeçalho fixo */}
      <header className={styles.productHeader}>
        <ProductIcon productId={product.id} />
        <div className={styles.productHeaderText}>
          <h3 className={styles.productName}>{product.name}</h3>
          <p className={styles.productSubtitle}>{product.subtitle}</p>
        </div>
      </header>

      <div className={styles.cardBody}>
        {/* Região B — Jornada dinâmica */}
        <section className={styles.journey} aria-live="polite">
          <h4 className={styles.journeyTitle}>{journey.title}</h4>
          <p className={styles.journeyDescription}>{journey.description}</p>
        </section>

        {/* Região C — Acessos rápidos */}
        {journey.quickLinks?.length > 0 && (
          <nav
            className={styles.quickLinks}
            aria-label={`Acessos rápidos de ${product.name} para ${
              audience === "sre" ? "SRE" : "Developers"
            }`}
          >
            {journey.quickLinks.map((item) => (
              <QuickLink key={item.label} item={item} />
            ))}
          </nav>
        )}
      </div>

      {/* Região D — Rodapé fixo */}
      <footer className={styles.cardFooter}>
        <ProductDocsFooter docs={product.docs} />
      </footer>
    </article>
  );
}

/** Seletor global segmentado implementado como radio group acessível. */
function AudienceSelector({ audience, onChange }) {
  const groupId = useId();

  return (
    <div
      className={styles.audienceSelector}
      role="radiogroup"
      aria-label="Selecionar perfil"
    >
      {AUDIENCES.map((option) => {
        const selected = option.id === audience;
        const inputId = `${groupId}-${option.id}`;
        return (
          <label
            key={option.id}
            className={styles.segment}
            htmlFor={inputId}
            data-selected={selected}
          >
            <input
              id={inputId}
              className={styles.segmentInput}
              type="radio"
              name={`audience-${groupId}`}
              value={option.id}
              checked={selected}
              onChange={() => onChange(option.id)}
            />
            <span className={styles.segmentLabel}>{option.label}</span>
          </label>
        );
      })}
    </div>
  );
}

export default function Home() {
  const [audience, setAudience] = useState(DEFAULT_AUDIENCE);

  return (
    <Layout
      title="Containers Products"
      description="Documentação centralizada para Factory Distroless, EKS e ECS."
      noNavbar
      noFooter
    >
      <div className={styles.page}>
        <header className={styles.topBar}>
          <nav className={styles.topNavigation} aria-label="Produtos de containers">
            <span className={styles.navigationItem}>
              EKS
              <Chevron />
            </span>
            <span className={styles.navigationItem}>ECS</span>
            <div className={styles.ecrMenu}>
              <button className={`${styles.navigationItem} ${styles.ecrTrigger}`} type="button">
                ECR
                <Chevron />
              </button>
              <div className={styles.ecrDropdown}>
                <Link className={styles.dropdownLink} to="/image-base">
                  Image Base
                </Link>
              </div>
            </div>
          </nav>
        </header>

        <section className={styles.hero} aria-labelledby="containers-products-title">
          <div className={styles.heroContent}>
            <h1 id="containers-products-title">Containers Products</h1>
            <p>Documentação centralizada para Factory Distroless, EKS e ECS.</p>
          </div>
        </section>

        <section className={styles.productsArea} aria-labelledby="products-section-title">
          <div className={styles.productsInner}>
            <div className={styles.sectionHeader}>
              <h2 id="products-section-title" className={styles.sectionTitle}>
                Explore nossos produtos
              </h2>
              <AudienceSelector audience={audience} onChange={setAudience} />
            </div>

            <div className={styles.cardsGrid}>
              {products.map((product) => (
                <ProductCard key={product.id} product={product} audience={audience} />
              ))}
            </div>
          </div>
        </section>

        <footer className={styles.footer}>
          <div className={styles.footerContent}>
            <nav className={styles.footerLinks} aria-label="Links institucionais">
              <span>Quem somos</span>
              <span>Colabora tech</span>
              <span>GitHub</span>
            </nav>
            <p>© 2026 containers products - Todos os direitos reservados</p>
          </div>
        </footer>
      </div>
    </Layout>
  );
}
