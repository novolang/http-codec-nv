#!/usr/bin/env python3
"""Write tests/differential_tests.nv from Python's http.client.

`http.client.HTTPResponse` is an independent HTTP/1.1 response reader.
This script builds responses from a seeded pseudo-random generator,
has Python read each one, and records what it read: the status, the
reason phrase, the header fields in order with their case, and the
body.  The test file feeds the same bytes to this package's reader in
pieces of a recorded size and asserts the same answer.

The responses cover the three framings a response can have
(Content-Length, chunked with and without extensions and trailer
fields, and until the close), repeated header fields, names in mixed
case, optional whitespace around values, and line ends of CRLF or a
bare LF.  Python keeps the whitespace after a field value, which RFC
9112 section 5 says is not part of the value, so the values recorded
here have it removed.  Chunk data is always followed by CRLF, because Python reads
exactly two bytes there.  Python drops a trailer section, so the trailer fields are
not compared.  Every generated response is one both readers accept;
a response Python refused would stop the script.

Run from the package root:  python3 tools/differential.py
The output is passed through `novo fmt`.
"""
import http.client
import io
import random
import subprocess

COUNT = 120
SEED = 9112

NAMES = ['Content-Type', 'cache-control', 'X-Request-Id', 'SET-COOKIE',
         'Vary', 'Server', 'Date', 'ETag', 'x-trace', 'Via']
REASONS = {200: 'OK', 201: 'Created', 202: 'Accepted', 203: '',
           206: 'Partial Content', 301: 'Moved Permanently',
           302: 'Found', 400: 'Bad Request', 404: 'Not Found',
           418: "I'm a teapot", 500: 'Internal Server Error',
           503: 'Service Unavailable'}
WORDS = ['alpha', 'beta', 'text/html; charset=utf-8', 'no-cache, no-store',
         'W/"abc123"', 'a=1; Path=/; HttpOnly', 'Mon, 01 Jan 2024 00:00:00 GMT',
         '1.1 proxy.example', 'gzip', 'value with  inner   spaces']
BODY = 'abcdefghijklmnopqrstuvwxyz0123456789 ABCDEFGHIJ\r\n.,;:?-_=+/'


class Sock:
    def __init__(self, data):
        self.data = data

    def makefile(self, mode):
        return io.BytesIO(self.data)


def response(rng):
    """One response: its bytes and whether it is framed by the close."""
    eol = '\r\n' if rng.random() < 0.8 else '\n'
    status = rng.choice(sorted(REASONS))
    reason = REASONS[status]
    version = 'HTTP/1.1' if rng.random() < 0.9 else 'HTTP/1.0'
    lines = ['%s %d %s' % (version, status, reason)]
    for _ in range(rng.randrange(0, 6)):
        name = rng.choice(NAMES)
        ws1 = rng.choice(['', ' ', '  ', '\t'])
        ws2 = rng.choice(['', '', ' ', '\t '])
        lines.append('%s:%s%s%s' % (name, ws1, rng.choice(WORDS), ws2))
    body = ''.join(rng.choice(BODY) for _ in range(rng.randrange(0, 90)))
    framing = rng.choice(['length', 'chunked', 'close'])
    tail = ''
    if framing == 'length':
        lines.append('Content-Length: %d' % len(body))
        tail = body
    elif framing == 'chunked':
        lines.append('Transfer-Encoding: chunked')
        at = 0
        while at < len(body):
            n = rng.randrange(1, 20)
            piece = body[at:at + n]
            ext = rng.choice(['', '', ';x=1', ' ;name="v"'])
            size = '%x' % len(piece)
            if rng.random() < 0.3:
                size = size.upper()
            tail += size + ext + eol + piece + '\r\n'
            at += n
        tail += '0' + eol
        if rng.random() < 0.3:
            tail += 'Server-Timing: total;dur=12' + eol
        tail += eol
    else:
        tail = body
    text = eol.join(lines) + eol + eol + tail
    return text, framing == 'close'


def python_reads(raw):
    """Python's reading: status, reason, fields and body."""
    r = http.client.HTTPResponse(Sock(raw.encode('latin-1')), method='GET')
    r.begin()
    fields = [(k, v.rstrip(' \t')) for k, v in r.msg.items()]
    body = r.read().decode('latin-1')
    return r.status, r.reason, fields, body


