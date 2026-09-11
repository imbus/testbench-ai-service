import '@testing-library/jest-dom/vitest'

// jsdom's `AbortController`/`AbortSignal` do not satisfy Node's built-in
// `Request`'s webidl brand check on `signal` -- a known jsdom/undici
// interop gap (reproduces with nothing but `new Request(url, { signal: new
// AbortController().signal })` in this exact test environment). react-router
// v6.4+'s data router (`createBrowserRouter`/`createMemoryRouter` +
// `RouterProvider`, needed for `useBlocker`) constructs one internally on
// EVERY navigation, loader or not, so any test driving a real navigation
// through one throws `RequestInit: Expected signal ... to be an instance of
// AbortSignal` before this screen's own code ever runs. Retrying without the
// (jsdom-originated, cross-realm) signal is harmless here: nothing in this
// app's tests depends on that internal Request object's abort behavior --
// only on the navigation state (`useBlocker`, `useParams`, ...) it drives.
const NativeRequest = globalThis.Request
if (NativeRequest) {
  function PatchedRequest(input: RequestInfo | URL, init?: RequestInit) {
    try {
      return new NativeRequest(input, init)
    } catch (err) {
      if (init && 'signal' in init && err instanceof TypeError) {
        const { signal: _signal, ...rest } = init
        return new NativeRequest(input, rest)
      }
      throw err
    }
  }
  globalThis.Request = PatchedRequest as unknown as typeof Request
}
