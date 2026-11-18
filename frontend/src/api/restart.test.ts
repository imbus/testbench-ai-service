import { describe, expect, it } from 'vitest'
import { movedTo } from './restart'

function at(url: string): Location {
  return new URL(url) as unknown as Location
}

const SAME = { host: '127.0.0.1', port: 8010, tls: false, in_flight_tasks: 0 }

describe('movedTo', () => {
  it('is null when the address stays', () => {
    expect(movedTo(SAME, at('http://127.0.0.1:8010/admin/status'))).toBeNull()
  })

  it('treats the loopback names as one host', () => {
    expect(movedTo(SAME, at('http://localhost:8010/admin/'))).toBeNull()
  })

  it('keeps the browser host name for a wildcard bind', () => {
    expect(
      movedTo({ ...SAME, host: '0.0.0.0', port: 9000 }, at('http://srv.example:8010/admin/')),
    ).toBe('http://srv.example:9000/admin/')
  })

  it('names the new scheme when TLS is switched on', () => {
    expect(movedTo({ ...SAME, tls: true }, at('http://127.0.0.1:8010/admin/'))).toBe(
      'https://127.0.0.1:8010/admin/',
    )
  })

  it('reads a missing port as the scheme default', () => {
    expect(
      movedTo({ ...SAME, host: 'srv', port: 443, tls: true }, at('https://srv/admin/')),
    ).toBeNull()
  })
})
