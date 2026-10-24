# cpatch (Rust)

A Rust port of `python -m infuse_iot.cpatch`, for generating, applying and inspecting
CPatch binary patch files.

Patch files use the same format and encoders as the Python implementation
(`shortest-path` and `shortest-path-delta`), at roughly 15x the speed. Tie-breaking between
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
cpatch generate [--encoder shortest-path|shortest-path-delta] <ORIGINAL> <NEW> <PATCH>
cpatch validation [--invalid-length] [--invalid-crc] [--delta] <INPUT_FILE> <PATCH>
cpatch patch <ORIGINAL> <PATCH> <OUTPUT>
cpatch dump <PATCH>
```

`--verbose` / `-v` before the command prints instruction counts when generating.

## Keeping the implementations in sync

The modules mirror the Python package:

| Rust                       | Python                                         |
|----------------------------|------------------------------------------------|
| `src/instructions.rs`      | `infuse_iot/cpatch/instructions.py`            |
| `src/matching.rs`          | run finding in `encoder_shortest_path.py`      |
| `src/shortest_path.rs`     | `encoder_shortest_path.py`                     |
| `src/shortest_path_delta.rs` | `encoder_shortest_path_delta.py`             |
| `src/cpatch.rs`            | `infuse_iot/cpatch/__init__.py`                |

Changes to either encoder's algorithm should be made in both implementations, and compared
on a set of real firmware releases to confirm the patch sizes remain equivalent.
