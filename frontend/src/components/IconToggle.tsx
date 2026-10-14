import type { ReactNode } from 'react'
import { SelectButton, type SelectButtonPassThroughMethodOptions } from 'primereact/selectbutton'

export type IconToggleOption<T extends string> = { label: string; value: T; icon: ReactNode }

/**
 * An either/or switch drawn as icons: a PrimeReact `SelectButton` whose
 * options render only their glyph. Prime already puts each option's label on
 * its button as `aria-label`; the same label goes into `title` so a sighted
 * user gets it on hover.
 */
export function IconToggle<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: T
  options: IconToggleOption<T>[]
  onChange: (value: T) => void
  ariaLabel?: string
}) {
  return (
    <SelectButton
      aria-label={ariaLabel}
      value={value}
      allowEmpty={false}
      options={options}
      itemTemplate={(option: IconToggleOption<T>) => option.icon}
      onChange={(event) => {
        if (event.value) onChange(event.value as T)
      }}
      pt={{
        button: ({ context }: SelectButtonPassThroughMethodOptions) => ({
          title: (context.option as IconToggleOption<T>).label,
          style: { padding: '6px 9px', display: 'inline-flex', alignItems: 'center' },
        }),
      }}
    />
  )
}

/** Glyph props shared by the toggle icons, matching NavRail's line icons. */
const GLYPH = {
  width: 16,
  height: 16,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round',
  'aria-hidden': true,
} as const

export const ListIcon = (
  <svg {...GLYPH}>
    <path d="M9 6h11M9 12h11M9 18h11" />
    <circle cx="4.5" cy="6" r="1" />
    <circle cx="4.5" cy="12" r="1" />
    <circle cx="4.5" cy="18" r="1" />
  </svg>
)

export const MatrixIcon = (
  <svg {...GLYPH}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M3 9h18M3 15h18M9 3v18M15 3v18" />
  </svg>
)

export const SplitIcon = (
  <svg {...GLYPH}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M9 4v16M15 4v16" />
  </svg>
)

export const TabsIcon = (
  <svg {...GLYPH}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M3 9h18M9 4v5M15 4v5" />
  </svg>
)
