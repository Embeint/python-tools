#!/usr/bin/env python3

import argparse
import logging

from infuse_iot.cpatch import Encoder, cpatch

parser = argparse.ArgumentParser()
parser.add_argument("--verbose", "-v", action="store_true", help="Verbose command output")
subparser = parser.add_subparsers(dest="command", title="Commands", required=True)

# Generate patch file
generate_args = subparser.add_parser("generate", help="Generate a patch file")
generate_args.add_argument("original", help="Original file to use as base image")
generate_args.add_argument("new", help="New file that will be the result of applying the patch")
generate_args.add_argument("patch", help="Output patch file name")
generate_args.add_argument(
    "--encoder",
    choices=[e.value for e in Encoder],
    default=Encoder.SHORTEST_PATH.value,
    help="Patch encoding algorithm",
)

# Generate validation patch file
validation_args = subparser.add_parser("validation", help="Generate a patch file for validating appliers")
validation_args.add_argument("--invalid-length", action="store_true", help="Incorrect output file length")
validation_args.add_argument("--invalid-crc", action="store_true", help="Incorrect output file CRC")
validation_format = validation_args.add_mutually_exclusive_group()
validation_format.add_argument(
    "--delta", action="store_true", help="Include PATCH_DELTA instructions (patch version 2.0)"
)
validation_format.add_argument(
    "--stream-thumb2",
    action="store_true",
    help="Element stream with relocation (patch version 3.0)",
)
validation_args.add_argument("input_file", help="File to use as base image and desired output")
validation_args.add_argument("patch", help="Output patch file name")

# Apply patch file
patch_args = subparser.add_parser("patch", help="Apply a patch file")
patch_args.add_argument("original", help="Original file to use as base image")
patch_args.add_argument("patch", help="Patch file to apply")
patch_args.add_argument("output", help="File to write output to")

# Dump patch instructions
dump_args = subparser.add_parser("dump", help="Dump patch file instructions to terminal")
dump_args.add_argument("patch", help="Patch file to dump")

# Parse args
args = parser.parse_args()
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Run requested command
if args.command == "generate":
    with open(args.original, "rb") as f_orig, open(args.new, "rb") as f_new:
        patch = cpatch.generate(
            f_orig.read(-1),
            f_new.read(-1),
            args.verbose,
            Encoder(args.encoder),
        )
    with open(args.patch, "wb") as f_output:
        f_output.write(patch)
elif args.command == "validation":
    with open(args.input_file, "rb") as f_input:
        patch = cpatch.validation(
            f_input.read(-1), args.invalid_length, args.invalid_crc, args.delta, args.stream_thumb2
        )
    with open(args.patch, "wb") as f_output:
        f_output.write(patch)
elif args.command == "patch":
    with open(args.original, "rb") as f_orig, open(args.patch, "rb") as f_patch:
        output = cpatch.patch(f_orig.read(-1), f_patch.read(-1))
    with open(args.output, "wb") as f_output:
        f_output.write(output)
elif args.command == "dump":
    with open(args.patch, "rb") as f_patch:
        cpatch.dump(f_patch.read(-1))
