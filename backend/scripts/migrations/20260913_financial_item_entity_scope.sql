ALTER TABLE financial_items
    ADD COLUMN IF NOT EXISTS entity_scope TEXT NOT NULL DEFAULT 'unknown';

UPDATE financial_items AS item
SET entity_scope = CASE
    WHEN concat_ws(
        ' ',
        source.title,
        source.metadata ->> 'source_section_title',
        source.metadata ->> 'nearby_context'
    ) ~* '(母公司|parent company|standalone)'
        THEN 'parent_company'
    WHEN concat_ws(
        ' ',
        source.title,
        source.metadata ->> 'source_section_title',
        source.metadata ->> 'nearby_context'
    ) ~* '(合并|consolidated|group statement)'
        THEN 'consolidated'
    ELSE 'unknown'
END
FROM parsed_tables AS source
WHERE item.doc_id = source.doc_id
  AND item.source_table_id = source.table_id
  AND item.fact_type = 'metric';

CREATE INDEX IF NOT EXISTS ix_financial_items_entity_scope
    ON financial_items (entity_scope);
