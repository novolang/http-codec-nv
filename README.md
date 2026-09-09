# http-codec-nv

**Status: NOT IMPLEMENTED — interface only.**

Every public function below is published with its signature and its
effect row, and every body is `todo()`.  Installing this package works;
calling it panics with `not implemented`.

## What this is

HTTP/1.1 as a state machine that performs nothing.  Feed it bytes; take
back a head, then body chunks, then an end.  Content-Length and chunked
framing (RFC 9112 § 6 and § 7), a header section with case-insensitive
lookup over verbatim storage, refusals that name the byte they stopped
at, and encoders that return bytes.

No socket, no timeout, no retry, no clock, no connection pool.  A
server drives it over a `TcpStream`; a client drives it over TLS; a
proxy drives it over both at once; a replay tool drives it over a pcap.
All four get the same code, because the package has no idea which one
it is.

## Adding it, and checking it

```bash
novo pkg add http-codec-nv    # into your novo.toml
novo pkg build                # type- and effect-check the package
novo test --isolate tests/h1msg_tests.nv
```

`novo test` is red today and that is the point of the release: every
assertion fails with `not implemented: http-codec-nv.<module>.<fn>`.
They turn green one at a time as bodies land.

## The one example that will work

```novo
use h1read
use h1msg
use h1write

// A socket handed us some bytes.  Feed them, take what came out.
fn on_bytes(r: H1Reader, chunk: [u8]) -> Result<H1Reader, H1DecodeError>
    var step = h1read.feed(r, chunk)!
    var go = true
    while go
        match step.event
            None     => go = false
            Some(ev) =>
                handle(ev)
                step = h1read.take(step.reader)!
    Ok(step.reader)

fn handle(ev: H1Event)
    match ev
        RequestHead(req) => start(req)
        BodyBytes(data)  => write_out(data)
        Trailers(_)      => nothing()
        MessageDone      => finish()
        ResponseHead(_)  => nothing()      // a server's reader never sees one
```

## The layer, and why

`core`.  Everything here is arithmetic over bytes the caller already
holds: nothing is read, nothing is written, no clock is consulted, and
the reader's state is a value the caller owns rather than a buffer the
package hides.  That is what lets the same parser run in a server, in a
client, and in a test that feeds it one byte at a time to prove it
survives a chunk boundary anywhere.

**There is no `tests/embedded_probe.nv` in this release, and its
absence is a filed defect rather than a decision.**  `Result<T, E>`
cannot be spelled at `@tier(embedded)`: with the package's own error
type the compiler refuses `impl Error for H1DecodeError` because the
`Error` trait is not in the prelude at that tier [E2005], and without
the impl it refuses the `Result` itself because SPEC § 3.4 requires
one [E2018].  Both refusals were reproduced from this lane against the
probe that was written for it.  That is
`result-is-unusable-at-tier-embedded-no-error-trait`, open against the
toolchain; the signatures keep their `Result` rather than retreating to
`?T` to make a probe build, because a package that dropped its error
reporting to pass an audit row would be reporting a toolchain defect as
a design.

## The load-bearing interface

Two functions, and the fact that each takes an argument you might not
have expected.

```novo
pub fn response_framing(sent: H1Method, resp: H1Response) -> Result<H1Framing, H1DecodeError>
pub fn may_reuse(req: H1Request, resp: H1Response) -> Bool
```

**How long is the body, and may I send another message?**  Those are
the only two questions that matter between two messages on one
connection, and both of them are wrong in most hand-written HTTP code
for the same reason: the answer is not in the message you are holding.

A response to `HEAD` carries the `Content-Length` of the body it is not
sending.  A client that framed on that header alone waits forever for
bytes that were never coming — the oldest bug in HTTP client code — so
`response_framing` takes the method that was sent and this package will
not let you not know it.  `H1Reader` carries the same fact for the
streaming path: a `ReadsResponses` reader is told with `expect(r,
sent)`, once per request, and one that was never told refuses rather
than guessing `Get`.

Persistence is four rules that interact — `Connection: close` from
either party, HTTP/1.0's non-persistence, a body framed by the close
itself, and an upgrade that takes the connection out of HTTP — and two
of them live in the request and two in the response.  So `may_reuse`
takes both heads.  A client that reuses a connection it should not have
gets its next request answered by the tail of the previous body, which
is a disclosure bug rather than a hiccup.

Both of them are **predicates rather than paragraphs**, and both are
called by the encoder: `h1write.response(sent, resp, body)` refuses a
body on a 204 and a body on the answer to a HEAD, so a program that
never read this README still cannot put the illegal message on a wire.

The third load-bearing shape is that a head is a head:

```novo
pub struct H1Request
    method: H1Method
    target: Str
    version: H1Version
    headers: H1Headers
```

There is no `body` field, and there will not be one.  A 4 GB PUT is a
normal thing for a person to do; a body arrives as a series of
`BodyBytes` events and a caller that wants it whole accumulates it
itself.  A struct with a body field would have forced this package to
buffer an upload before handing anything back.

## Taking a stream from the host

`drain` is the one function in the package with an effect row, and the
row is a parameter rather than an effect:

```novo
pub fn drain<S: Read[e]>(r: H1Reader, src: S) -> Result<H1Drained, H1DecodeError> [e]
```

