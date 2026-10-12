import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { PaneResizer } from './PaneResizer'

// jsdom has no PointerEvent: without one, fireEvent builds a bare Event and
// drops button / clientY. MouseEvent carries both.
beforeAll(() => {
  if (!('PointerEvent' in window)) {
    Object.defineProperty(window, 'PointerEvent', { value: MouseEvent, configurable: true })
  }
})

function setup(height = 230, max = 500) {
  const onResize = vi.fn()
  render(<PaneResizer height={height} min={120} max={() => max} label="Resize" onResize={onResize} />)
  return { handle: screen.getByRole('separator', { name: 'Resize' }), onResize }
}

describe('PaneResizer', () => {
  it('grows the pane when dragged up and clamps to max', () => {
    const { handle, onResize } = setup()
    handle.setPointerCapture = vi.fn()
    handle.hasPointerCapture = vi.fn(() => true)
    handle.releasePointerCapture = vi.fn()
    fireEvent.pointerDown(handle, { button: 0, clientY: 400, pointerId: 1 })
    fireEvent.pointerMove(handle, { clientY: 300, pointerId: 1 })
    expect(onResize).toHaveBeenLastCalledWith(330)
    fireEvent.pointerMove(handle, { clientY: 0, pointerId: 1 })
    expect(onResize).toHaveBeenLastCalledWith(500)
    fireEvent.pointerUp(handle, { pointerId: 1 })
    onResize.mockClear()
    fireEvent.pointerMove(handle, { clientY: 100, pointerId: 1 })
    expect(onResize).not.toHaveBeenCalled()
  })

  it('shrinks no further than min', () => {
    const { handle, onResize } = setup()
    handle.setPointerCapture = vi.fn()
    fireEvent.pointerDown(handle, { button: 0, clientY: 400, pointerId: 1 })
    fireEvent.pointerMove(handle, { clientY: 900, pointerId: 1 })
    expect(onResize).toHaveBeenLastCalledWith(120)
  })

  it('resizes with the arrow keys', () => {
    const { handle, onResize } = setup()
    fireEvent.keyDown(handle, { key: 'ArrowUp' })
    expect(onResize).toHaveBeenLastCalledWith(246)
    fireEvent.keyDown(handle, { key: 'ArrowDown' })
    expect(onResize).toHaveBeenLastCalledWith(214)
  })
})
