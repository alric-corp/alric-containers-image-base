import Mark from "mark.js";
import { useEffect, useState } from "react";
import { useLocation, useHistory } from "@docusaurus/router";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";

export function HighlightSearchResults() {
  const location = useLocation();
  const history = useHistory();
  const {
    siteConfig: { baseUrl },
  } = useDocusaurusContext();

  const [highlightData, setHighlightData] = useState({
    wordToHighlight: '',
    isTitleSuggestion: false,
    titleText: ''
  });

  useEffect(() => {
    const word = location.state?.highlightState?.wordToHighlight;
    if (!word || word.length === 0) {
      return;
    }

    setHighlightData(location.state.highlightState);

    const { highlightState, ...state } = location.state || {};
    history.replace({ 
      ...location,
      state,
    });
  }, [location.state, history, location]);

  useEffect(() => {
    if (!highlightData.wordToHighlight || highlightData.wordToHighlight.length === 0) {
      return;
    }

    const root =
      document.getElementsByTagName("article")[0] || document.getElementsByTagName("main")[0];
    if (!root) {
      return;
    }

    const mark = new Mark(root);
    const options = {
      ignoreJoiners: true,
    };
    mark.mark([highlightData.wordToHighlight], options);


    return () => mark.unmark(options);
  }, [highlightData]);

  return null;
}
