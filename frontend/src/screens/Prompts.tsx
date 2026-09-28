import { Link } from 'react-router-dom'
import { usePromptTree } from '../api/queries'
import type { PromptTreeEntry, PromptTreeLanguage, PromptUsage } from '../api/types'
import { useTranslations, type Lang } from '../i18n'

/** A mono line that clips to its track. File paths have no break points, so
 *  without this they run on under the next column. */
const MONO_CELL = {
  fontSize: 11,
  fontFamily: 'ui-monospace, Menlo, monospace',
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
} as const

/** One agent across every language the server found a prompt file for. */
type PromptRow = { agent: string; byLang: Map<string, PromptTreeEntry> }

/**
 * Pivots the per-language tree into one row per agent, in the order the
 * agents first appear. The same agent usually exists in every language, and
 * listing it once per language section is what left the old screen mostly
 * empty width.
 */
function pivot(languages: PromptTreeLanguage[]): PromptRow[] {
  const rows = new Map<string, PromptRow>()
  for (const language of languages) {
    for (const prompt of language.prompts ?? []) {
      let row = rows.get(prompt.agent)
      if (!row) {
        row = { agent: prompt.agent, byLang: new Map() }
        rows.set(prompt.agent, row)
      }
      row.byLang.set(language.lang, prompt)
    }
  }
  return [...rows.values()]
}

/** Every usage of the row's files, deduplicated across languages: a config
 *  reference resolves to the same file name in each language directory. */
function usagesOf(row: PromptRow): PromptUsage[] {
  const seen = new Map<string, PromptUsage>()
  for (const entry of row.byLang.values()) {
    for (const usage of entry.used_by ?? []) {
      seen.set(`${usage.agent}\u0000${usage.project ?? ''}`, usage)
    }
  }
  return [...seen.values()]
}

/**
 * The prompt tree (design §5.6): one row per agent, one column per language,
 * each cell linking to that language's editor.
 */
