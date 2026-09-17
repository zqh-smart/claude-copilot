type CitationHandler = (id: string) => void

let citationHandler: CitationHandler | null = null

export function setCitationClickHandler(handler: CitationHandler | null) {
  citationHandler = handler
}

export function emitCitationClick(id: string) {
  citationHandler?.(id)
}
