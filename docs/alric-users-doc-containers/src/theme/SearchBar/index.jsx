import React, { useRef, useCallback, useState } from "react";
import clsx from "clsx";
import { useHistory } from "@docusaurus/router";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import { usePluginData } from "@docusaurus/useGlobalData";
import useIsBrowser from "@docusaurus/useIsBrowser";
import { HighlightSearchResults } from "./HighlightSearchResults";

const Search = (props) => {
  const initialized = useRef(false);
  const searchBarRef = useRef(null);
  const [indexReady, setIndexReady] = useState(false);
  const history = useHistory();
  const { siteConfig = {} } = useDocusaurusContext();

  const pluginConfig = (siteConfig.plugins || []).find(
    (plugin) =>
      Array.isArray(plugin) &&
      typeof plugin[0] === "string" &&
      plugin[0].includes("docusaurus-lunr-search")
  );

  const isBrowser = useIsBrowser();
  const { baseUrl } = siteConfig;
  const assetUrl =
    (pluginConfig && pluginConfig[1] && pluginConfig[1]?.assetUrl) || baseUrl;

  const initAlgolia = (searchDocs, searchIndex, DocSearch, options) => {
    new DocSearch({
      searchDocs,
      searchIndex,
      baseUrl,
      inputSelector: "#search-input_react",

      // Override algolia's default selection event, allowing client-side nav
      handleSelected: (_input, _event, suggestion) => {
        const url = suggestion.url || "/";
        const a = document.createElement("a");
        a.href = url;

        _input.setVal(""); // clear value
        _event.target.blur(); // remove focus

        // Get the highlight word from the suggestion
        let wordToHighlight = "";
        if (options.highlightResult) {
          try {
            const matchedLine =
              suggestion.text || suggestion.subcategory || suggestion.title;
            const matchedWordResult = matchedLine.match(
              new RegExp("<span.+span>\\w*", "g")
            );

            if (matchedWordResult && matchedWordResult.length > 0) {
              const tempDoc = document.createElement("div");
              tempDoc.innerHTML = matchedWordResult[0];
              wordToHighlight = tempDoc.textContent;
            }
          } catch (e) {
            console.log(e);
          }
        }

        history.push(url, {
          highlightState: { wordToHighlight },
        });
      },
    });
  };

  const pluginData = usePluginData("docusaurus-lunr-search");

  const getSearchDoc = () =>
    process.env.NODE_ENV === "production"
      ? fetch(`${assetUrl}${pluginData.fileNames.searchDoc}`).then((res) =>
          res.json()
        )
      : Promise.resolve({});

  const getLunrIndex = () =>
    process.env.NODE_ENV === "production"
      ? fetch(`${assetUrl}${pluginData.fileNames.lunrIndex}`).then((res) =>
          res.json()
        )
      : Promise.resolve({});

  const loadAlgolia = () => {
    if (!initialized.current) {
      Promise.all([
        getSearchDoc(),
        getLunrIndex(),
        import("./DocSearch"),
        import("./algolia.css"),
      ]).then(([searchDocFile, searchIndex, { default: DocSearch }]) => {
        const { searchDocs, options } = searchDocFile;
        if (!searchDocs || searchDocs.length === 0) {
          return;
        }
        initAlgolia(searchDocs, searchIndex, DocSearch, options);
        setIndexReady(true);
      });
      initialized.current = true;
    }
  };

  const toggleSearchIconClick = useCallback(
    (e) => {
      if (!searchBarRef.current.contains(e.target)) {
        searchBarRef.current.focus();
      }
      props.handleSearchBarToggle &&
        props.handleSearchBarToggle(!props.isSearchBarExpanded);
    },
    [props.isSearchBarExpanded]
  );

  let placeholder;
  if (isBrowser) {
    loadAlgolia();
    placeholder = window.navigator.platform.includes("Mac")
      ? "Buscar (⌘ + K)"
      : "Buscar (Ctrl + K)";
  }

  return (
    <div className="navbar_search" key="search-box">
      <span
        role="button"
        className={clsx("search-icon")}
        onClick={toggleSearchIconClick}
        onKeyDown={toggleSearchIconClick}
        onFocus={toggleSearchIconClick}
        tabIndex={0}
        onBlur={toggleSearchIconClick}
      />

      <input
        id="search-input_react"
        type="search"
        placeholder={indexReady ? placeholder : "Carregando..."}
        className={clsx(
          "navbar__search-input",
          { "search-bar-expanded": props.isSearchBarExpanded },
          { "search-bar": !props.isSearchBarExpanded }
        )}
        onClick={loadAlgolia}
        onMouseOver={loadAlgolia}
        onBlur={loadAlgolia}
        ref={searchBarRef}
        onFocus={toggleSearchIconClick}
        disabled={!indexReady}
      />
      <HighlightSearchResults />
    </div>
  );
};

export default Search;
