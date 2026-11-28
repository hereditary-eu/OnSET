// Where the ontology editor (OntologyEditor) draws the classes of an ontology, also used by the
// miniatures of its history (OntologyHistoryElement).
import type { OntoClass, Ontology } from './api'

export const CARD_W = 190
// must match the card CSS of OntologyEditor (header, rows, padding)
export const HEADER_H = 24
export const ROW_H = 18
export const PAD = 4

/** Position of the ``i``-th class without a position (e.g. added by the agent): on a grid. */
export const gridPos = (i: number) => ({ x: 20 + (i % 3) * (CARD_W + 120), y: 60 + Math.floor(i / 3) * 170 })

export const classPos = (ontology: Ontology, cls: OntoClass) => cls.x != null && cls.y != null
    ? { x: cls.x, y: cls.y } : gridPos(ontology.classes.indexOf(cls))

/** The card of a class: its position and size. */
export const classRect = (ontology: Ontology, cls: OntoClass) =>
    ({ ...classPos(ontology, cls), w: CARD_W, h: HEADER_H + Math.max(1, cls.fields.length) * ROW_H + PAD })
