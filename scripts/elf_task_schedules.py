#!/usr/bin/env python3

import argparse
import base64
import sys
from dataclasses import dataclass
from pathlib import Path

from elftools.dwarf.descriptions import describe_form_class
from elftools.dwarf.dwarf_expr import DWARFExprParser
from elftools.dwarf.locationlists import LocationEntry
from elftools.elf.elffile import ELFFile

STRUCT_NAME = "task_schedule"


@dataclass
class Candidate:
    name: str
    address: int
    size: int
    element_size: int
    file_offset: int
    source: str | None


@dataclass
class SkippedCandidate:
    name: str
    reason: str
    source: str | None


def die_name(die):
    attr = die.attributes.get("DW_AT_name")
    if attr is None:
        return None
    return attr.value.decode("utf-8", errors="replace")


def type_die(die):
    if "DW_AT_type" not in die.attributes:
        return None
    return die.get_DIE_from_attribute("DW_AT_type")


def resolve_type(die):
    while die is not None and die.tag in (
        "DW_TAG_const_type",
        "DW_TAG_volatile_type",
        "DW_TAG_restrict_type",
        "DW_TAG_atomic_type",
        "DW_TAG_typedef",
    ):
        die = type_die(die)
    return die


def type_size(die):
    die = resolve_type(die)
    if die is None:
        return None
    if "DW_AT_byte_size" in die.attributes:
        return die.attributes["DW_AT_byte_size"].value
    if die.tag == "DW_TAG_array_type":
        return array_size(die)
    return None


def subrange_count(subrange_die):
    if "DW_AT_count" in subrange_die.attributes:
        return subrange_die.attributes["DW_AT_count"].value
    if "DW_AT_upper_bound" not in subrange_die.attributes:
        return None

    upper = subrange_die.attributes["DW_AT_upper_bound"].value
    lower = subrange_die.attributes.get("DW_AT_lower_bound")
    lower = lower.value if lower is not None else 0
    return upper - lower + 1


def array_size(array_die):
    if "DW_AT_byte_size" in array_die.attributes:
        return array_die.attributes["DW_AT_byte_size"].value

    elem = type_size(type_die(array_die))
    if elem is None:
        return None

    count = 1
    for child in array_die.iter_children():
        if child.tag != "DW_TAG_subrange_type":
            continue
        sub_count = subrange_count(child)
        if sub_count is None:
            return None
        count *= sub_count
    return elem * count


def array_element_size(array_die):
    return type_size(type_die(array_die))


def is_task_schedule_array(var_die):
    var_type = resolve_type(type_die(var_die))
    if var_type is None or var_type.tag != "DW_TAG_array_type":
        return False

    elem_type = resolve_type(type_die(var_type))
    return elem_type is not None and elem_type.tag == "DW_TAG_structure_type" and die_name(elem_type) == STRUCT_NAME


def source_location(die, dwarf_info):
    file_attr = die.attributes.get("DW_AT_decl_file")
    if file_attr is None:
        return None

    lineprog = dwarf_info.line_program_for_CU(die.cu)
    if lineprog is None:
        return None

    file_index = file_attr.value - 1
    if file_index < 0 or file_index >= len(lineprog["file_entry"]):
        return None

    entry = lineprog["file_entry"][file_index]
    filename = entry.name.decode("utf-8", errors="replace")
    include_dirs = lineprog.header.include_directory
    directory = ""
    if entry.dir_index != 0:
        directory = include_dirs[entry.dir_index - 1].decode("utf-8", errors="replace")

    line = die.attributes.get("DW_AT_decl_line")
    path = str(Path(directory) / filename) if directory else filename
    return f"{path}:{line.value}" if line is not None else path


def address_from_expr(expr, dwarf_info):
    parser = DWARFExprParser(dwarf_info.structs)
    operations = parser.parse_expr(expr)
    if len(operations) != 1:
        return None

    op = operations[0]
    if op.op_name == "DW_OP_addr":
        return op.args[0]

    # Some toolchains emit indexed address operations in split-DWARF-like forms.
    if op.op_name in ("DW_OP_addrx", "DW_OP_GNU_addr_index"):
        try:
            return dwarf_info.get_addr(op.args[0])
        except AttributeError:
            return None

    return None


def variable_address(var_die, dwarf_info):
    loc_attr = var_die.attributes.get("DW_AT_location")
    if loc_attr is None:
        return None

    form_class = describe_form_class(loc_attr.form)
    if form_class == "exprloc":
        return address_from_expr(loc_attr.value, dwarf_info)

    if form_class != "loclist":
        return None

    loc_lists = dwarf_info.location_lists()
    loc_list = loc_lists.get_location_list_at_offset(loc_attr.value, die=var_die)
    addresses = set()
    for entry in loc_list:
        if isinstance(entry, LocationEntry):
            address = address_from_expr(entry.loc_expr, dwarf_info)
            if address is not None:
                addresses.add(address)

    return addresses.pop() if len(addresses) == 1 else None


