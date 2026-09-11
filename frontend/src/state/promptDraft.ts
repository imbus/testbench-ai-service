import { emptyMessage, emptyVariant } from '../api/prompts'
import type { MessageRole, PromptDocument, PromptVarDecl, PromptVariantDoc } from '../api/types'

export type PromptDraftAction =
  | { type: 'setHeader'; field: 'name' | 'summary' | 'description' | 'default_model' | 'default_variant'; value: string }
  | { type: 'addVariant'; name: string }
  | { type: 'renameVariant'; from: string; to: string }
  | { type: 'removeVariant'; name: string }
  | { type: 'setVariantModel'; variant: string; model: string | null }
  | { type: 'addVar'; variant: string; key: string }
  | { type: 'editVar'; variant: string; key: string; decl: PromptVarDecl }
  | { type: 'removeVar'; variant: string; key: string }
  | { type: 'addMessage'; variant: string }
  | { type: 'removeMessage'; variant: string; index: number }
  | { type: 'moveMessage'; variant: string; index: number; to: number }
  | { type: 'setMessageRole'; variant: string; index: number; role: MessageRole }
  | { type: 'setMessageContent'; variant: string; index: number; content: string }
  | { type: 'reset'; document: PromptDocument }

function mapVariant(
  doc: PromptDocument,
  name: string,
  change: (variant: PromptVariantDoc) => PromptVariantDoc,
): PromptDocument {
  return {
    ...doc,
    variants: doc.variants.map((variant) => (variant.name === name ? change(variant) : variant)),
  }
}

export function promptDraftReducer(
  state: PromptDocument,
  action: PromptDraftAction,
): PromptDocument {
  switch (action.type) {
    case 'reset':
      return action.document

    case 'setHeader':
      return { ...state, [action.field]: action.value }

    case 'addVariant':
      return { ...state, variants: [...state.variants, emptyVariant(action.name)] }

    case 'renameVariant': {
      const renamed = mapVariant(state, action.from, (v) => ({ ...v, name: action.to }))
      // A rename that left default_variant behind would fail validation on save.
      return state.default_variant === action.from
        ? { ...renamed, default_variant: action.to }
        : renamed
    }

    case 'removeVariant': {
      // PromptDefinition requires at least one variant.
      if (state.variants.length <= 1) return state
      const variants = state.variants.filter((v) => v.name !== action.name)
      const defaultGone = state.default_variant === action.name
      return {
        ...state,
        variants,
        default_variant: defaultGone ? variants[0].name : state.default_variant,
      }
    }

    case 'setVariantModel':
      return mapVariant(state, action.variant, (v) => ({ ...v, model: action.model }))

    case 'addVar':
      return mapVariant(state, action.variant, (v) => ({
        ...v,
        vars: {
          ...v.vars,
          [action.key]: {
            name: action.key,
            description: null,
            value_type: 'string',
            choices: null,
            default_value: null,
            required: false,
          },
        },
      }))

    case 'editVar':
      return mapVariant(state, action.variant, (v) => ({
        ...v,
        vars: {
          ...v.vars,
          // PromptVariableDefinition refuses `choices` on any non-enum type, so
          // the reducer clears them rather than letting the save 422.
          [action.key]:
            action.decl.value_type === 'enum'
              ? action.decl
              : { ...action.decl, choices: null },
        },
      }))

    case 'removeVar':
      return mapVariant(state, action.variant, (v) => {
        const vars = { ...v.vars }
        delete vars[action.key]
        return { ...v, vars }
      })

    case 'addMessage':
      return mapVariant(state, action.variant, (v) => ({
        ...v,
        messages: [...v.messages, emptyMessage()],
      }))

    case 'removeMessage':
      return mapVariant(state, action.variant, (v) =>
        // PromptVariant requires at least one message.
        v.messages.length <= 1
          ? v
          : { ...v, messages: v.messages.filter((_, i) => i !== action.index) },
      )

    case 'moveMessage':
      return mapVariant(state, action.variant, (v) => {
        if (action.to < 0 || action.to >= v.messages.length) return v
        const messages = [...v.messages]
        const [moved] = messages.splice(action.index, 1)
        messages.splice(action.to, 0, moved)
        return { ...v, messages }
      })

    case 'setMessageRole':
      return mapVariant(state, action.variant, (v) => ({
        ...v,
        messages: v.messages.map((m, i) => (i === action.index ? { ...m, role: action.role } : m)),
      }))

    case 'setMessageContent':
      return mapVariant(state, action.variant, (v) => ({
        ...v,
        messages: v.messages.map((m, i) =>
          i === action.index ? { ...m, content: action.content } : m,
        ),
      }))

    default:
      return state
  }
}

/** Everything except the file-backed message bodies -- i.e. what the YAML holds. */
function yamlShape(doc: PromptDocument): string {
  return JSON.stringify({
    name: doc.name,
    summary: doc.summary,
    description: doc.description,
    default_model: doc.default_model,
    default_variant: doc.default_variant,
    variants: doc.variants.map((v) => ({
      name: v.name,
      description: v.description,
      model: v.model,
      vars: v.vars,
      messages: v.messages.map((m) => ({
        role: m.role,
        source: m.source,
        file: m.file,
        // An inline body lives in the YAML; a file body does not.
        text: m.source === 'inline' ? m.content : null,
      })),
    })),
  })
}

export function isDirty(original: PromptDocument, draft: PromptDocument): boolean {
  return changedFiles(original, draft).length > 0
}

/**
 * Which files a save would write, as the confirm dialog lists them.
 *
 * The YAML is named when anything outside a file-backed body changed; each
 * template is named only when its own body did.
 */
export function changedFiles(original: PromptDocument, draft: PromptDocument): string[] {
  const files: string[] = []
  if (yamlShape(original) !== yamlShape(draft)) files.push(draft.file)

  const before = new Map<string, string>()
  for (const variant of original.variants) {
    for (const message of variant.messages) {
      if (message.source === 'file' && message.file) before.set(message.file, message.content)
    }
  }
  for (const variant of draft.variants) {
    for (const message of variant.messages) {
      if (message.source !== 'file' || !message.file) continue
      if (before.get(message.file) !== message.content && !files.includes(message.file)) {
        files.push(message.file)
      }
    }
  }
  return files
}
