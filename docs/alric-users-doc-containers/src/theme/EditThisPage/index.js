import React from "react";
import Link from "@docusaurus/Link";
import { ThemeClassNames } from "@docusaurus/theme-common";
import IconEdit from "@theme/Icon/Edit";
import "./index.css";

export default function EditThisPage({ editUrl }) {
  return (
    <div className="botoes-rodape">
      <Link to={editUrl} className={ThemeClassNames.common.editThisPage}>
        <IconEdit /> Editar esta página
      </Link>
    </div>
  );
}
