"""Functions that help us work with files and folders.
"""
import json
import logging
import os
from pathlib import Path

from milc import cli

from qmk.constants import ARM_PROCESSORS, AVR_PROCESSORS
from qmk.errors import NoSuchKeyboardError
from qmk.keyboard import find_all_layouts, parse_rules_mk, parse_rules_mk_file


def arm_processor_rules(info_data, rules_mk):
    """Setup the default info for an ARM board.
    """
    info_data['processor_type'] = 'arm'
    info_data['bootloader'] = rules_mk['BOOTLOADER'] if 'BOOTLOADER' in rules_mk else 'unknown'
    info_data['processor'] = rules_mk['MCU'] if 'MCU' in rules_mk else 'unknown'
    if info_data['bootloader'] == 'unknown':
        if 'STM32' in info_data['processor']:
            info_data['bootloader'] = 'stm32-dfu'
        elif info_data.get('manufacturer') == 'Input Club':
            info_data['bootloader'] = 'kiibohd-dfu'
    if 'STM32' in info_data['processor']:
        info_data['platform'] = 'STM32'
    elif 'MCU_SERIES' in rules_mk:
        info_data['platform'] = rules_mk['MCU_SERIES']
    elif 'ARM_ATSAM' in rules_mk:
        info_data['platform'] = 'ARM_ATSAM'

    return info_data


def avr_processor_rules(info_data, rules_mk):
    """Setup the default info for an AVR board.
    """
    info_data['processor_type'] = 'avr'
    info_data['bootloader'] = rules_mk['BOOTLOADER'] if 'BOOTLOADER' in rules_mk else 'atmel-dfu'
    info_data['platform'] = rules_mk['ARCH'] if 'ARCH' in rules_mk else 'unknown'
    info_data['processor'] = rules_mk['MCU'] if 'MCU' in rules_mk else 'unknown'

    return info_data


def unknown_processor_rules(keyboard_info, rules_mk):
    """Setup the default keyboard info for unknown boards.
    """
    keyboard_info['bootloader'] = 'unknown'
    keyboard_info['platform'] = 'unknown'
    keyboard_info['processor'] = 'unknown'
    keyboard_info['processor_type'] = 'unknown'


def build_info_data(keyboard):
    """Returns a dictionary describing a keyboard, with default values.
    """
    return {
        'keyboard_name': str(keyboard),
        'keyboard_folder': str(keyboard),
        'layouts': {},
        'maintainer': 'qmk',
    }


def info_json(keyboard):
    """Generate the info.json data for a specific keyboard.
    """
    info_data = build_info_data(keyboard)

    for layout_name, layout_json in find_all_layouts(keyboard).items():
        if not layout_name.startswith('LAYOUT_kc'):
            info_data['layouts'][layout_name] = layout_json

    info_data = merge_info_jsons(keyboard, info_data)

    # Pull some keyboard information from existing rules.mk files
    rules_mk = parse_rules_mk(keyboard)

    # Setup platform specific keys
    mcu = rules_mk.get('MCU')
    if mcu in ARM_PROCESSORS:
        arm_processor_rules(info_data, rules_mk)
    elif mcu in AVR_PROCESSORS:
        avr_processor_rules(info_data, rules_mk)
    else:
        cli.log.warning("%s: Unknown MCU: %s" % (keyboard, mcu))
        unknown_processor_rules(info_data, rules_mk)

    return info_data


def merge_info_jsons(keyboard, info_data):
    """Return a merged copy of all the info.json files for a keyboard.
    """
    for info_file in find_info_json(keyboard):
        # Load and validate the JSON data
        with info_file.open('r') as info_fd:
            new_info_data = json.load(info_fd)

        if not isinstance(new_info_data, dict):
            cli.log.error("Invalid file %s, root object should be a dictionary.", str(info_file))
            continue

        # Copy whitelisted keys into `info_data`
        for key in ('keyboard_name', 'manufacturer', 'identifier', 'url', 'maintainer', 'processor', 'bootloader', 'width', 'height'):
            if key in new_info_data:
                info_data[key] = new_info_data[key]

        # Merge the layouts in
        if 'layouts' in new_info_data:
            for layout_name, json_layout in new_info_data['layouts'].items():
                # Only pull in layouts we have a macro for
                if layout_name in info_data['layouts']:
                    if len(info_data['layouts'][layout_name]['layout']) != len(json_layout['layout']):
                        cli.log.error('%s: %s: Number of elements in info.json does not match! info.json:%s != %s:%s', info_data['keyboard_folder'], layout_name, len(json_layout['layout']), layout_name, len(info_data['layouts'][layout_name]['layout']))
                    else:
                        info_data['layouts'][layout_name]['layout'] = json_layout['layout']

    return info_data


def find_info_json(keyboard):
    """Finds all the info.json files associated with a keyboard.
    """
    # Find the most specific first
    base_path = Path('keyboards')
    keyboard_path = base_path / keyboard
    keyboard_parent = keyboard_path.parent
    info_jsons = [keyboard_path / 'info.json']

    # Add DEFAULT_FOLDER before parents, if present
    rules_mk_path = Path('qmk_firmware/keyboards/%s/rules.mk' % keyboard)
    if rules_mk_path.exists():
        rules_mk = parse_rules_mk_file(rules_mk_path)
        if 'DEFAULT_FOLDER' in rules_mk:
            info_jsons.append(Path(rules_mk['DEFAULT_FOLDER']) / 'info.json')

    # Add in parent folders for least specific
    for _ in range(5):
        info_jsons.append(keyboard_parent / 'info.json')
        if keyboard_parent.parent == base_path:
            break
        keyboard_parent = keyboard_parent.parent

    # Return a list of the info.json files that actually exist
    return [info_json for info_json in info_jsons if info_json.exists()]


def keymap(keyboard):
    """Locate the correct directory for storing a keymap.

    Args:
        keyboard
            The name of the keyboard. Example: clueboard/66/rev3
    """
    for directory in ['.', '..', '../..', '../../..', '../../../..', '../../../../..']:
        basepath = os.path.normpath(os.path.join('keyboards', keyboard, directory, 'keymaps'))

        if os.path.exists(basepath):
            return basepath

    logging.error('Could not find keymaps directory!')
    raise NoSuchKeyboardError('Could not find keymaps directory for: %s' % keyboard)


def normpath(path):
    """Returns the fully resolved absolute path to a file.

    This function will return the absolute path to a file as seen from the
    directory the script was called from.
    """
    if path and path[0] == '/':
        return os.path.normpath(path)

    return os.path.normpath(os.path.join(os.environ['ORIG_CWD'], path))
