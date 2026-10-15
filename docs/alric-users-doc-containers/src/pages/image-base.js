import Link from "@docusaurus/Link";
import Layout from "@theme/Layout";
import MDXContent from "@theme/MDXContent";
import TOC from "@theme/TOC";
import React from "react";

import ImageBaseContent, { toc } from "../content/image-base.md";
import styles from "./image-base.module.css";

function Chevron() {
  return <span className={styles.chevron} aria-hidden="true" />;
}

function HomeIcon() {
  return <span className={styles.homeIcon} aria-hidden="true" />;
}

function ProductMarks() {
  return (
    <span className={styles.productMarks} aria-hidden="true">
      <span className={styles.markBlue} />
      <span className={styles.markRed} />
      <span className={styles.markOrange} />
    </span>
  );
}

export default function ImageBase() {
  return (
    <Layout
      title="Factory Distroless - Imagens base corporativas"
      description="Guia de consumo das imagens base corporativas: catálogo, Dockerfile, atualizações, certificados e troubleshooting."
      noNavbar
      noFooter
    >
      <div className={styles.page} data-theme="dark">
        <header className={styles.topBar}>
          <div className={styles.topBarContent}>
            <Link className={styles.brand} to="/">
              <ProductMarks />
              <span>Containers Products</span>
            </Link>

            <nav className={styles.topNavigation} aria-label="Produtos de containers">
              <span className={styles.navigationItem}>
                EKS
                <Chevron />
              </span>
              <span className={styles.navigationItem}>ECS</span>
              <div className={`${styles.ecrMenu} ${styles.activeEcrMenu}`}>
                <button className={`${styles.navigationItem} ${styles.ecrTrigger}`} type="button">
                  ECR
                  <Chevron />
                </button>
                <div className={styles.ecrDropdown}>
                  <Link aria-current="page" className={styles.dropdownLink} to="/image-base">
                    Image Base
                  </Link>
                </div>
              </div>
              <span className={styles.optionalNavigationItem}>Bottlerocket</span>
              <span className={styles.optionalNavigationItem}>Ajuda</span>
              <span className={styles.optionalNavigationItem}>Contribua</span>
              <span className={styles.optionalNavigationItem}>Comunicados</span>
              <span className={styles.searchLabel} aria-hidden="true">
                Buscar (Ctrl+K)
              </span>
            </nav>
          </div>
        </header>

        <main className={styles.docsLayout}>
          <aside className={styles.sidebar} aria-label="Navegação da documentação">
            <span className={styles.sidebarItem}>Guia do Desenvolvedor</span>
          </aside>

          <article className={styles.content}>
            <div className={styles.breadcrumbs}>
              <HomeIcon />
              <span className={styles.breadcrumbSeparator}>/</span>
              <span className={styles.breadcrumbCurrent}>Guia do Desenvolvedor</span>
            </div>

            <h1>Factory Distroless - Imagens base corporativas</h1>
            <p className={styles.lead}>
              <strong>Menos manutenção da base. Mais foco na sua aplicação.</strong>
              Sua squad consome uma base no Dockerfile e acrescenta seu código
              ou artefato compilado. Você mantém o controle da aplicação e do deploy.
            </p>

            <aside className={styles.notice}>
              <span className={styles.noticeIcon} aria-hidden="true">i</span>
              <div>
                <strong>IMAGENS BASE DISPONÍVEIS PARA CONSUMO</strong>
                <p>
                  Escolha a família e a versão compatíveis com sua aplicação no{" "}
                  <a href="#catalogo">catálogo</a> e siga o{" "}
                  <a href="#exemplos">guia de uso no Dockerfile</a>.
                </p>
              </div>
            </aside>

            <hr />

            <div className={`${styles.markdown} markdown`}>
              <MDXContent>
                <ImageBaseContent />
              </MDXContent>
            </div>
          </article>

          <aside className={styles.tableOfContents} aria-label="Nesta página">
            <TOC toc={toc} minHeadingLevel={2} maxHeadingLevel={2} />
          </aside>
        </main>
      </div>
    </Layout>
  );
}
