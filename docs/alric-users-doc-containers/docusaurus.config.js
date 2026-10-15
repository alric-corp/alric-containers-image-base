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
      },
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
          editUrl: github + alric + project + "/edit/develop/docs/alric-users-doc-containers/",
        },
        blog: false,
        theme: {
          customCss: require.resolve("./src/css/custom.css"),
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
      navbar: {
        title: "Containers Products",
        logo: {
          alt: "Runners",
          src: "/img/logoEscura.png",
          srcDark: "/img/logoClaro.png",
        },
        items: [],
      },
      footer: {
        style: "dark",
        links: [],
        copyright: `Copyright © ${new Date().getFullYear()} Alric Corp. Todos os direitos reservados.`,
      },
      prism: {
        theme: lightCodeTheme,
        darkTheme: darkCodeTheme,
      },
    }),
};

module.exports = config;
