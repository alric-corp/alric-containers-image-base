import React from "react";
import clsx from "clsx";
import './index.css';
import { useHistory } from "@docusaurus/router";

export default function PaginatorNavLink(props) {
  const { permalink, title, subLabel, isNext } = props;
  const ariaLabel = isNext ? 'Ir para próxima página' : 'Ir para página anterior';
  const history = useHistory();

  const navigateToPage = () => {
    history.push(permalink);
  };

  return (
    <button
      aria-label={ariaLabel + ' ' + title}
      type="button"
      onClick={navigateToPage}
      className={clsx(
        'botoes-rodape',
        'paginator-nav-link',
        isNext ? 'pagination-nav__link--next' : 'pagination-nav__link--prev'
      )}
    >
      {subLabel && <p className='paginator-nav-link__sub-label'>{subLabel}</p>}
      {title}
    </button>
  );
}
