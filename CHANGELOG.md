# Changelog

Every published version, newest first. This file is on the publish
allow-list, so it travels with the package: it is the only thing a
consumer deciding whether to upgrade can read.

## 0.0.1 — 2026-09-09

The **interface**, before anyone implements it. Every signature, every
type and every effect row is published; every body is `todo()`, and the
release is stamped `NOT IMPLEMENTED — interface only`. Adding this
package works and calling it panics.

- `H1Request`, `H1Response`, `H1Header`, `H1Headers`, `H1Method`,
  `H1Version` and `H1TargetForm` — an HTTP/1.1 head as values. Named
  `H1…` because `std.http` already owns `HttpRequest`, `HttpResponse`
  and `HttpHeader`, and because `H1` is what the reference
  implementations call this wire format when they have to distinguish
  it from HTTP/2.
- Neither head carries a body, and neither will. A body arrives as a
  series of `BodyBytes` events; a struct with a body field would have
  forced the package to buffer a 4 GB upload before handing anything
  back.
- `H1Framing`, with `request_framing` and `response_framing` computing
  it. `response_framing` takes the method that was sent, because a
  response to HEAD carries the `Content-Length` of the body it does not
  send and a client that framed on the header alone waits forever.
- `may_reuse` and `status_forbids_body` — the two rules a caller most
  reliably gets wrong, as predicates rather than paragraphs, and both
  called by the encoder so that a program that ignored them still
  cannot write the illegal message.
- `H1Reader`, `feed`, `take`, `finish` and `expect` — the state between
  a byte stream and an event, as a value the caller owns. `event: None`
  means "not yet" and is not an error, which is the same line
  `hci-codec-nv` draws between `Scan` and `DecodeError`.
- `H1DecodeError` and `H1EncodeError` as two types: what the peer sent
  wrong, and what you asked to write wrong. Every decode variant
  carries the byte offset it stopped at, counted from the first byte
  the reader was ever given rather than from the chunk that happened to
  contain the fault.
- `drain`, the one function with an effect row, which binds the
  standard library's `Read[e]` and so costs whatever the caller's
  source costs and nothing of its own.

One toolchain defect travels with the release rather than being
designed around. There is **no `tests/embedded_probe.nv`**: `Result<T,
E>` cannot be spelled at `@tier(embedded)` — with the package's own
error type the `Error` trait is not in the prelude there [E2005], and
without the impl `Result` itself is refused [E2018] — which is
`result-is-unusable-at-tier-embedded-no-error-trait`, open against the
toolchain. The signatures keep their `Result`.

Two further defects were filed from the lane that wrote this package
and do not affect its surface:
`a-struct-bound-two-constructors-deep-in-a-match-pattern-is-an-ice`,
which is why `tests/h1read_tests.nv` splits one match in two; and
`a-call-qualified-with-the-wrong-sibling-module-emits-invalid-ir-instead-of-e2003`.