It binds the standard library's `Read` effect parameter, so it costs
whatever the caller's source costs — `[io, net]` against a `TcpStream`,
nothing against an in-memory `Buffer` — which is what lets a `core`
package offer the read-until-done loop instead of making every caller
write it (SPEC § 5.6, and `docs/publishing.md` § Design calls this the
direct shape).

`tests/h1read_tests.nv` asserts it over a `Buffer`, and the assertion
is made by the compiler before the run starts: had `drain` spent an
effect instead of binding one, that file would not compile.

## What this does not do, on purpose

- **It does not parse the target.**  `H1Request.target` is the bytes as
  they arrived.  Only one of RFC 9112 § 3.2's four target forms is a
  URL, `target_form` says which form you are holding, and url-nv parses
  the one that is — from the caller, not from here.  Taking url-nv as a
  dependency would put it in every consumer for the form most of them
  will never meet.
- **It does not percent-decode.**  A `%2F` in a path is not a `/`, and a
  decode this package performed would be a decode a caller could not opt
  out of.
- **It does not decompress.**  `gzip` and `br` are content codings; only
  `chunked` is framing.  A caller decompresses after this package has
  framed the message.
- **It does not do HTTP/2 or HTTP/3.**  Those are different wire formats
  that share a semantics.  `h1err.BadHttpVersion` is what a reader
  answers when it meets one.
- **It does not connect, wait, retry or pool.**  That is the whole
  meaning of `core`.

## What `std.http` keeps

`std.http` is the client and the server, and it stays both.  It owns
`HttpClient`, `HttpServer`, `HttpRouter` and the middleware; it owns
`HttpRequest`, `HttpResponse` and `HttpHeader`, which is why this
package's types are named `H1…`; and it owns every effect —
`http_server_router` declares `[io, net, mutate]` and always will.

What moves under it is the parsing.  `std.http`'s
`http_server_parse_head(raw: Str) -> ?HttpRequest` takes a `Str`,
returns `None` for every kind of malformed message alike, reads only
the head, and has no chunked decoder at all.  This package takes bytes,
so a head with an invalid UTF-8 byte is refused rather than mangled on
the way in; returns a reason with the byte offset; frames the body; and
decodes chunked transfer coding, which `std.http`'s server today
handles with `HttpChunkWriter` on the way out and not at all on the way
in.

`orbit/http-server` is the other consumer, and the same applies: it
keeps the routing and the accept loop.

## The reference implementation

`httparse` for the head — its "resume from where you stopped" contract
is why `H1Reader` carries an offset rather than restarting a parse per
chunk — and `h11` for the state machine, whose separation of a
connection's two halves into two readers with one role each is the
shape `H1Role` takes.  RFC 9110 and RFC 9112 are the specification and
the source of the test vectors, and RFC 9112 § 6.1's MUST about
`Content-Length` beside `Transfer-Encoding` is the one refusal in this
package that is a security property rather than a preference.

Three things change in the port.  `httparse`'s `Status<T>` — `Complete`
or `Partial` — becomes `event: ?H1Event` on a step, because a partial
message is the ordinary case on a socket and a codec that reported it
in the error channel would have every caller filtering one variant out
of its logs forever; `hci-codec-nv` drew the same line between `Scan`
and `DecodeError` and it is drawn here for the same reason.  `h11`'s
single `Connection` with a role field becomes `H1Role` on the reader,
so a server cannot accidentally parse a response.  And `h11`'s
exceptions become two error types rather than one: `H1DecodeError` is
what the peer sent, `H1EncodeError` is what you asked to write, and a
caller matching one enum for both would be writing arms it can never
reach.

## Status

| item | implemented |
| --- | --- |
| `h1msg` — `H1Method`, `H1Version`, `H1Header`, `H1Headers`, `H1Request`, `H1Response`, `H1Framing`, `H1TargetForm` | types only |
| `h1msg.headers`, `.no_headers`, `.get`, `.get_all`, `.has`, `.set`, `.append`, `.remove`, `.fields_of`, `.field_count`, `.name_eq` | no |
| `h1msg.is_token`, `.is_field_value`, `.method_token`, `.method_of`, `.version_text`, `.target_form` | no |
| `h1msg.request_framing`, `.response_framing` | no |
| `h1msg.status_forbids_body`, `.is_informational`, `.status_reason`, `.may_reuse`, `.wants_close`, `.is_upgrade` | no |
| `h1err` — `H1DecodeError`, `H1EncodeError` | types only |
| `h1err.offset_of`, `.status_for`, and both `message` impls | no |
| `h1read` — `H1Role`, `H1Limits`, `H1Event`, `H1Step`, `H1Reader`, `H1Drained` | types only |
| `h1read.default_limits`, `.embedded_limits`, `.reader`, `.expect` | no |
| `h1read.feed`, `.take`, `.finish`, `.pending_len`, `.offset`, `.message_open`, `.parse_head` | no |
| `h1read.drain` | no |
| `h1write.request_head`, `.response_head`, `.request`, `.response` | no |
| `h1write.with_content_length`, `.with_chunked`, `.chunk`, `.last_chunk` | no |
| `h1write.continue_head`, `.switching_protocols_head`, `.error_head` | no |
