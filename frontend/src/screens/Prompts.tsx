import { Link } from 'react-router-dom'
import { usePromptTree } from '../api/queries'
import { useTranslations, type Lang } from '../i18n'

/**
 * The prompt tree (design §5.6): every prompt file the server found, grouped
 * by language, with each agent linking to its editor.
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

  return (
    <div style={{ padding: '28px 32px', display: 'flex', flexDirection: 'column', gap: 24 }}>
      <h2 style={{ margin: 0, fontSize: 30 }}>{t.prompts}</h2>

      {languages.length === 0 ? (
        <div className="text-muted" style={{ fontSize: 13 }}>
          {t.noPromptTree}
        </div>
      ) : (
        languages.map((language) => (
          <section key={language.lang} data-testid={`prompt-lang-${language.lang}`}>
            <h3
              style={{
                margin: '0 0 8px',
                fontSize: 13,
                fontFamily: 'ui-monospace, Menlo, monospace',
                letterSpacing: '.08em',
                textTransform: 'uppercase',
              }}
            >
              {language.lang}
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {language.prompts.map((prompt) => (
                <div
                  key={prompt.agent}
                  data-testid={`prompt-agent-${language.lang}-${prompt.agent}`}
                  className="tb-row"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '6px 10px',
                    borderBottom: '1px solid var(--color-divider)',
                  }}
                >
                  {/* A broken prompt still links to its editor: an operator
                      who cannot open it cannot fix it either. */}
                  <Link
                    to={`/prompts/${encodeURIComponent(language.lang)}/${encodeURIComponent(prompt.agent)}`}
                  >
                    {prompt.name ?? prompt.agent}
                  </Link>
                  <span
                    className="text-muted"
                    style={{ fontSize: 11, fontFamily: 'ui-monospace, Menlo, monospace' }}
                  >
                    {prompt.agent}
                  </span>
                  {!prompt.ok && (
                    <span
                      className="tag tag-accent"
                      style={{ fontSize: 11, padding: '1px 6px', color: '#a33a2b' }}
                    >
                      {prompt.error}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  )
}
