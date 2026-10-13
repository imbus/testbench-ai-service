import 'i18next'
import type { de } from './de'

// Types `t` against the German dictionary: an unknown key or a missing
// `{{placeholder}}` value fails the build, as `t.someKey` did before.
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation'
    resources: { translation: typeof de }
  }
}
