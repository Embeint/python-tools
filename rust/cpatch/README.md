# cpatch (Rust)

A Rust port of `python -m infuse_iot.cpatch`, for generating, applying and inspecting
CPatch binary patch files.

Patch files use the same format and encoders as the Python implementation
(`shortest-path`, `shortest-path-delta` and `stream-thumb2`), at roughly 15x the speed. Tie-breaking between
equally sized encodings is not guaranteed to match, so generated patches can differ from the
Python output while being equivalent in size. The `greedy` encoder is not supported, and
terminal output differs from the Python tool.

## Building

```sh
cargo build --release
```

The binary is written to `target/release/cpatch`. There are no external dependencies.

## Usage

```sh
cpatch generate [--encoder shortest-path|shortest-path-delta|stream-thumb2] <ORIGINAL> <NEW> <PATCH>
cpatch validation [--invalid-length] [--invalid-crc] [--delta|--stream-thumb2] <INPUT_FILE> <PATCH>
cpatch patch <ORIGINAL> <PATCH> <OUTPUT>
cpatch dump <PATCH>
```

`--verbose` / `-v` before the command prints instruction counts when generating.

## Element stream format (version 3, `stream-thumb2`)

Patch data is a relocation preamble followed by a flat stream of elements, each a header byte
of `copy:4 | op:4` that copies from the original then performs one operation (16 bit addition
from a 10 entry delta history, explicit addition, literal, literal followed by a shift, or
shift). See `src/stream.rs` for the exact encoding.

Every copy relocates the sites it fully contains, rather than only dedicated instructions:

* Thumb-2 BL / B.W instructions, by the shift of the original offset they target
* Aligned words that point into the original image, given its load address
* Aligned words that point into other address regions (such as RAM), each with its own map

The exact rules for finding and relocating sites, which appliers must match, are in the
`src/stream.rs` module documentation.

Relocation maps have no fixed entry limit, and use fixed width sorted entries so appliers can
binary search them in the patch file rather than caching them in RAM.

## Keeping the implementations in sync

The modules mirror the Python package:

| Rust                       | Python                                         |
|----------------------------|------------------------------------------------|
| `src/instructions.rs`      | `infuse_iot/cpatch/instructions.py`            |
| `src/matching.rs`          | run finding in `encoder_shortest_path.py`      |
| `src/shortest_path.rs`     | `encoder_shortest_path.py`                     |
| `src/shortest_path_delta.rs` | `encoder_shortest_path_delta.py`             |
| `src/stream.rs`            | `infuse_iot/cpatch/stream.py`                  |
| `src/stream_thumb2.rs`     | `encoder_stream_thumb2.py`                     |
| `src/cpatch.rs`            | `infuse_iot/cpatch/__init__.py`                |

Changes to either encoder's algorithm should be made in both implementations, and compared
on a set of real firmware releases to confirm the patch sizes remain equivalent.
