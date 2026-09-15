# http-codec-nv

HTTP is the protocol the web runs on.
[RFC 9110](https://www.rfc-editor.org/rfc/rfc9110) defines its semantics:
the methods, the status codes and the header fields.
[RFC 9112](https://www.rfc-editor.org/rfc/rfc9112) defines HTTP/1.1, the
text wire format those semantics travel in. This package brings RFC 9112
to novo-lang as a codec, with no socket underneath. Two other packages on
the registry meet it:
[websocket-codec-nv](https://novo-lang.org/packages/websocket-codec-nv),
whose handshake is an HTTP/1.1 upgrade, and
[form-nv](https://novo-lang.org/packages/form-nv), which decodes the
request bodies this package frames.
[http2-nv](https://novo-lang.org/packages/http2-nv) carries the same
semantics over a different wire format.

**Status: NOT IMPLEMENTED — interface only.** Every function is declared
with its full signature, but every body is a `todo()` that panics when
called. The package is published so its design can be reviewed and
depended on before it is implemented. Version 0.1.0 will be the first
working release.

## What HTTP/1.1 is

An HTTP message is a **head** followed by a **body**. The head is a
**start line** and a **header section**, and a blank line ends it. A
request's start line is a method, a request target and a version, such as
`GET /index.html HTTP/1.1`. A response's start line is a version, a
three-digit status and a reason phrase, such as `HTTP/1.1 200 OK`. RFC
9112 sections 3 and 4 define the two.

A **header field** is a name, a colon and a value, one per line. Field
names are compared without regard to case, and only ASCII case (RFC 9110
section 5.1). A name may appear more than once. `Set-Cookie` and `Via`
legitimately repeat, so a header section is an ordered list of fields
rather than a map.

The head does not say where the body ends. **Framing** is the rule that
answers that question, and it is computed from the head rather than read
out of it. RFC 9112 section 6 gives four answers.

| Framing | How the length is known | Reference |
| --- | --- | --- |
| No body | The method or the status forbids one, or a request carries neither framing header | RFC 9112 section 6 |
| Fixed length | A `Content-Length` field gives the byte count | RFC 9112 section 6.2 |
| Chunked | Each piece is preceded by its size in hexadecimal, and a piece of size zero ends the body | RFC 9112 section 7.1 |
| Until close | The connection closing is what ends the body. Responses only | RFC 9112 section 6.3 |

**Chunked transfer coding** is the only transfer coding that frames a
message. `gzip` and `br` are content codings, which change the bytes and
not the length. A chunked body may end with a **trailer section**: header
fields sent after the body, for values the sender could not know until it
had written the body.

One connection carries more than one message. A **persistent connection**
is one a client may send a second request on, and HTTP/1.1 is persistent
by default (RFC 9112 section 9.3). Four things end persistence: a
`Connection: close` field from either party, an HTTP/1.0 peer that did
not ask to keep the connection alive, a response framed by the close
itself, and an exchange that hands the connection to another protocol.

A **request target** takes one of four shapes, and three rules depend on
which one arrived (RFC 9112 section 3.2).

| Form | Example | Where it is legal |
| --- | --- | --- |
| origin-form | `/where?q=now` | Every ordinary request |
| absolute-form | `http://example.org/where` | A request to a proxy, and any conforming server must accept one directly |
| authority-form | `example.org:443` | `CONNECT`, and nothing else |
| asterisk-form | `*` | A server-wide `OPTIONS`, and nothing else |

This package performs no input or output. It opens nothing, waits for
nothing, retries nothing and consults no clock. Every function is
arithmetic over bytes the caller already holds, so the same code runs in
a server over a TCP socket, in a client over TLS, in a proxy over both at
once, and in a replay tool reading a packet capture.

## Install

```
novo pkg add http-codec-nv
```

## Example

```novo
use h1msg
use h1read
use h1err

fn main() [io]
    // The bytes of one request.  On a server these arrive from a
    // socket; here they come from memory, and the codec cannot tell.
    let src = Buffer.from_str("GET /index.html HTTP/1.1\r\nHost: example.org\r\n\r\n")

    // A server's reader parses requests.  The limits are what it will
    // refuse to grow past while one peer keeps sending.
    let r = h1read.reader(ReadsRequests, h1read.default_limits())

    // Read until the message ends, and take every event it produced.
    match h1read.drain(r, src)
        Ok(d) =>
            for ev in d.events
                match ev
                    RequestHead(req) => println("${h1msg.method_token(req.method)} ${req.target}")
                    BodyBytes(data)  => println("${list.len(data)} body byte(s)")
                    Trailers(_)      => println("the trailer section arrived")
                    MessageDone      => println("the message ended")
                    ResponseHead(_)  => println("a server's reader never sees one")
        Err(e) => println("byte ${h1err.offset_of(e)}: ${e.message()}")
    src.drop()
```

Build and test with `novo pkg build` and `novo test`. Today `novo test`
fails on purpose: every test reaches a
`not implemented: http-codec-nv.<module>.<fn>` panic. The tests are the
specification the implementation will have to satisfy.

## What the package contains

| Module | Contents |
| --- | --- |
| `h1msg` | A message head as values. The methods, the versions, the header section with case-insensitive lookup, the four target forms, and the functions that compute framing and persistence from a head. |
| `h1read` | The reader. Bytes go in and events come out: a head, then body bytes, then trailers, then an end. The reader's limits and its byte counter are here. |
| `h1write` | The encoder. Heads, whole messages, and the pieces of a chunked body, each returned as bytes the caller sends. |
| `h1err` | The two error types. What the peer sent wrong, and what you asked to write wrong, with the status a server should answer each refusal with. |

## How to choose an entry point

There are three ways to read, and they differ in who runs the loop.

**`drain` reads until a message ends.** It takes any value that
implements the standard library's `Read` trait, pumps it, and hands back
every event at once. Use it when the bytes come from a stream you can
hand over, such as a TCP connection or an in-memory `Buffer`.

**`feed` and `take` let you run the loop.** `feed` adds bytes and returns
at most one event. `take` returns the next event already buffered,
without adding bytes. Use them when the bytes arrive from somewhere
`drain` cannot reach, such as a TLS record layer or a decompressor.

**`parse_head` reads one head out of a byte list.** It consumes no body
and reports how many bytes it used. Use it when you already hold a whole
head and want nothing else.

There are two ways to write, and they differ in what the body costs in
memory.

**`request` and `response` write a whole message in one call.** They add
the `Content-Length` for the body they were given. Use them when the body
is already in memory.

**`request_head` or `response_head`, then `chunk`, then `last_chunk`,
writes a body of any size.** The head declares chunked transfer coding
with `with_chunked`, and each `chunk` call is a piece the caller sends
and forgets. Use this for a body that does not fit in memory.

## The rules a user needs

1. **"Not yet" is not an error.** A reader answers `event: None` when it
   holds only a prefix of a message, and the caller keeps feeding. An
   `H1DecodeError` means something arrived complete and was wrong. The
   two answers are opposite instructions, so they are separate types.
2. **One call produces one event.** A small request that arrives in a
   single packet completes its head, its body and its end at once, and
   `feed` hands back only the first. Call `take` until it answers `None`
   before going back to the socket.
3. **A client must tell its reader the method it sent.** A response to
   `HEAD` carries the `Content-Length` of the body it does not send (RFC
   9110 section 9.3.2). Call `expect` once per request, in the order the
   requests went out. A `ReadsResponses` reader that was never told
   refuses with `MessageStillOpen` rather than guessing `Get`.
4. **`response_framing` takes the method for the same reason.** So does
   `h1write.response`, which refuses a body on the answer to a `HEAD` and
   a body on a status that forbids one.
5. **`Content-Length` and `Transfer-Encoding` together are refused.** RFC
   9112 section 6.1 says a recipient must refuse the message. Accepting
   one and preferring the other is the request-smuggling bug. The refusal
   is `ConflictingFraming`, and the encoder removes the other header
   rather than write the pair.
6. **1xx, 204 and 304 never carry a body**, whatever their headers say
   (RFC 9110 section 15). `status_forbids_body` is that rule as a
   predicate. A 304 keeps the `Content-Length` a 200 would have carried
   and sends no bytes.
7. **Check `may_reuse` before sending a second request.** It takes both
   heads, because two of the four persistence rules live in the request
   and two in the response (RFC 9112 section 9.3). A client that reuses a
   connection it should not have gets its next request answered by the
   tail of the previous body.
8. **Call `finish` when the peer closes.** A response framed until close
   ends at the close, so its `MessageDone` exists only once somebody says
   the close happened. A close in the middle of any other message is
   `MessageTruncated`. A close between messages is neither an event nor
   an error.
9. **`BodyBytes` is not a message boundary.** The reader hands over
   whatever it has, with chunk framing already removed. How many events
   one body produces depends on how the host read its socket.
10. **Header lookup ignores case and header storage does not.** `get` and
    `name_eq` compare ASCII case-insensitively (RFC 9110 section 5.1).
    `fields_of` returns the names in the case they arrived in, because an
    HTTP message signature (RFC 9421) covers the name as written.
11. **`get` returns the first value of a repeated field.** Use `get_all`
    for every value. Joining `Set-Cookie` values with commas produces a
    cookie nobody can parse.
12. **Methods are case-sensitive** (RFC 9110 section 9). A lowercase
    `get` is `BadMethodToken` and not `Get`. An unregistered token that
    is otherwise legal arrives as `ExtensionMethod`, because RFC 9110
    section 9 leaves the list open.
13. **Every refusal carries the byte it stopped at.** The count starts at
    the first byte the reader was ever given, not at the chunk that
    contained the fault. `h1read.offset` is the same counter.
14. **`h1err.status_for` chooses the answer.** 400 for a malformed
    message, 431 for a head or a header count over the limit, 501 for an
    unsupported transfer coding, and `None` when there is nobody left to
    answer.
15. **The limits are yours to set.** `default_limits` is a 64 KiB head,
    128 fields and 1 MiB chunks, which is what a server on the open
    internet survives with. `embedded_limits` is a 1 KiB head, 16 fields
    and 512-byte chunks. Every limit exists because the unbounded version
    costs an attacker one open socket.
16. **`chunk` refuses an empty piece.** A zero-size chunk is the last
    chunk and ends the message, so `last_chunk` is the only way to end a
    body.
17. **Stop feeding this package when `is_upgrade` answers true.** A 101,
    or a 2xx answering a `CONNECT`, hands the connection to another
    protocol. What follows on it is not HTTP/1.1.

## What is not included

- **Target parsing and percent-decoding.** `H1Request.target` is the
  bytes as they arrived. `target_form` says which of the four shapes you
  are holding, and [url-nv](https://novo-lang.org/packages/url-nv) parses
  the one that is a URL. A `%2F` in a path is not a `/`, and a decode
  this package performed would be one a caller could not opt out of.
- **Content codings.** `gzip` and `br` change the bytes and not the
  length. A caller decompresses after this package has framed the
  message.
- **HTTP/2 and HTTP/3.** They are different wire formats carrying the
  same semantics. A reader that meets one answers `BadHttpVersion`.
  [http2-nv](https://novo-lang.org/packages/http2-nv) is the package for
  HTTP/2.
- **Connecting, waiting, retrying and pooling.** The package holds no
  socket and reads no clock. A host does all four.
- **A proof that the package builds for a microcontroller.** No test in
  this release builds for a device target. `Result<T, E>` cannot be
  spelled at the embedded tier with a package's own error type, because
  the `Error` trait is not in the prelude there. The toolchain defect is
  `result-is-unusable-at-tier-embedded-no-error-trait`, and the
  signatures keep their `Result` until it is fixed.

## Related packages

- [http2-nv](https://novo-lang.org/packages/http2-nv) is HTTP/2: the same
  semantics as binary frames on multiplexed streams, with HPACK header
  compression. A server that speaks both holds one codec of each and
  converts between the two header types.
- [websocket-codec-nv](https://novo-lang.org/packages/websocket-codec-nv)
  is the WebSocket frame format. Its handshake is an HTTP/1.1 upgrade, so
  a server reads the request with this package, answers with
  `h1write.switching_protocols_head`, and then stops feeding this
  package.
- [form-nv](https://novo-lang.org/packages/form-nv) decodes
  `application/x-www-form-urlencoded` and `multipart/form-data` bodies.
  It takes the body bytes this package framed.
- [url-nv](https://novo-lang.org/packages/url-nv) parses an absolute-form
  request target, and the `Location` and `Referer` field values.
- [grpc-codec-nv](https://novo-lang.org/packages/grpc-codec-nv) and
  [grpc-nv](https://novo-lang.org/packages/grpc-nv) are gRPC, which runs
  on HTTP/2 and not on this wire format.
- `std.http` in the standard library is the client and the server. It
  owns `HttpClient`, `HttpServer`, `HttpRouter` and the middleware, and
  its types are named `HttpRequest` and `HttpResponse`, which is why this
  package's are named `H1Request` and `H1Response`. Its own head parser
  takes a `Str`, answers nothing on every kind of malformed message
  alike, reads only the head, and has no chunked decoder.

## Tests

```bash
novo test tests/h1msg_tests.nv       # 19 tests on the heads and the framing rules
novo test tests/h1read_tests.nv      # 12 tests on the reader
novo test tests/h1write_tests.nv     # 12 tests on the encoder
```

The messages the suite asserts against are RFC 9110's and RFC 9112's own:
the section 3 request line, the section 4 status line, the section 6
framing rules, and the section 7.1 chunked body with its trailer section.
The suite checks that a prefix is not an error, that a refusal names the
byte it stopped at, that a response to `HEAD` frames as no body however
long its `Content-Length` says it is, that both framing headers at once
are refused, and that the encoder will not write a message the reader
would refuse.

Two tests are decided by the compiler before the run starts. One holds
`drain` over an in-memory `Buffer`, and would not compile if `drain` had
spent an effect of its own instead of binding the caller's. The other
calls `expect`, and would not compile if the method a client sent were
not something the reader carries.

The tests compile today and fail at run, each on the
`not implemented: http-codec-nv.<module>.<fn>` panic that is its body.
That is the expected state of an interface release. They turn green one
at a time as bodies land.

## Implementation status

| Item | Implemented |
| --- | --- |
| `h1msg.headers`, `.no_headers`, `.get`, `.get_all`, `.has`, `.set`, `.append`, `.remove`, `.fields_of`, `.field_count`, `.name_eq` | no |
| `h1msg.is_token`, `.is_field_value`, `.method_token`, `.method_of`, `.version_text`, `.target_form` | no |
| `h1msg.request_framing`, `.response_framing` | no |
| `h1msg.status_forbids_body`, `.is_informational`, `.status_reason`, `.may_reuse`, `.wants_close`, `.is_upgrade` | no |
| `h1read.default_limits`, `.embedded_limits`, `.reader`, `.expect` | no |
| `h1read.feed`, `.take`, `.finish`, `.pending_len`, `.offset`, `.message_open`, `.parse_head` | no |
| `h1read.drain` | no |
| `h1write.request_head`, `.response_head`, `.request`, `.response` | no |
| `h1write.with_content_length`, `.with_chunked`, `.chunk`, `.last_chunk` | no |
| `h1write.continue_head`, `.switching_protocols_head`, `.error_head` | no |
| `h1err.offset_of`, `.status_for`, and the `message` of both error types | no |

## Licence

Apache-2.0. See `LICENSE`.

<!-- docs/writing-a-readme.md is the style guide for this page. -->
