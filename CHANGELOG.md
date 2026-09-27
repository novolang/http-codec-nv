# Changelog

Every published version, newest first. This file is on the publish
allow-list, so it travels with the package: it is the only thing a
consumer deciding whether to upgrade can read.

## 0.1.0 — 2026-09-27

The first implementation of the interface published as 0.0.1: the
header section and the framing rules, the reader, the encoders and the
refusals.

### Added

- `h1read` reads requests and responses a byte at a time or in any
  pieces, with `Content-Length`, chunked and until-close framing, chunk
  extensions skipped, trailer sections, pipelined messages, interim 1xx
  responses and the method queue `expect` keeps.  A line may end in a
  bare line feed, and empty lines before a start line are skipped (RFC
  9112 section 2.2).  A start line is refused as soon as its first bytes
  are wrong, not after a whole head.
- `BodyNotAllowed` is answered when bytes that do not begin a status
  line follow a 1xx, 204 or 304 response or the answer to `HEAD`.
- `h1write` checks the method, the target, the status, the reason
  phrase and every field before it writes them.
- `tests/h1wire_tests.nv` reads RFC 9112's and RFC 9110's examples and
  the h11 and httparse edge cases whole, three bytes and one byte at a
  time.  `tests/differential_tests.nv`, written by
  `tools/differential.py`, compares the reader with Python's
  `http.client` over 120 responses.  Every line under `src/` is run by
  the suites; `bash tests/coverage.sh` prints the number.

### Changed

These break code written against 0.0.x.

- `H1EncodeError` has four more variants: `BadTargetToWrite`,
  `BadReasonToWrite`, `EmptyChunkToWrite` and `ForbiddenTrailerToWrite`.
  Each names a message the encoders refuse that the 0.0.x variants had
  no name for.
- `H1Reader` has five more fields: `phase`, `remaining`, `methods`,
  `closed` and `no_body_status`.  A reader is made with `h1read.reader`.
- `h1msg.is_field_value` refuses every control character but the
  horizontal tab, as RFC 9110 section 5.5 does, and not only CR, LF and
  NUL.
- A lowercase `get` is `ExtensionMethod("get")`, as the 0.0.x tests
  said, and not `BadMethodToken`, as the 0.0.x README and `h1err`
  comment said.
- `finish` answers the next event after the close, and `take` answers
  the rest.  `parse_head` computes no framing: the reader in its answer
  has consumed the head and nothing else.
- A `Transfer-Encoding` naming any coding but `chunked` is refused in a
  response too.
- `h1msg` and `h1read` spell the decode error `h1err.H1DecodeError`.
  The type is the same one.
- The toolchain floor is 0.13.0.

## 0.0.3 — 2026-09-15

README rewritten to the package README style guide (docs/writing-a-readme.md); no change to the interface.

## 0.0.2 — 2026-09-10

- **Toolchain floor is 0.8.9**: the bodies and signatures use what 0.8.9 added (`todo()`, a bound effect parameter, the four layers), and the manifest says so instead of letting an older toolchain fail on an undefined function.  No signature changed.

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

### Design notes

The port took its shape from two reference implementations. `httparse`
supplied the head parser's "resume from where you stopped" contract,
which is why `H1Reader` carries an offset rather than restarting a parse
on every chunk. `h11` supplied the state machine, whose separation of a
connection's two halves into two readers with one role each became
`H1Role`.

Three things changed in the port. `httparse`'s `Status<T>` — `Complete`
or `Partial` — became `event: ?H1Event` on a step, because a partial
message is the ordinary case on a socket and a codec that reported it in
the error channel would have every caller filtering one variant out of
its logs forever. `h11`'s single connection with a role field became
`H1Role` on the reader, so a server cannot accidentally parse a
response. And `h11`'s exceptions became two error types rather than one,
so a caller matching on either is not writing arms it can never reach.

The types are named `H1…` because `std.http` already owns `HttpRequest`,
`HttpResponse` and `HttpHeader`, and a public type name is unique across
a whole assembly rather than per package. `H1` is what the reference
implementations call this wire format when they have to distinguish it
from HTTP/2.
