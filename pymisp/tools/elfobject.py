#!/usr/bin/env python3

from __future__ import annotations

import logging

from hashlib import md5, sha1, sha256, sha512
from io import BytesIO
from pathlib import Path
from typing import Any

from . import FileObject
from .abstractgenerator import AbstractMISPObjectGenerator
from ..exceptions import InvalidMISPObject

import lief

try:
    import pydeep  # type: ignore
    HAS_PYDEEP = True
except ImportError:
    HAS_PYDEEP = False

logger = logging.getLogger('pymisp')


def make_elf_objects(lief_parsed: lief.ELF.Binary,
                     misp_file: FileObject,
                     standalone: bool = True,
                     default_attributes_parameters: dict[str, Any] = {}) -> tuple[FileObject, ELFObject, list[ELFSectionObject]]:
    elf_object = ELFObject(parsed=lief_parsed, standalone=standalone, default_attributes_parameters=default_attributes_parameters)
    misp_file.add_reference(elf_object.uuid, 'includes', 'ELF indicators')
    elf_sections = []
    for s in elf_object.sections:
        elf_sections.append(s)
    return misp_file, elf_object, elf_sections


class ELFObject(AbstractMISPObjectGenerator):

    __elf: lief.ELF.Binary

    def __init__(self, parsed: lief.ELF.Binary | None = None,  # type: ignore[no-untyped-def]
                 filepath: Path | str | None = None,
                 pseudofile: BytesIO | bytes | list[int] | None = None, **kwargs) -> None:
        """Creates an ELF object, with lief"""
        super().__init__('elf', **kwargs)
        if not HAS_PYDEEP:
            logger.warning("pydeep is missing, please install pymisp this way: pip install pymisp[fileobjects]")
        if pseudofile:
            if isinstance(pseudofile, BytesIO):
                e = lief.ELF.parse(obj=pseudofile)
            elif isinstance(pseudofile, bytes):
                e = lief.ELF.parse(raw=list(pseudofile))
            elif isinstance(pseudofile, list):
                e = lief.ELF.parse(raw=pseudofile)
            else:
                raise InvalidMISPObject(f'Pseudo file can be BytesIO or bytes got {type(pseudofile)}')
            if not e:
                raise InvalidMISPObject('Unable to parse pseudofile')
            self.__elf = e
        elif filepath:
            if e := lief.ELF.parse(filepath):
                self.__elf = e
        elif parsed:
            # Got an already parsed blob
            if isinstance(parsed, lief.ELF.Binary):
                self.__elf = parsed
            else:
                raise InvalidMISPObject(f'Not a lief.ELF.Binary: {type(parsed)}')
        self.generate_attributes()

    def generate_attributes(self) -> None:
        # General information
        self.add_attribute('type', value=str(self.__elf.header.file_type).split('.')[1])
        self.add_attribute('entrypoint-address', value=self.__elf.entrypoint)
        self.add_attribute('arch', value=str(self.__elf.header.machine_type).split('.')[1])
        self.add_attribute('os_abi', value=str(self.__elf.header.identity_os_abi).split('.')[1])
        # Sections
        self.sections = []
        if self.__elf.sections:
            pos = 0
            for section in self.__elf.sections:
                if not section.name:
                    continue
                s = ELFSectionObject(section, standalone=self._standalone, default_attributes_parameters=self._default_attributes_parameters)
                self.add_reference(s.uuid, 'includes', f'Section {pos} of ELF')
                pos += 1
                self.sections.append(s)
        self.add_attribute('number-sections', value=len(self.sections))


class ELFSectionObject(AbstractMISPObjectGenerator):

    def __init__(self, section: lief.ELF.Section, **kwargs) -> None:  # type: ignore[no-untyped-def]
        """Creates an ELF Section object. Object generated by ELFObject."""
        # Python3 way
        # super().__init__('pe-section')
        super().__init__('elf-section', **kwargs)
        self.__section = section
        self.__data = bytes(self.__section.content)
        self.generate_attributes()

    def generate_attributes(self) -> None:
        self.add_attribute('name', value=self.__section.name)
        self.add_attribute('type', value=str(self.__section.type).split('.')[1])
        for flag in self.__section.flags_list:
            self.add_attribute('flag', value=str(flag).split('.')[1])
        self.add_attribute('size-in-bytes', value=self.__section.size)
        if int(self.__section.size) > 0:
            self.add_attribute('entropy', value=self.__section.entropy)
            self.add_attribute('md5', value=md5(self.__data).hexdigest())
            self.add_attribute('sha1', value=sha1(self.__data).hexdigest())
            self.add_attribute('sha256', value=sha256(self.__data).hexdigest())
            self.add_attribute('sha512', value=sha512(self.__data).hexdigest())
            if HAS_PYDEEP:
                self.add_attribute('ssdeep', value=pydeep.hash_buf(self.__data).decode())
