#
# Copyright (c) 2022-2023 Antmicro
#
# This file is licensed under the Apache License 2.0.
# Full license text is available in 'LICENSE'.
#
import abc
import json
import xmltodict
import os
from typing import Any, Iterator, List

def _wrap_in_list(obj: Any) -> List[Any]:
    return [obj] if not isinstance(obj, list) else obj

def to_json_simple(obj: Any) -> str:
    if hasattr(obj, 'to_json'):
        return obj.to_json()
    raise TypeError(f'Object of type {type(obj).__name__} does not contain to_json method')

def probe_is_file_svd(file_path: str) -> bool:
    # syntax for selecting peripheral within svd
    if ':' in file_path:
        (file_path) = file_path.split(':')[0]
    with open(file_path, 'r') as filep:
        first_line = filep.readline()
        return '<?xml' in first_line
    
def svd_get_peripheral_names(file_path: str) -> Iterator[str]:
    with open(file_path, 'r') as file:
        svd = xmltodict.parse(file.read())

    for peripheral in _wrap_in_list(svd['device']['peripherals']['peripheral']):
        yield peripheral['name']

class _CommonBase(abc.ABC):
    def get_kinds(self) -> List[str]:
        return list(map(lambda s: s.strip(), self.raw_data['SpecialKind'].split(',')))

    def is_any_special_kind(self, *kinds: str) -> bool:
        reg_kinds = self.get_kinds()
        return any(kind in reg_kinds for kind in kinds)

    def get_width(self) -> 'int|None':
        if self.is_any_special_kind('VariableLength', 'VariablePosition'):
            return None
        return self.raw_data["Range"]["End"] - self.raw_data["Range"]["Start"] + 1

    def get_callback_info(self) -> List[str]:
        shorts = {
            "HasReadCb":            'Read',
            "HasWriteCb":           'Write',
            "HasChangeCb":          'Change',
            "HasValueProviderCb":   'Provider',
        }
        rets = []
        for short, present in self.raw_data['CallbackInfo'].items():
            if present:
                rets.append(shorts[short])

        return rets

#NOTE: if using _CommonBase store dict in variable named raw_data
class Field(_CommonBase):
    def __init__(self, field: dict) -> None:
        self.raw_data = field

    def __getitem__(self, key: str) -> dict:
        if key == 'FieldMode':
            raise KeyError('Use get_field_modes instead')
        return self.raw_data[key]

    def to_json(self) -> dict:
        return self.raw_data

    def get_field_modes_str(self) -> str:
        if not (modes := self.get_field_modes()):
            return 'N/A'
        else:
            return (', '.join(modes)) or (self.raw_data["FieldMode"])

    # TODO: enum ???
    def get_field_modes(self) -> 'List[str]':
        if self.is_any_special_kind('Tag', 'Reserved'):
            return []
        return [s.strip().replace('FieldMode.', '') for s in self.raw_data["FieldMode"].split('|')]

    @staticmethod
    def _map_svd_access_to_renode_access(access: str) -> str:
        # TODO: this list definitely needs to be expanded but we will get KeyError here, so we will know
        return {
            'read-only'  : 'Read',
            'write-only' : 'Write',
            'read-write' : 'Read, Write',
        }[access]

    @classmethod
    def from_svd_fragment(cls, field_fragment: 'svd|dict', uniq_id: int, reg_access: str = '???') -> 'Field':
        access = field_fragment.get('access') or reg_access

        def _get_start(fragment):
            if 'bitOffset' in fragment:
                return int(field_fragment['bitOffset'], 10)
            elif 'lsb':
                return int(field_fragment['lsb'], 10)
            else:
                raise LookupError('RangeStart')

        def _get_end(fragment):
            if 'bitWidth' in fragment:
                return int(field_fragment['bitOffset'], 10) + int(field_fragment['bitWidth'], 10) - 1
            elif 'msb':
                return int(field_fragment['msb'], 10)
            else:
                raise LookupError('RangeEnd')

        return cls({
            'UniqueId':         uniq_id,
            'Name':             ((r := field_fragment.get('displayName')) and r.strip()) or field_fragment['name'].strip(),
            'Description':      field_fragment.get('description'),
            'Range': {
                'Start':        _get_start(field_fragment),
                'End':          _get_end(field_fragment)
            },
            'BlockId':          0,      # does not translate
            'GeneratorName':    None,   # neither this - PROPOSAL far future TODO: put code here that would generate the register in Renode
            'SpecialKind':      '',
            'CallbackInfo':     dict(),
            'FieldMode':        cls._map_svd_access_to_renode_access(access),
        })

