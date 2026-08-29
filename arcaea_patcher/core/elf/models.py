from dataclasses import dataclass


@dataclass
class SectionHeader:
    """ELF section header."""

    name_idx: int
    sh_type: int
    sh_flags: int
    sh_addr: int
    sh_offset: int
    sh_size: int
    sh_link: int
    sh_info: int
    sh_addralign: int
    sh_entsize: int


@dataclass
class ProgramHeader:
    """ELF program header."""

    p_type: int
    p_offset: int
    p_vaddr: int
    p_paddr: int
    p_filesz: int
    p_memsz: int
    p_flags: int
    p_align: int