import { Fragment, useState, type CSSProperties } from 'react'
import { SelectButton } from 'primereact/selectbutton'
import { useTranslation } from 'react-i18next'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { COMPONENTS } from '../../components/MarkdownView'

type JsonRecord = Record<string, unknown>
type Mode = 'formatted' | 'json'

/** Nesting deeper than this is shown as JSON, so a report cannot recurse the page away. */
const MAX_DEPTH = 6
/** A string longer than this, or with a line break, is prose and gets its own block. */
const LONG_TEXT = 120

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isLongText = (value: unknown): value is string =>
  typeof value === 'string' && (value.length > LONG_TEXT || value.includes('\n'))

const isShort = (value: unknown) =>
  (value === null || typeof value !== 'object') && !isLongText(value)

/** Fits on one line: a short scalar, a list of them, or nothing at all. */
const isInline = (value: unknown): boolean =>
  isShort(value) ||
  (Array.isArray(value) && value.every(isShort)) ||
  (isRecord(value) && Object.keys(value).length === 0)

/** Nothing to show: a row with only such details gets no way to open them. */
const isEmpty = (value: unknown): boolean =>
  value === undefined ||
  value === null ||
  value === '' ||
  (Array.isArray(value) && value.length === 0) ||
  (isRecord(value) && Object.keys(value).length === 0)

const SNAKE_CASE = /^[a-z][a-z0-9]*(_[a-z0-9]+)+$/
const CAMEL_CASE = /^[a-z]+([A-Z][a-z0-9]+)+$/

/**
 * A field name as a label: `sets_screened` and `setsScreened` read "Sets screened".
 * Anything else is kept, since a key of a map is often an ID like `iTB-TC-1`.
 */
export function humanize(key: string): string {
  let words = key
  if (SNAKE_CASE.test(key)) words = key.replace(/_/g, ' ')
  else if (CAMEL_CASE.test(key)) words = key.replace(/([a-z0-9])([A-Z])/g, '$1 $2').toLowerCase()
  else if (!/^[a-z][a-z0-9]*$/.test(key)) return key
  return words[0].toUpperCase() + words.slice(1)
}

const CELL: CSSProperties = {
  padding: '6px 24px 6px 8px',
  borderBottom: '1px solid var(--color-divider)',
  textAlign: 'left',
  verticalAlign: 'top',
}

function Empty() {
  return <span className="text-muted">—</span>
}

/** A value that fits on one line. */
function Inline({ value }: { value: unknown }) {
  const { t } = useTranslation()
  if (Array.isArray(value)) {
    if (value.length === 0) return <Empty />
    return (
      <>
        {value.map((item, i) => (
          <Fragment key={i}>
            {i > 0 && ', '}
            <Inline value={item} />
          </Fragment>
        ))}
      </>
    )
  }
  if (value === null || value === undefined || value === '' || isRecord(value)) return <Empty />
  if (typeof value === 'boolean') {
    return <>{value ? `✓ ${t('reportYes')}` : `✕ ${t('reportNo')}`}</>
  }
  if (typeof value === 'string' && /^https?:\/\/\S+$/.test(value)) {
    return (
      <a href={value} target="_blank" rel="noopener noreferrer">
        {value}
      </a>
    )
  }
  return <>{String(value)}</>
}

