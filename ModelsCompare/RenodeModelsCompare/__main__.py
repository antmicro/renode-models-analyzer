#
# Copyright (c) 2022-2023 Antmicro
#
# This file is licensed under the Apache License 2.0.
# Full license text is available in 'LICENSE'.
#
import json, argparse, os
from typing import Any, Iterator

from RenodeModelsCompare import report_generator, regcompare, register, models_match

def create_parsers():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(title='subcommands', dest='verb')

    summary_parser = subparsers.add_parser('summary', help='Print summary of peripheral from JSON/SVD data')
    summary_parser.add_argument("files", nargs='+', help='Files/directories to parse')
    summary_parser.add_argument('--html', nargs='?', required=False, const='report.html', help="Output summary in html format")
    summary_parser.add_argument('--include-diagnostics', action='store_true', required=False, default=False)

    compare_parser = subparsers.add_parser('compare', help='Compare peripheral models')
    compare_parser.add_argument('files', nargs='+', help='A pair of files to compare')

    misc_parser = subparsers.add_parser('misc', help='Misc helper/debugging utils')
    misc_parser.add_argument('target')
    misc_parser.add_argument('--svd-list-peripherals', action='store_true', required=False)
    misc_parser.add_argument('--is-svd-file', action='store_true', required=False)
    misc_parser.add_argument('--to-json', required=False, help='Transcribe svd peripheral to our JSON format.')

    return parser

######

def utils(args):
    if args.is_svd_file:
        print('Is SVD:', register.probe_is_file_svd(args.target))
    if args.svd_list_peripherals:
        print('Found peripherals:', [*register.svd_get_peripheral_names(args.target)])
    if args.to_json:
        if ':' in args.target:
            (file_path, peripheral) = args.target.split(':')

            register.RegistersGroup.from_svd_file(file_path, peripheral).to_json_file(args.to_json)
        else:
            print('For SVDs the syntax is: path:peripheral:', args.target)

######

def get_subfolder_file(path: str, suffix: str, name: str) -> str:
    # remember to remove extensions from name
    return os.path.join(path, f'{name}-{suffix}.json')

def select_report_gen(args) -> 'report_generator.ReportGenerator':
    return report_generator.ReportGenerator() if not args.html else report_generator.HtmlReportGenerator(args.html)

def load_files_for_report(args, file_path: str, report_gen: 'report_generator.ReportGenerator') -> bool:
    if os.path.isdir(file_path):
        # structured jsons from analyzers
        name = os.path.basename(file_path)

        if args.include_diagnostics:
            report_gen.diagnostics = []
            if os.path.exists(diag_info := get_subfolder_file(file_path, 'diagnosticInfo', name)):
                with open(diag_info) as filep:
                    report_gen.diagnostics = json.load(filep)

        if os.path.exists(reg_info := get_subfolder_file(file_path, 'registersInfo', name)):
            report_gen.load_reg_info(os.path.splitext(name)[0], register.RegistersGroup.from_json_file(reg_info)).generate_report()
    else:
        # standalone file
        if register.probe_is_file_svd(file_path):
            if ':' in file_path:
                (file_path, peripherals) = file_path.split(':')
            else:
                print('Skipping! For SVDs the syntax is: path:names,of,peripherals,to,parse:', file_path)
                return

            if ',' in peripherals:
                peripherals = peripherals.split(',')
            else:
                peripherals = [peripherals]
            
            # standalone svd file
            for peripheral in peripherals:
                report_gen.load_reg_info(peripheral, register.RegistersGroup.from_svd_file(file_path, peripheral)).generate_report()
        else:
            # standalone json file
            report_gen.load_reg_info(report_generator.ReportGenerator.file_to_peripheral_name(file_path), register.RegistersGroup.from_json_file(file_path)).generate_report()

def summarize(args):
    generator = select_report_gen(args)
    with generator as report_gen:
        for file_path in args.files:
            try:
                load_files_for_report(args, file_path, report_gen)
            except json.decoder.JSONDecodeError as error:
                print(f'Exception while parsing file "{file_path}" the file will be omitted:', error)

######

def file_to_reg_group(file_path: str) -> 'register.RegistersGroup':
    if os.path.isdir(file_path):
        name = os.path.basename(file_path)

        if os.path.exists(reg_info := get_subfolder_file(file_path, 'registersInfo', name)):
            return register.RegistersGroup.from_json_file(reg_info)
    else:
        if register.probe_is_file_svd(file_path):
            if ':' in file_path:
                (file_path, peripheral) = file_path.split(':')
            else:
                print('For SVDs the syntax is: path:peripheral:', file_path)
                return
            return register.RegistersGroup.from_svd_file(file_path, peripheral)
        else:
            return register.RegistersGroup.from_json_file(file_path)

def compare(args):
    if len(args.files) < 2:
        print('Not enough files')
        return

    file1 = args.files[0]
    files = args.files[1:]

    regs1 = file_to_reg_group(file1)

    results = []
    for file in files:
        regs2 = file_to_reg_group(file)
        if not regs2:
            continue

        print('###########')
        print('Comparing', file1, 'with', file)

        cmpr = regcompare.RegCompare(regs1, regs2)
        result = cmpr.compare_register_group_layout()

        results += [result]

    models_match.match_most_similar(results)

######

def main():
    parser = create_parsers()
    args = parser.parse_args()

    verbs = {
        'summary': summarize,
        'compare': compare,
        'misc':    utils,
    }

    if args.verb not in verbs:
        parser.print_usage()
        return 1

    verbs[args.verb](args)

if __name__ == "__main__":
    main()