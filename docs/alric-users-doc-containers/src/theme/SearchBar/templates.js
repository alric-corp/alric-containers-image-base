const prefix = 'algolia-docsearch';
const suggestionPrefix = `${prefix}-suggestion`;
const footerPrefix = `${prefix}-footer`;

const templates = {
  suggestion: `
  <a class="${suggestionPrefix}
   {{#isCategoryHeader}} ${suggestionPrefix}__main {{/isCategoryHeader}}
   {{#isSubCategoryHeader}} ${suggestionPrefix}__secondary {{/isSubCategoryHeader}}"
   aria-label="{{{_highlightResult.title.value}}}"
   href="{{{url}}}"
  >
    <div class="${suggestionPrefix}--category-header">
      <span class="${suggestionPrefix}--category-header-lv10">{{{category}}}</span>
    </div>
    <div class="${suggestionPrefix}--wrapper">
      <div class="${suggestionPrefix}--subcategory-column">
        <span class="${suggestionPrefix}--subcategory-column-text">{{{subcategory}}}</span>
      </div>
      {{#isTextOrSubcategoryNonEmpty}}
      <div class="${suggestionPrefix}--content">
        <div class="${suggestionPrefix}--subcategory-inline">{{{subcategory}}}</div>
        <div class="${suggestionPrefix}--title">{{{title}}}</div>
        {{#text}}<div class="${suggestionPrefix}--text">{{{text}}}</div>{{/text}}
        {{#version}}<div class="${suggestionPrefix}--version">{{{version}}}</div>{{/version}}
      </div>
      {{/isTextOrSubcategoryNonEmpty}}
    </div>
  </a>`,

  suggestionSimple: `
  <div class="${suggestionPrefix}
    {{#isCategoryHeader}} ${suggestionPrefix}__main {{/isCategoryHeader}}
    {{#isSubCategoryHeader}} ${suggestionPrefix}__secondary {{/isSubCategoryHeader}}">
    
    <div class="${suggestionPrefix}--category-header">
      {{^isLv10}}
        <span class="${suggestionPrefix}--category-header-lv10 ${suggestionPrefix}--category-header-item">{{{category}}}</span>
        {{^isLv11}}
          {{^isLv11EmptyOrDuplicate}}
            <span class="${suggestionPrefix}--category-header-lv11 ${suggestionPrefix}--category-header-item">
              {{{subcategory}}}
            </span>
          {{/isLv11EmptyOrDuplicate}}
        {{/isLv11}}
      {{/isLv10}}

      <div class="${suggestionPrefix}--title ${suggestionPrefix}--category-header-item">
        {{#isLv12}} {{{title}}} {{/isLv12}}
        {{#isLv11}} {{{subcategory}}} {{/isLv11}}
        {{#isLv10}} {{{subcategory}}} {{/isLv10}}
      </div>
    </div>
  </div>`,

  empty: `
  <div class="${suggestionPrefix}">
    <div class="${suggestionPrefix}--wrapper">
      <div class="${suggestionPrefix}--content ${suggestionPrefix}--no-results">
       <div class="${suggestionPrefix}--title">
         <div class="${suggestionPrefix}--text">
           Nenhum resultado encontrado para sua busca. <b>"{{query}}</b>".
         </div>
       </div>
    </div>
  </div>`,

  searchBox: `
  <form novalidate="novalidate" onsubmit="return false;" class="searchbox">
   <div role="search" class="searchbox_wrapper">
     <input id="docsearch" type="search" placeholder="Pesquisar nas documentações" autoComplete="off" aria-hidden="true"  />
   </div>
  </form>`,

  footer: `
  <div class="${footerPrefix}">
  </div>`
};

export default templates;