function RawJson({ value }: { value: unknown }) {
  return (
    <pre style={{ margin: 0, overflowX: 'auto', fontFamily: 'var(--font-code)', fontSize: 12 }}>
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

/**
 * The fields of an object: those that fit on one line as a label/value list,
 * the others (prose, lists of objects, nested objects) each under its own heading.
 */
function Fields({ record, depth }: { record: JsonRecord; depth: number }) {
  const entries = Object.entries(record)
  const facts = entries.filter(([, value]) => isInline(value))
  const blocks = entries.filter(([, value]) => !isInline(value))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
      {facts.length > 0 && (
        <dl
          style={{
            display: 'grid',
            gridTemplateColumns: 'max-content minmax(0, 1fr)',
            gap: '4px 16px',
            margin: 0,
          }}
        >
          {facts.map(([key, value]) => (
            <Fragment key={key}>
              <dt className="text-muted">{humanize(key)}</dt>
              <dd style={{ margin: 0, overflowWrap: 'anywhere' }}>
                <Inline value={value} />
              </dd>
            </Fragment>
          ))}
        </dl>
      )}
      {blocks.map(([key, value]) => (
        <section key={key} style={{ minWidth: 0 }}>
          <div className="card-kicker" style={{ marginBottom: 4 }}>
            {humanize(key)}
          </div>
          <Block value={value} depth={depth + 1} />
        </section>
      ))}
    </div>
  )
}

/** Any value, in the form that suits its shape. */
function Block({ value, depth }: { value: unknown; depth: number }) {
  if (depth > MAX_DEPTH) return <RawJson value={value} />
  if (isLongText(value)) {
    // Markdown, never HTML: a report carries TestBench data and model output,
    // which must not become markup (see MarkdownView).
    return (
      <div className="markdown-body">
        <Markdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
          {value}
        </Markdown>
      </div>
    )
  }
  if (isInline(value)) return <Inline value={value} />
  if (Array.isArray(value)) {
    if (value.every(isRecord)) return <Table rows={value} depth={depth} />
    return (
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {value.map((item, i) => (
          <li key={i}>
            <Block value={item} depth={depth + 1} />
          </li>
        ))}
      </ul>
    )
  }
  if (isRecord(value)) {
    return (
      <div style={{ paddingLeft: 12, borderLeft: '2px solid var(--color-divider)' }}>
        <Fields record={value} depth={depth} />
      </div>
    )
  }
  return <Inline value={value} />
}

/**
 * A list of objects as a table. A field is a column when it fits on one line in
 * every row; what does not opens below its row.
 */
function Table({ rows, depth }: { rows: JsonRecord[]; depth: number }) {
  const keys = [...new Set(rows.flatMap((row) => Object.keys(row)))]
  const columns = keys.filter((key) => rows.every((row) => isInline(row[key])))
  const nested = keys.filter((key) => !columns.includes(key))
  if (columns.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {rows.map((row, i) => (
          <div key={i} style={{ paddingLeft: 12, borderLeft: '2px solid var(--color-divider)' }}>
            <Fields record={row} depth={depth + 1} />
          </div>
        ))}
      </div>
    )
  }
  const numeric = new Set(
    columns.filter((key) => rows.every((row) => typeof row[key] === 'number')),
  )
  const align = (key: string): CSSProperties =>
    numeric.has(key) ? { textAlign: 'right', fontVariantNumeric: 'tabular-nums' } : {}
  return (
    <div style={{ overflowX: 'auto' }}>
      {/* As wide as its content, so a short column does not drift away from the next. */}
      <table style={{ borderCollapse: 'collapse', maxWidth: '100%' }}>
        <thead>
          <tr>
            {nested.length > 0 && <th style={{ ...CELL, width: 14 }} />}
            {columns.map((key) => (
              <th
                key={key}
                className="text-muted"
                style={{ ...CELL, fontSize: 12, fontWeight: 600, ...align(key) }}
              >
                {humanize(key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <Row key={i} row={row} columns={columns} nested={nested} align={align} depth={depth} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Row({
  row,
  columns,
  nested,
  align,
  depth,
}: {
  row: JsonRecord
  columns: string[]
  nested: string[]
  align: (key: string) => CSSProperties
  depth: number
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const details = Object.fromEntries(
    nested.filter((key) => !isEmpty(row[key])).map((key) => [key, row[key]]),
  )
  const hasDetails = Object.keys(details).length > 0
  return (
    <>
      <tr>
        {nested.length > 0 && (
          <td style={CELL}>
            {hasDetails && (
              <button
                type="button"
                aria-expanded={open}
                aria-label={t('reportShowDetails')}
                onClick={() => setOpen(!open)}
                className="text-muted"
                style={{ all: 'unset', cursor: 'pointer' }}
              >
                {open ? '▾' : '▸'}
              </button>
            )}
          </td>
        )}
        {columns.map((key) => (
          <td key={key} style={{ ...CELL, overflowWrap: 'anywhere', ...align(key) }}>
            <Inline value={row[key]} />
          </td>
        ))}
      </tr>
      {open && (
        <tr>
          <td colSpan={columns.length + 1} style={{ ...CELL, padding: '8px 8px 12px 30px' }}>
            <Fields record={details} depth={depth + 1} />
          </td>
        </tr>
      )}
    </>
  )
}

/**
 * A report no view was written for, laid out from its shape alone: short values
 * as a label/value list, lists of objects as tables, prose as Markdown, nested
 * objects as sections. The stored JSON stays one click away.
 */
export function GenericReport({ report }: { report: unknown }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<Mode>('formatted')
  return (
    <div
      data-testid="generic-report"
      style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}
    >
      <SelectButton
        aria-label={t('reportViewMode')}
        className="markdown-view-modes"
        value={mode}
        allowEmpty={false}
        options={[
          { label: t('reportViewFormatted'), value: 'formatted' },
          { label: t('reportViewJson'), value: 'json' },
        ]}
        onChange={(event) => {
          if (event.value) setMode(event.value as Mode)
        }}
        pt={{ button: { style: { padding: '2px 8px', fontSize: 11 } } }}
      />
      {mode === 'json' ? (
        <RawJson value={report} />
      ) : isRecord(report) ? (
        <Fields record={report} depth={0} />
      ) : (
        <Block value={report} depth={0} />
      )}
    </div>
  )
}
