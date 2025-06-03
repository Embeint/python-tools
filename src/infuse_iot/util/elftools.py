#!/usr/bin/env python3

import ctypes

from elftools.dwarf.die import DIE
from elftools.dwarf.dwarf_expr import DW_OP_name2opcode
from elftools.dwarf.dwarfinfo import DWARFInfo
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import Symbol, SymbolTableSection
from typing_extensions import Self

TYPEDEF_TO_CTYPE: dict[str, type[ctypes._SimpleCData]] = {
    "int8_t": ctypes.c_int8,
    "uint8_t": ctypes.c_uint8,
    "int16_t": ctypes.c_int16,
    "uint16_t": ctypes.c_uint16,
    "int32_t": ctypes.c_int32,
    "uint32_t": ctypes.c_uint32,
    "int64_t": ctypes.c_int64,
    "uint64_t": ctypes.c_uint64,
}

DWARF_TO_CTYPE: dict[str, type[ctypes._SimpleCData]] = {
    "_Bool": ctypes.c_bool,
    "unsigned char": ctypes.c_ubyte,
    "signed char": ctypes.c_byte,
    "char": ctypes.c_byte,
    "short unsigned int": ctypes.c_uint16,
    "unsigned int": ctypes.c_uint32,
    "int": ctypes.c_int32,
    "long int": ctypes.c_int32,
    "long long int": ctypes.c_int64,
    "long long unsigned int": ctypes.c_uint64,
    "float": ctypes.c_float,
    "double": ctypes.c_double,
}


def symbols_from_name(elf: ELFFile, name: str) -> list[Symbol]:
    """Get a list of symbols from an ELF file with names matching the provided string"""
    symtab = None

    # Locate the symbol table
    for section in elf.iter_sections():
        if isinstance(section, SymbolTableSection):
            symtab = section
            break

    if not symtab:
        return []

    symbols = []
    # Search for the symbol in the symbol table
    for symbol in symtab.iter_symbols():
        if symbol.name == name:
            symbols.append(symbol)
    return symbols


def symbol_from_address(elf: ELFFile, address: int) -> Symbol | None:
    """Get a list of symbols from an ELF file with names matching the provided string"""
    symtab = None

    # Locate the symbol table
    for section in elf.iter_sections():
        if isinstance(section, SymbolTableSection):
            symtab = section
            break

    if not symtab:
        return None

    # Search for the symbol in the symbol table
    for symbol in symtab.iter_symbols():
        start = symbol.entry["st_value"]
        size = symbol.entry["st_size"]
        end = start + size - 1
        if start <= address <= end:
            return symbol
    return None


def dwarf_die_from_symbol(elf: ELFFile, symbol: Symbol) -> DIE | None:
    """Get a Debug Information Entry associated with a symbol (Global variables only)"""
    dwarfinfo = elf.get_dwarf_info()

    for CU in dwarfinfo.iter_CUs():
        for die in CU.iter_DIEs():
            if die.tag == "DW_TAG_variable" and "DW_AT_name" in die.attributes and "DW_AT_location" in die.attributes:
                die_name = die.attributes["DW_AT_name"].value.decode("utf-8")
                die_location = die.attributes.get("DW_AT_location").value
                # Not our symbol
                if die_name != symbol.name:
                    continue
                # Constant addresses are in a list of form [0x03, addr_bytes]
                if not isinstance(die_location, list):
                    continue
                if die_location[0] != DW_OP_name2opcode["DW_OP_addr"]:
                    continue
                address = int.from_bytes(die_location[1:], "little")
                if address == symbol.entry["st_value"]:
                    return die
    return None


def dwarf_die_file_info(elf: ELFFile, die: DIE) -> tuple[str | None, int]:
    file_attr = die.attributes["DW_AT_decl_file"]
    line_attr = die.attributes["DW_AT_decl_line"]

    dwarfinfo = elf.get_dwarf_info()
    lineprogram = dwarfinfo.line_program_for_CU(die.cu)
    if lineprogram is None:
        cu_filename = None
    else:
        cu_filename = lineprogram["file_entry"][file_attr.value - 1].name.decode("latin-1")

    return cu_filename, line_attr.value