class Register(_CommonBase):
    def __init__(self, reg: dict) -> None:
        self.raw_data = reg

    def __getitem__(self, key: str) -> dict:
        return self.raw_data[key]

    def to_json(self) -> dict:
        return self.raw_data

    @property
    def Offset(self) -> int:
        return self.raw_data['Address']

    @property
    def Name(self) -> str:
        return self.raw_data['Name']

    @property
    def Fields(self) -> str:
        return self.raw_data['Fields']
    
    def get_width(self) -> 'int|None':
        if self.is_any_special_kind('VariableLength', 'VariablePosition'):
            return None
        return self.raw_data['Width']

    @classmethod
    def _get_fields_from_svd_fragment(cls, fields_svd_fragment: 'svd|dict', reg_access: str = '???') -> dict:
        rets = []
        id = 0
        for field in fields_svd_fragment:
            rets.append(Field.from_svd_fragment(field, id, reg_access))
            id += 1

        return rets

    @classmethod
    def from_json_fragment(cls, register: dict) -> 'Register':
        register_cpy = register.copy()
        fields = [Field(f) for f in register['Fields']]
        register_cpy['Fields'] = fields

        return cls(register_cpy)

    @classmethod
    def from_svd_fragment(cls, register: 'svd|dict') -> 'Register':
        def _int_or_none(fragment, alt=None):
            if fragment in register:
                return int(register[fragment], 16)
            return alt

        def get_width(fragment):
            if 'size' in fragment:
                return _int_or_none('size')
            elif 'width' in fragment:
                return _int_or_none('width')
            else:
                return 64 # FIXME nrf52840.svd!!!

        return cls({ 
                'Name':         ((r := register.get('displayName')) and r.strip()) or register['name'].strip(),
                'Description':  register.get('description'),
                'Address':      int(register['addressOffset'], 16),
                'Width':        get_width(register),
                'ResetValue':   _int_or_none('resetValue'),
                'ParentReg':    None,    # TODO: dim, dimIncrement - used to denote derivative registers (DefineMany)
                'SpecialKind':  '',      # none currently
                'CallbackInfo': dict(),
                'Fields':       cls._get_fields_from_svd_fragment(_wrap_in_list(register['fields']['field']), register.get('access', '???')),
        })

class RegistersGroup:
    def __init__(self, regs: List[Register], *, name: str = '') -> None:
        self.raw_data = sorted(regs, key = lambda r: r.Offset)
        self.name = name

    def __getitem__(self, key: str) -> Register:
        return self.raw_data[key]

    def __len__(self) -> int:
        return len(self.raw_data)

    @classmethod
    def from_json_file(cls, file_path: str) -> 'RegistersGroup':
        with open(file_path, 'r') as filep:
            regs = json.load(filep)
        return cls([Register.from_json_fragment(r) for r in regs], name=os.path.basename(file_path))

    @classmethod
    def from_svd_file(cls, file_path: str, peripheral_name: str) -> 'RegistersGroup':
        registers = None

        with open(file_path, 'r') as file:
            svd = xmltodict.parse(file.read())

        for peripheral in _wrap_in_list(svd['device']['peripherals']['peripheral']):
            if peripheral['name'] == peripheral_name:
                if registers:
                    print('Many peripherals of the same name, SVD is malformed. Selecting the first one.')
                    break
                registers = []

                for register in _wrap_in_list(peripheral['registers']['register']):
                    registers.append(Register.from_svd_fragment(register))

        # we extracted no data
        if registers is None:
            raise LookupError(f'The peripheral named "{peripheral_name}" does not exist in this file.')

        return cls(registers, name=peripheral_name)

    def to_json_file(self, file_path: str) -> None:
        with open(file_path, 'w') as file:
            json.dump(self.raw_data, file, default=to_json_simple, indent=2)
