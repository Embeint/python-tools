#!/usr/bin/env python3

import binascii
import sys

import tabulate
from elftools.dwarf.die import DIE
from elftools.elf.elffile import ELFFile

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.util import console, elftools
from infuse_iot.util.argparse import ValidFile
from infuse_iot.zephyr.errno import errno


class sym_read(InfuseRpcCommand, defs.mem_read):
    RPC_DATA_RECEIVE = True

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--elf", type=ValidFile, help="ELF file to read symbol data from")
        read_type = parser.add_mutually_exclusive_group(required=True)
        read_type.add_argument("--sym", type=str, help="Symbol name to read")
        read_type.add_argument("--addr", type=lambda x: int(x, 0), help="Address to read")

    def __init__(self, args):
        # Ignore context-manager warning since ELFFile requires the file to remain opened
        self.elf_file = open(args.elf, "rb")  # noqa: SIM115
        self.elf = ELFFile(self.elf_file)
        self.symbol_die: DIE | None

        if args.sym:
            symbols = elftools.symbols_from_name(self.elf, args.sym)
            if len(symbols) == 0:
                sys.exit(f"{args.sym} not found in '{args.elf}' symbol table")
            elif len(symbols) == 1:
                self.symbol_die = elftools.dwarf_die_from_symbol(self.elf, symbols[0])
                idx = 0
            else:
                dies = []
                options = []
                # User readable selection requires the filename and line number
                for s in symbols:
                    die = elftools.dwarf_die_from_symbol(self.elf, s)
                    if die is None:
                        continue
                    filename, linenum = elftools.dwarf_die_file_info(self.elf, die)
                    dies.append(die)
                    options.append(f"{filename}:{linenum}")
                # Ask the user which symbol they mean
                try:
                    idx, _ = console.choose_one(f"Multiple symbols matching '{args.sym}', choose one:", options)
                except IndexError:
                    sys.exit("No symbol chosen...")
                self.symbol_die = dies[idx]

            self.symbol = symbols[idx]
        elif args.addr:
            symbol = elftools.symbol_from_address(self.elf, args.addr)
            if symbol is None:
                sys.exit(f"Could not find symbol for address 0x{args.addr:08x} in '{args.elf}' symbol table")
            self.symbol = symbol
        else:
            raise NotImplementedError("Unexpected symbol refrence")

        self.address = self.symbol.entry["st_value"]
        self.num = self.symbol.entry["st_size"]

        dwarf_info = self.elf.get_dwarf_info()
        if self.symbol_die is not None:
            self.symbol_info = elftools.dwarf_die_variable_inf(dwarf_info, self.symbol_die)

        self.expected_offset = 0
        self.output = b""

    def request_struct(self):
        return self.request(self.address)

    def data_payload_recv_len(self):
        return self.num

    def data_recv_cb(self, offset: int, data: bytes) -> None:
        if offset != self.expected_offset:
            missing = offset - self.expected_offset
            print(f"Missed {missing:d} bytes from offset 0x{self.expected_offset:08x}")
            self.output += b"\x00" * missing

        self.output += data
        # Next expected offset
        self.expected_offset = offset + len(data)

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to read data logger ({errno.strerror(-return_code)})")
            return

        if response.sent_len != len(self.output):
            print(f"Unexpected received length ({response.sent_len} != {len(self.output)})")
            return

        if response.sent_crc != binascii.crc32(self.output):
            print(f"Unexpected received length ({response.sent_crc:08x} != {binascii.crc32(self.output)}:08x)")
            return

        if self.elf is None:
            # Hexdump the received payload
            for offset in range(0, len(self.output), 16):
                print(f"{self.address + offset:08x}: {self.output[offset : offset + 16].hex()}")
            return

        # Parse returned value
        symbol_size = self.symbol.entry["st_size"]
        assert len(self.output) >= symbol_size

        if self.symbol_die is not None:
            filename, linenum = elftools.dwarf_die_file_info(self.elf, self.symbol_die)
            print(f" Symbol: {self.symbol.name} ({filename}:{linenum})")

        address_base = self.symbol.entry["st_value"]
        print(f"Address: 0x{address_base:x}")
        print(f"   Size: {symbol_size} bytes")
        if symbol_size <= 32:
            print(f"    Raw: {self.output.hex()}")
        else:
            print(f"    Raw: {self.output[:32].hex()}...")

        def info_table(info, offset=0):
            table = [[f"{'  ' * offset}{info.name}", f"({info.tag}) ({info.ctype}) {info.offset}", ""]]
            for child in info.children:
                table += info_table(child, offset + 1)
            return table

        def field_table(info: elftools.dwarf_field, buffer: bytes, offset: int = 0):
            if info.ctype is None:
                table = [[f"0x{address_base + info.offset:08x}", f"{'  ' * offset}{info.name}", "", "", ""]]
            else:
                value = info.ctype.from_buffer_copy(buffer, info.offset).value
                value_hex = hex(value) if not isinstance(value, float) else "N/A"
                points_to = ""
                if info.tag == "DW_TAG_pointer_type":
                    if value == 0x00:
                        points_to = "NULL"
                    else:
                        sym = elftools.symbol_from_address(self.elf, value)
                        if sym:
                            ptr_offset = ""
                            if value != sym.entry["st_value"]:
                                ptr_offset = f" (+ {value - sym.entry['st_value']})"
                            points_to = f"{sym.name}{ptr_offset}"
                        else:
                            points_to = "<unknown>"
                table = [
                    [f"0x{address_base + info.offset:08x}", f"{'  ' * offset}{info.name}", value, value_hex, points_to]
                ]
            for child in info.children:
                table += field_table(child, buffer, offset + 1)
            return table

        tabulate.PRESERVE_WHITESPACE = True
        print(
            tabulate.tabulate(field_table(self.symbol_info, self.output), ["Address", "Field", "Value", "Hex", "Ptr"])
        )
