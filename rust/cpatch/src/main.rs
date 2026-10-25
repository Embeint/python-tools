//! Generate and apply CPatch binary patch files.
//!
//! Port of `python -m infuse_iot.cpatch`, supporting the `shortest-path`, `shortest-path-delta`
//! and `stream-thumb2` encoders.

mod cpatch;
mod crc;
mod instructions;
mod matching;
mod shortest_path;
mod shortest_path_delta;
mod stream;
mod stream_thumb2;

use std::fs;
use std::process::ExitCode;

use cpatch::Encoder;

const USAGE: &str = "\
Usage: cpatch [--verbose|-v] <COMMAND>

Commands:
  generate [--encoder <ENCODER>] <ORIGINAL> <NEW> <PATCH>
      Generate a patch file
      --encoder   shortest-path (default) | shortest-path-delta | stream-thumb2
  validation [--invalid-length] [--invalid-crc] [--delta|--stream-thumb2] <INPUT_FILE> <PATCH>
      Generate a patch file for validating appliers
  patch <ORIGINAL> <PATCH> <OUTPUT>
      Apply a patch file
  dump <PATCH>
      Dump patch file instructions to terminal
";

fn read(path: &str) -> Result<Vec<u8>, String> {
    fs::read(path).map_err(|e| format!("{path}: {e}"))
}

fn write(path: &str, data: &[u8]) -> Result<(), String> {
    fs::write(path, data).map_err(|e| format!("{path}: {e}"))
}

/// Split arguments into flags (with optional values) and positional arguments
struct Args {
    flags: Vec<(String, Option<String>)>,
    positional: Vec<String>,
}

fn parse(args: &[String], with_value: &[&str], allowed: &[&str]) -> Result<Args, String> {
    let mut flags = Vec::new();
    let mut positional = Vec::new();
    let mut iter = args.iter();
    while let Some(arg) = iter.next() {
        if let Some(stripped) = arg.strip_prefix("--").filter(|_| arg.len() > 2) {
            let (name, inline) = match stripped.split_once('=') {
                Some((n, v)) => (format!("--{n}"), Some(v.to_string())),
                None => (arg.clone(), None),
            };
            if !allowed.contains(&name.as_str()) {
                return Err(format!("unrecognized argument: {name}"));
            }
            let value = if with_value.contains(&name.as_str()) {
                Some(
                    inline
                        .or_else(|| iter.next().cloned())
                        .ok_or(format!("{name} requires a value"))?,
                )
            } else {
                None
            };
            flags.push((name, value));
        } else {
            positional.push(arg.clone());
        }
    }
    Ok(Args { flags, positional })
}

impl Args {
    fn has(&self, name: &str) -> bool {
        self.flags.iter().any(|(n, _)| n == name)
    }

    fn value(&self, name: &str) -> Option<&str> {
        self.flags
            .iter()
            .rev()
            .find(|(n, _)| n == name)
            .and_then(|(_, v)| v.as_deref())
    }

    fn positional<const N: usize>(&self) -> Result<[&str; N], String> {
        let args: Vec<&str> = self.positional.iter().map(String::as_str).collect();
        args.try_into()
            .map_err(|_| format!("expected {N} positional arguments"))
    }
}

fn run(args: &[String]) -> Result<(), String> {
    let mut verbose = false;
    let mut rest = args;
    while let Some(first) = rest.first() {
        match first.as_str() {
            "--verbose" | "-v" => verbose = true,
            "--help" | "-h" => {
                print!("{USAGE}");
                return Ok(());
            }
            _ => break,
        }
        rest = &rest[1..];
    }
    let (command, rest) = rest.split_first().ok_or("missing command")?;

    match command.as_str() {
        "generate" => {
            let args = parse(rest, &["--encoder"], &["--encoder"])?;
            let [original, new, patch] = args.positional()?;
            let encoder_name = args.value("--encoder").unwrap_or("shortest-path");
            let encoder = Encoder::from_name(encoder_name).ok_or(format!("invalid encoder: {encoder_name}"))?;
            let bin_original = read(original)?;
            let bin_new = read(new)?;
            let generated = cpatch::generate(&bin_original, &bin_new, encoder).map_err(|e| e.to_string())?;
            let ratio = 100.0 * generated.patch.len() as f64 / bin_new.len() as f64;
            println!("Original File: {:6} bytes", bin_original.len());
            println!("     New File: {:6} bytes", bin_new.len());
            println!(
                "   Patch File: {:6} bytes ({ratio:.2}%) ({:5} instructions)",
                generated.patch.len(),
                generated.count
            );
            if verbose {
                println!();
                println!("Instructions:");
                for (name, count) in &generated.counts {
                    println!("{name:>16}: {count}");
                }
            }
            write(patch, &generated.patch)
        }
        "validation" => {
            let args = parse(
                rest,
                &[],
                &["--invalid-length", "--invalid-crc", "--delta", "--stream-thumb2"],
            )?;
            let [input, patch] = args.positional()?;
            let bin = read(input)?;
            let out = cpatch::validation(
                &bin,
                args.has("--invalid-length"),
                args.has("--invalid-crc"),
                args.has("--delta"),
                args.has("--stream-thumb2"),
            )?;
            write(patch, &out)
        }
        "patch" => {
            let args = parse(rest, &[], &[])?;
            let [original, patch, output] = args.positional()?;
            let out = cpatch::apply(&read(original)?, &read(patch)?).map_err(|e| e.to_string())?;
            write(output, &out)
        }
        "dump" => {
            let args = parse(rest, &[], &[])?;
            let [patch] = args.positional()?;
            cpatch::dump(&read(patch)?).map_err(|e| e.to_string())
        }
        other => Err(format!("invalid command: {other}")),
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match run(&args) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("error: {e}\n\n{USAGE}");
            ExitCode::FAILURE
        }
    }
}