class dwarf_field:
    def __init__(
        self,
        name: str,
        tag: str,
        ctype: type[ctypes._SimpleCData] | None,
        children: list[Self] | None,
        offset: int,
    ):
        self.name = name
        self.tag = tag
        self.ctype = ctype
        if children is None:
            self.children = []
        else:
            self.children = children
        self.offset = offset


def _type_from_dwarf_info(dwarfinfo: DWARFInfo, die: DIE):
    refaddr = die.attributes["DW_AT_type"].value + die.cu.cu_offset
    return dwarfinfo.get_DIE_from_refaddr(refaddr, die.cu)


def dwarf_die_variable_inf(
    dwarfinfo: DWARFInfo, die: DIE, offset: int = 0, name_override: str | None = None
) -> dwarf_field:
    type_die = _type_from_dwarf_info(dwarfinfo, die)

    if "DW_AT_name" in die.attributes:
        field_name = die.attributes["DW_AT_name"].value.decode("utf-8")
    else:
        field_name = "<unknown>"
    if "DW_AT_name" in type_die.attributes:
        type_name = type_die.attributes["DW_AT_name"].value.decode("utf-8")
    else:
        type_name = None
    info_name = name_override if name_override is not None else field_name

    if type_die.tag == "DW_TAG_array_type":
        count = 0
        for child in type_die.iter_children():
            if child.tag == "DW_TAG_subrange_type" and "DW_AT_upper_bound" in child.attributes:
                count = child.attributes["DW_AT_upper_bound"].value + 1
        element_die = _type_from_dwarf_info(dwarfinfo, type_die)

        children = []
        element_offset = 0
        for idx in range(count):
            child = dwarf_die_variable_inf(dwarfinfo, type_die, offset + element_offset, f"{info_name}[{idx}]")
            if "DW_AT_byte_size" in element_die.attributes:
                element_offset += element_die.attributes["DW_AT_byte_size"].value
            else:
                if child.ctype is not None:
                    element_offset += ctypes.sizeof(child.ctype)
            children.append(child)

        return dwarf_field(info_name, type_die.tag, None, children, offset)
    elif type_die.tag == "DW_TAG_structure_type":
        children = []
        for child in type_die.iter_children():
            field_offset = child.attributes["DW_AT_data_member_location"].value
            child_field = dwarf_die_variable_inf(dwarfinfo, child, offset + field_offset)
            children.append(child_field)

        return dwarf_field(info_name, type_die.tag, None, children, offset)

    elif type_die.tag == "DW_TAG_union_type":
        children = []
        for child in type_die.iter_children():
            child_field = dwarf_die_variable_inf(dwarfinfo, child, offset)
            children.append(child_field)
        return dwarf_field(info_name, type_die.tag, None, children, offset)
    elif type_die.tag == "DW_TAG_typedef":
        if type_name in TYPEDEF_TO_CTYPE:
            return dwarf_field(info_name, type_die.tag, TYPEDEF_TO_CTYPE[type_name], None, offset)
        else:
            return dwarf_die_variable_inf(dwarfinfo, type_die, offset, name_override)
    elif type_die.tag == "DW_TAG_base_type":
        if type_name not in DWARF_TO_CTYPE:
            raise NotImplementedError(f"'{type_name}' not known in DWARF_TO_CTYPE")
        return dwarf_field(info_name, type_die.tag, DWARF_TO_CTYPE[type_name], None, offset)
    elif type_die.tag == "DW_TAG_pointer_type":
        return dwarf_field(info_name, type_die.tag, ctypes.c_uint32, None, offset)
    elif type_die.tag in ["DW_TAG_enumeration_type", "DW_TAG_const_type"]:
        return dwarf_die_variable_inf(dwarfinfo, type_die, offset)
    else:
        raise NotImplementedError(type_die.tag)