def file_offset_for_address(elf, address, size):
    for segment in elf.iter_segments():
        if segment.header.p_type != "PT_LOAD":
            continue

        start = segment.header.p_vaddr
        file_end = start + segment.header.p_filesz
        if start <= address and address + size <= file_end:
            return segment.header.p_offset + (address - start)

    for section in elf.iter_sections():
        if section.header.sh_type == "SHT_NOBITS" or section.header.sh_addr == 0:
            continue

        start = section.header.sh_addr
        end = start + section.header.sh_size
        if start <= address and address + size <= end:
            return section.header.sh_offset + (address - start)

    return None


def symbol_file_offsets(elf, name, size):
    offsets = []
    for section in elf.iter_sections():
        if section.header.sh_type not in ("SHT_SYMTAB", "SHT_DYNSYM"):
            continue

        for symbol in section.iter_symbols():
            if symbol.name != name:
                continue
            if symbol["st_info"]["type"] != "STT_OBJECT":
                continue
            if isinstance(symbol["st_shndx"], str):
                continue

            target = elf.get_section(symbol["st_shndx"])
            if target.header.sh_type == "SHT_NOBITS":
                continue

            sym_size = symbol["st_size"]
            if sym_size != 0 and sym_size < size:
                continue

            if target.header.sh_addr == 0:
                offset = target.header.sh_offset + symbol["st_value"]
            else:
                offset = target.header.sh_offset + symbol["st_value"] - target.header.sh_addr

            section_start = target.header.sh_offset
            section_end = section_start + target.header.sh_size
            if section_start <= offset and offset + size <= section_end:
                offsets.append(offset)

    return sorted(set(offsets))


def find_candidates(elf, dwarf_info, name_filter):
    candidates = []
    skipped = []

    for cu in dwarf_info.iter_CUs():
        for die in cu.iter_DIEs():
            if die.tag != "DW_TAG_variable" or not is_task_schedule_array(die):
                continue

            name = die_name(die) or "<anonymous>"
            source = source_location(die, dwarf_info)
            if name_filter is not None and name != name_filter:
                continue

            array_die = resolve_type(type_die(die))
            size = array_size(array_die)
            if size is None:
                skipped.append(SkippedCandidate(name, "unknown array size", source))
                continue

            element_size = array_element_size(array_die)
            if element_size is None:
                skipped.append(SkippedCandidate(name, "unknown array element size", source))
                continue

            address = variable_address(die, dwarf_info)
            if address is None:
                skipped.append(SkippedCandidate(name, "no absolute ELF address", source))
                continue

            file_offset = file_offset_for_address(elf, address, size)
            if file_offset is None:
                offsets = symbol_file_offsets(elf, name, size)
                if len(offsets) == 1:
                    file_offset = offsets[0]
                else:
                    skipped.append(SkippedCandidate(name, "not backed by initialized ELF bytes", source))
                    continue

            candidates.append(Candidate(name, address, size, element_size, file_offset, source))

    return candidates, skipped


def describe_candidate(candidate):
    source = f" ({candidate.source})" if candidate.source else ""
    return f"{candidate.name} @ 0x{candidate.address:x}, {candidate.size} bytes{source}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Print the raw hex bytes for the single initialized 'struct task_schedule' array in a Zephyr ELF.",
        allow_abbrev=False,
    )
    parser.add_argument("elf", type=Path, help="Path to zephyr.elf")
    parser.add_argument(
        "--name",
        help="Require a specific variable name when the ELF contains multiple initialized arrays",
    )
    parser.add_argument("--base64", action="store_true", help="Output base64 data instead of hex")
    args = parser.parse_args()

    with args.elf.open("rb") as f:
        elf = ELFFile(f)
        if not elf.has_dwarf_info():
            sys.exit(f"{args.elf}: no DWARF debug info found")

        dwarf_info = elf.get_dwarf_info()
        candidates, skipped = find_candidates(elf, dwarf_info, args.name)

        if len(candidates) != 1:
            details = []
            if candidates:
                details.append("initialized candidates:")
                details.extend(f"  - {describe_candidate(c)}" for c in candidates)
            if skipped:
                details.append("skipped candidates:")
                details.extend(f"  - {s.name}: {s.reason}" + (f" ({s.source})" if s.source else "") for s in skipped)
            hint = " Use --name to select one." if len(candidates) > 1 else ""
            sys.exit(
                f"expected exactly one initialized struct {STRUCT_NAME} array, "
                f"found {len(candidates)}.{hint}\n" + "\n".join(details)
            )

        candidate = candidates[0]
        f.seek(candidate.file_offset)
        data = f.read(candidate.size)

    array_elements = [data[i : i + candidate.element_size] for i in range(0, len(data), candidate.element_size)]

    def fmt(val: bytes):
        return base64.b64encode(val).decode("utf-8") if args.base64 else val.hex()

    print("\n".join(f"{1001 + i:3d}: {fmt(val)}" for i, val in enumerate(array_elements)))
