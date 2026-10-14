import Link from "@docusaurus/Link";
import Layout from "@theme/Layout";
import React from "react";

import styles from "./image-base.module.css";

const tableOfContents = [
  "1. O que é a solução?",
  "2. Por que usar as imagens corporativas?",
  "3. Glossário rápido",
  "4. O que você ganha?",
  "5. Responsabilidades - matriz RACI",
  "6. Qual imagem devo usar?",
  "7. Runtime x -dev",
  "8. Como usar no Dockerfile",
  "9. Como funcionam atualizações e correções de CVE?",
];

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
      description="Guia temporário para Image Base."
      noNavbar
      noFooter
    >
      <div className={styles.page}>
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
              Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sua equipe
              mantém a aplicação e controla seu deploy.
            </p>

            <aside className={styles.notice}>
              <span className={styles.noticeIcon} aria-hidden="true">i</span>
              <div>
                <strong>IMAGENS BASE DISPONÍVEIS PARA CONSUMO</strong>
                <p>
                  Lorem ipsum dolor sit amet, consectetur adipiscing elit. Utilize
                  esta página temporária como base para o conteúdo definitivo.
                </p>
              </div>
            </aside>

            <hr />

            <section>
              <h2>1. O que é a solução?</h2>
              <p>
                Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do
                eiusmod tempor incididunt ut labore et dolore magna aliqua.
              </p>
            </section>

            <section>
              <h2>2. Por que usar as imagens corporativas?</h2>
              <p>
                Lorem ipsum dolor sit amet, consectetur adipiscing elit. Ut enim ad
                minim veniam, quis nostrud exercitation ullamco laboris.
              </p>
            </section>

            <section>
              <h2>3. Glossário rápido</h2>
              <p>
                Lorem ipsum dolor sit amet, consectetur adipiscing elit. Duis aute
                irure dolor in reprehenderit in voluptate velit esse cillum dolore.
              </p>
            </section>
          </article>

          <aside className={styles.tableOfContents} aria-label="Nesta página">
            {tableOfContents.map((item) => (
              <span className={item.startsWith("5.") ? styles.activeTocItem : undefined} key={item}>
                {item}
              </span>
            ))}
          </aside>
        </main>
      </div>
    </Layout>
  );
}