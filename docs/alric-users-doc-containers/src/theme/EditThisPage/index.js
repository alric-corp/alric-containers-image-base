import React from "react";
import { ThemeClassNames } from "@docusaurus/theme-common";
import IconEdit from "@theme/Icon/Edit";
import "./index.css";

export default function EditThisPage({ editUrl }) {
  return (
    <div className="botoes-rodape">
      <button
        onClick={(e) => {
          e.preventDefault();
          window.location.href = editUrl;
        }}
        className={ThemeClassNames.common.editThisPage}
        type="button"
      >
        <IconEdit /> Editar esta página
      </button>
    </div>
  );
}