def nv(s):
    out = s.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$')
    return '"' + out.replace('\r', '\\r').replace('\n', '\\n').replace('\t', '\\t') + '"'


def main():
    rng = random.Random(SEED)
    rows = []
    while len(rows) < COUNT:
        raw, close = response(rng)
        status, reason, fields, body = python_reads(raw)
        summary = '%d|%s|%s|%s' % (
            status, reason, ';'.join('%s=%s' % f for f in fields), body)
        rows.append((raw, close, rng.choice([1, 2, 5, 17, 1000]), summary))
    out = []
    out.append('''// tests/differential_tests.nv — this package's reader against
// Python's `http.client`, over %d pseudo-random responses.
//
// Written by tools/differential.py; do not edit by hand.  Each row is
// the bytes of a response, whether the connection closes after it, the
// size of the pieces the bytes are fed in, and what Python read: the
// status, the reason phrase, the header fields in order and the body.
// Python drops a trailer section, so trailer fields are not compared,
// and it keeps the whitespace after a field value, which RFC 9112
// section 5 says is not part of it, so the recorded values have it
// removed.

use std.test
use std.str
use std.bytes
use h1msg
use h1read

// The rows: the bytes, whether the peer closes, the piece size, and
// Python's reading.
fn rows() -> [(Str, Bool, Int, Str)]
    [''' % COUNT)
    for i, (raw, close, piece, summary) in enumerate(rows):
        sep = ',' if i + 1 < len(rows) else ''
        out.append('        (%s,\n        %s,\n        %d,\n        %s)%s' % (
            nv(raw), 'true' if close else 'false', piece, nv(summary), sep))
    out.append('''    ]

// The text of a list of bytes.
fn text_of(data: [u8]) -> Str
    let sb = str.builder_new()
    for b in data
        str.builder_append_char(sb, b as Int)
    let s = str.builder_to_str(sb)
    str.builder_drop(sb)
    s

// A response head in the form Python's reading is written.
fn head_text(resp: H1Response) -> Str
    let fields = list.map(h1msg.fields_of(resp.headers), f => f.name + "=" + f.value)
    "${resp.status}|" + resp.reason + "|" + str.join(fields, ";") + "|"

// This package's reading of one row, in the form Python's is written.
fn reading(raw: Str, close: Bool, piece: Int) -> Result<Str, H1DecodeError>
    let input = bytes.to_byte_list(bytes.from_str(raw))
    var r = h1read.expect(h1read.reader(ReadsResponses, h1read.default_limits()), Get)
    var head = ""
    var body = ""
    var at = 0
    var closing = false
    loop
        let step = h1read.take(r)!
        r = step.reader
        match step.event
            Some(ResponseHead(resp)) =>
                head = head_text(resp)
            Some(BodyBytes(data)) => body = body + text_of(data)
            Some(MessageDone) => return Ok(head + body)
            Some(_) => ()
            None =>
                if at < list.len(input)
                    var hi = at + piece
                    if hi > list.len(input)
                        hi = list.len(input)
                    let fed = h1read.feed(r, input[at:hi])!
                    at = hi
                    r = fed.reader
                    match fed.event
                        Some(ResponseHead(resp)) =>
                            head = head_text(resp)
                        Some(BodyBytes(data)) => body = body + text_of(data)
                        Some(MessageDone) => return Ok(head + body)
                        Some(_) => ()
                        None => ()
                else
                    if not close or closing
                        return Ok("the message did not end")
                    closing = true
                    let fin = h1read.finish(r)!
                    r = fin.reader
                    match fin.event
                        Some(BodyBytes(data)) => body = body + text_of(data)
                        Some(MessageDone) => return Ok(head + body)
                        Some(_) => ()
                        None => ()

@test
fn test_every_response_reads_as_python_reads_it() [io]
    var n = 0
    for row in rows()
        let (raw, close, piece, want) = row
        test.case("row ${n}")
        match reading(raw, close, piece)
            Ok(got) => test.assert_eq_str(got, want)
            Err(e)  => test.fail(e.message())
        n = n + 1
''')
    path = 'tests/differential_tests.nv'
    open(path, 'w').write('\n'.join(out))
    subprocess.run(['novo', 'fmt', path], check=False)


if __name__ == '__main__':
    main()