export function Prompts({ lang = 'de' }: { lang?: Lang }) {
  const t = useTranslations(lang)
  const tree = usePromptTree()

  if (tree.isLoading) return <div style={{ padding: 28 }}>…</div>
  if (tree.isError) {
    const detail = (tree.error as Error)?.message
    return (
      <div role="alert" style={{ padding: 28 }}>
        <div>{t.promptsError}</div>
        {detail && (
          <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
            {detail}
          </div>
        )}
      </div>
    )
  }

  // Defaults the FIELD, not the container: `tree.data` can be a truthy `{}`
  // (a 200 whose body is missing `languages`), and `tree.data ?? {...}` would
  // never fire in that case. The same guard phase 3 added to Agents and
  // Projects, after both crashed on a payload missing a field -- an operator
  // who cannot load this screen cannot fix the underlying prompt file either.
  const languages = tree.data?.languages ?? []
  const langs = languages.map((language) => language.lang)
  const rows = pivot(languages)
  // The header strip and every row share one track, or the columns stop
  // lining up.
  const gridColumns = [
    'minmax(0, 1.2fr)',
    ...langs.map(() => 'minmax(0, 1fr)'),
    'minmax(0, 0.8fr)',
  ].join(' ')

  return (
    <div style={{ padding: '28px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 30 }}>{t.prompts}</h2>
        {rows.length > 0 && (
          <div
            className="text-muted"
            style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
          >
            {t.agents}: {rows.length} · {langs.join(' · ')}
          </div>
        )}
      </div>

      {rows.length === 0 ? (
        <div className="text-muted" style={{ fontSize: 13 }}>
          {t.noPromptTree}
        </div>
      ) : (
        <div className="blueprint" style={{ overflowX: 'auto' }}>
          <i className="corner tl" />
          <i className="corner tr" />
          <i className="corner bl" />
          <i className="corner br" />
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: gridColumns,
              gap: 16,
              padding: '8px 14px',
              borderBottom: '1px solid var(--color-divider)',
              fontSize: 11,
              letterSpacing: '.08em',
              textTransform: 'uppercase',
              color: 'color-mix(in srgb, var(--color-text) 60%, transparent)',
            }}
          >
            <span>Agent</span>
            {langs.map((code) => (
              <span key={code} data-testid={`prompt-lang-${code}`}>
                {code}
              </span>
            ))}
            <span>{t.promptsUsedBy}</span>
          </div>
          {rows.map((row) => (
            <PromptRowView
              key={row.agent}
              row={row}
              langs={langs}
              gridColumns={gridColumns}
              lang={lang}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function PromptRowView({
  row,
  langs,
  gridColumns,
  lang,
}: {
  row: PromptRow
  langs: string[]
  gridColumns: string
  lang: Lang
}) {
  const t = useTranslations(lang)
  // The console's own language names the row when that file has a name;
  // otherwise any language that does, and the bare key as a last resort.
  const title =
    row.byLang.get(lang)?.name ??
    [...row.byLang.values()].find((entry) => entry.name)?.name ??
    row.agent
  const usages = usagesOf(row)

  return (
    <div
      data-testid={`prompt-row-${row.agent}`}
      className="tb-row"
      style={{
        display: 'grid',
        gridTemplateColumns: gridColumns,
        gap: 16,
        alignItems: 'start',
        padding: '10px 14px',
        borderBottom: '1px solid var(--color-divider)',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600 }}>{title}</div>
        <div className="text-muted" style={MONO_CELL}>
          {row.agent}
        </div>
      </div>

      {langs.map((code) => {
        const entry = row.byLang.get(code)
        if (!entry) {
          return (
            <div key={code} className="text-muted" style={{ fontSize: 12 }}>
              — {t.promptsMissing}
            </div>
          )
        }
        return (
          <div
            key={code}
            data-testid={`prompt-agent-${code}-${row.agent}`}
            style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4 }}
          >
            {/* A broken prompt is still listed, with its file and the parse
                error beside it, so the operator knows which file to repair on
                disk. The link goes to the editor like any other cell, but the
                editor cannot OPEN an unparseable prompt -- the document
                endpoint 422s and the screen shows that error, which is why the
                tree carries the reason here rather than only behind the link. */}
            <Link
              to={`/admin/prompts/${encodeURIComponent(code)}/${encodeURIComponent(entry.agent)}`}
              style={MONO_CELL}
              title={entry.file}
            >
              {/* The column header already names the language, so its
                  directory prefix is noise here; the tooltip keeps it. */}
              {entry.file.startsWith(`${code}/`) ? entry.file.slice(code.length + 1) : entry.file}
            </Link>
            {entry.ok ? (
              entry.variants.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {entry.variants.map((variant) => (
                    <span
                      key={variant}
                      className="tag tag-neutral"
                      style={{ fontSize: 11, padding: '1px 6px' }}
                    >
                      {variant}
                    </span>
                  ))}
                </div>
              )
            ) : (
              <span
                className="tag tag-accent"
                style={{ fontSize: 11, padding: '1px 6px', color: '#a33a2b', alignSelf: 'start' }}
              >
                {entry.error}
              </span>
            )}
          </div>
        )
      })}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, minWidth: 0 }}>
        {usages.length === 0 ? (
          <span className="text-muted" style={{ fontSize: 12 }}>
            {t.promptsUnused}
          </span>
        ) : (
          usages.map((usage) => {
            const scope = usage.project ?? t.globalScope
            // A fork is referenced by another agent's config; name that agent
            // so the tag says who actually runs this file.
            const label = usage.agent === row.agent ? scope : `${usage.agent} · ${scope}`
            return (
              <span
                key={`${usage.agent}-${usage.project ?? ''}`}
                className="tag tag-outline"
                style={{ fontSize: 11, padding: '1px 6px' }}
              >
                {label}
              </span>
            )
          })
        )}
      </div>
    </div>
  )
}
