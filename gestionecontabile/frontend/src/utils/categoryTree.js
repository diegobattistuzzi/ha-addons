// Ordina le categorie in un albero a 2 livelli (padre poi le sue sotto-categorie,
// entrambi alfabetici) invece dell'ordine di arrivo/sort_order: usato ovunque le
// categorie vengano elencate all'utente (picker, filtri, pagina Categorie) cosi'
// la gerarchia scelta in Impostazioni > Categorie sia sempre visibile, non solo
// li'. Una categoria il cui genitore non e' (piu') nell'elenco fornito (es.
// disattivato o filtrato per un altro tipo) e' trattata come radice, altrimenti
// sparirebbe del tutto dall'elenco.
export function sortCategoriesAsTree(categories) {
  const idsInScope = new Set(categories.map(c => c.id))
  const isRoot = c => !c.parent_id || !idsInScope.has(c.parent_id)
  const sortAlpha = list => [...list].sort((a, b) => a.name.localeCompare(b.name, 'it'))
  const result = []
  for (const root of sortAlpha(categories.filter(isRoot))) {
    result.push({ ...root, depth: 0 })
    for (const child of sortAlpha(categories.filter(c => c.parent_id === root.id && !isRoot(c)))) {
      result.push({ ...child, depth: 1 })
    }
  }
  return result
}
