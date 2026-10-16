// @ts-check
// Note: type annotations allow type checking and IDEs autocompletion
// IMPORTANTE: não remova o comentário a seguir, ele é utilizado para a identificação do template utilizado
// TEMPLATE_CHOICE> complete

const { themes } = require("prism-react-renderer");

const lightCodeTheme = themes.github;
const darkCodeTheme = themes.dracula;

const github = "https://www.github.com/";
const alric = "alric-corp/";

// Adicione o nome do seu repositório aqui
const project = "alric-containers-image-base";

const editUrl = github + alric + project + "/edit/develop/docs/alric-users-doc-containers/";

// Itens do menu superior ainda sem página de destino: aparecem como texto,
// sem link nem botão, até existir documentação real para eles.
function staticNavbarItem(label, className = "") {
  return {
    type: "html",
    position: "right",
    className: `cp-navbar-static ${className}`.trim(),
    value: `${label}<span class="cp-sr-only"> (documentação em breve)</span>`,
  };
}

/** @type {import('@docusaurus/types').Config} */
const config = {
  // Configuração Mermaid
  markdown: {
    mermaid: true,
  },
  themes: ["@docusaurus/theme-mermaid"],

  plugins: [
    [
      require.resolve("docusaurus-lunr-search"),
      {
        languages: ["pt"], // define o idioma da busca
        // Sem versões de docs: evita o rótulo "Next" em cada resultado.
        disableVersioning: true,
      },
    ],
    // Documentação de Image Base: instância própria de docs, servida em
    // /image-base. Cada produto do portal pode ganhar sua instância.
    [
      "@docusaurus/plugin-content-docs",
      /** @type {import('@docusaurus/plugin-content-docs').Options} */
      ({
        id: "image-base",
        path: "image-base",
        routeBasePath: "image-base",
        sidebarPath: require.resolve("./sidebars-image-base.js"),
        breadcrumbs: true,
        showLastUpdateAuthor: false,
        showLastUpdateTime: false,
        editUrl,
      }),
    ],
  ],

  organizationName: "alric-corp",
  projectName: project,
  url: github,
  baseUrl: "/", // IMPORTANTE: Não alterar essa informação

  // Customize sua documentação
  title: "Containers Products",
  tagline: "Documentação das imagens base corporativas, EKS e ECS",
  favicon: "img/devops.ico", // Adicione o favicon

  onBrokenLinks: "warn",
  onBrokenMarkdownLinks: "warn",

  i18n: {
    defaultLocale: "pt",
    locales: ["pt"],
  },

  presets: [
    [
      "classic",
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          breadcrumbs: true,
          showLastUpdateAuthor: false,
          showLastUpdateTime: false,
          sidebarPath: require.resolve("./sidebars.js"),
          editUrl,
        },
        blog: false,
        theme: {
          customCss: [
            require.resolve("./src/css/custom.css"),
            require.resolve("./src/css/portal-docs.css"),
          ],
        },
        gtag: {
          trackingID: "G-PBB5KT3DKQ",
          anonymizeIP: true,
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      // O portal só tem tema escuro (a home e a documentação usam a mesma paleta).
      colorMode: {
        defaultMode: "dark",
        disableSwitch: true,
        respectPrefersColorScheme: false,
      },
      navbar: {
        title: "Containers Products",
        // Marca do portal; decorativa porque o título já identifica o link.
        logo: {
          src: "img/containers-products-marks.svg",
          width: 74,
          height: 28,
        },
        items: [
          staticNavbarItem("EKS"),
          staticNavbarItem("ECS"),
          {
            type: "dropdown",
            label: "ECR",
            position: "right",
            // activeBasePath destaca ECR > Image Base em todas as páginas do produto.
            items: [{ label: "Image Base", to: "/image-base/", activeBasePath: "/image-base" }],
          },
          staticNavbarItem("Bottlerocket", "cp-navbar-optional"),
          {
            label: "Ajuda",
            to: "/image-base/suporte",
            position: "right",
            className: "cp-navbar-optional",
          },
          staticNavbarItem("Contribua", "cp-navbar-optional"),
          staticNavbarItem("Comunicados", "cp-navbar-optional"),
          { type: "search", position: "right" },
        ],
      },
      footer: {
        style: "dark",
        links: [],
        copyright: `Copyright © ${new Date().getFullYear()} Alric Corp. Todos os direitos reservados.`,
      },
      prism: {
        theme: lightCodeTheme,
        darkTheme: darkCodeTheme,
        // bash e docker não fazem parte do conjunto padrão do prism-react-renderer.
        additionalLanguages: ["bash", "docker"],
      },
    }),
};

module.exports = config;
