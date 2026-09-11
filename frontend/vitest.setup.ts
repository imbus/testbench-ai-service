import '@testing-library/jest-dom/vitest'

// jsdom's `AbortController`/`AbortSignal` do not satisfy Node's built-in
// `Request`'s webidl brand check on `signal` -- a known jsdom/undici
// interop gap (reproduces with nothing but `new Request(url, { signal: new
// AbortController().signal })` in this exact test environment). react-router
// v6.4+'s data router (`createBrowserRouter`/`createMemoryRouter` +
// `RouterProvider`, needed for `useBlocker`) constructs one internally on
// EVERY navigation, loader or not, so any test driving a real navigation
// through one throws `RequestInit: Expected signal ... to be an instance of
// AbortSignal` before this screen's own code ever runs.
//
// This shim retries ONLY that exact failure (matched on the native error's
// own message, not merely its `TypeError` type -- a `TypeError` from some
// other malformed `init` must still fail loudly, not be silently swallowed
// as if it were this specific signal incompatibility). On a match, it drops
// the incompatible signal and constructs a real, fully-native `Request`
// instance -- `PatchedRequest.prototype = NativeRequest.prototype` keeps
// `instanceof Request` working suite-wide (statics such as `Request.json`,
// if any library starts relying on them, are NOT proxied by this).
//
// What this costs: the retried Request's `signal` never aborts, since the
// incompatible one was simply dropped rather than translated. Safe today
// only because this app declares no route `loader`/`action` (the only things
// that would read that internal Request's `signal`) and `apiFetch` builds its
// own request without going through this path at all.
//
// REMOVE THIS the moment either becomes false: (a) jsdom/undici fix the
// underlying interop gap (recheck by deleting this file's contents down to
// the `jest-dom` import and re-running the suite), or (b) this app adds a
// route `loader`/`action`, or ever wires an `AbortSignal` into `apiFetch` --
// at that point a dropped signal is silent breakage, not a safe elision.
const NativeRequest = globalThis.Request
if (NativeRequest) {
  function PatchedRequest(input: RequestInfo | URL, init?: RequestInit) {
    try {
      return new NativeRequest(input, init)
    } catch (err) {
      const isSignalIncompatibility =
        err instanceof TypeError && /Expected signal .* to be an instance of AbortSignal/.test(err.message)
      if (init && 'signal' in init && isSignalIncompatibility) {
        const { signal: _signal, ...rest } = init
        return new NativeRequest(input, rest)
      }
      throw err
    }
  }
  PatchedRequest.prototype = NativeRequest.prototype
  globalThis.Request = PatchedRequest as unknown as typeof Request
}
