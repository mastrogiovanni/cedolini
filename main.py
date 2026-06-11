"""CLI for cedolino (Italian payslip) PDF parsing.

Commands
--------
list-plugins          List all available plugins.
detect  <file>        Detect which plugin handles a PDF.
parse   <file>        Extract data from a cedolino PDF and print JSON.
  --plugin NAME       Force a specific plugin (skip auto-detection).
  --output FILE       Write JSON to FILE instead of stdout.
"""

import argparse
import json
import sys

import plugins


def cmd_list_plugins(args: argparse.Namespace) -> int:
    all_plugins = plugins.list_plugins()
    if not all_plugins:
        print("No plugins registered.")
        return 0
    width = max(len(name) for name, _ in all_plugins)
    for name, desc in all_plugins:
        print(f"  {name:<{width}}  {desc}")
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    plugin = plugins.detect(args.file)
    if plugin is None:
        print(f"No plugin found for: {args.file}", file=sys.stderr)
        return 1
    print(f"Plugin:      {plugin.name}")
    print(f"Description: {plugin.description}")
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    pdf_path = args.file

    if args.plugin:
        plugin = plugins.get_plugin(args.plugin)
        if plugin is None:
            print(f"Unknown plugin: {args.plugin}", file=sys.stderr)
            print(f"Available: {[n for n, _ in plugins.list_plugins()]}", file=sys.stderr)
            return 1
        if not plugin.can_handle(pdf_path):
            print(f'Warning: plugin "{args.plugin}" reports it cannot handle {pdf_path}', file=sys.stderr)
    else:
        plugin = plugins.detect(pdf_path)
        if plugin is None:
            print(f"No plugin detected for: {pdf_path}", file=sys.stderr)
            print("Use --plugin NAME to force a plugin.", file=sys.stderr)
            return 1
        print(f"Using plugin: {plugin.name}", file=sys.stderr)

    data = plugin.extract(pdf_path)
    text = json.dumps(data, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(text)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cedolini",
        description="Parse Italian payslip (cedolino) PDFs into structured JSON.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    sub.add_parser("list-plugins", help="List all available plugins")

    p_detect = sub.add_parser("detect", help="Detect which plugin handles a PDF")
    p_detect.add_argument("file", help="Path to the PDF file")

    p_parse = sub.add_parser("parse", help="Extract data from a cedolino PDF")
    p_parse.add_argument("file", help="Path to the PDF file")
    p_parse.add_argument("--plugin", metavar="NAME", help="Force a specific plugin")
    p_parse.add_argument("--output", metavar="FILE", help="Write JSON to FILE (default: stdout)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    handlers = {
        "list-plugins": cmd_list_plugins,
        "detect": cmd_detect,
        "parse": cmd_parse,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
