import argparse
import json
import logging
import sys

from .inspection import InspectionError, inspect_scene


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InspectionError("invalid_arguments", message)


def main(argv: list[str] | None = None) -> int:
    parser = JsonArgumentParser(prog="python -m tessera_x.ingestion", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "ingest", "prepare-cog"):
        subparser = commands.add_parser(command, allow_abbrev=False)
        subparser.add_argument("path")
        for name in ("scene-id", "platform", "sensor", "acquisition-time", "ingestion-release"):
            subparser.add_argument(f"--{name}", required=True)
        subparser.add_argument("--cloud-cover", type=float)
        if command == "ingest":
            subparser.add_argument("--store", required=True)
            subparser.add_argument("--patch-size", type=int, default=256)
        elif command == "prepare-cog":
            subparser.add_argument("destination")
    show = commands.add_parser("show", allow_abbrev=False)
    show.add_argument("scene_id")
    show.add_argument("--store", required=True)
    logging.getLogger("rasterio").addHandler(logging.NullHandler())
    logging.getLogger("rasterio").propagate = False
    try:
        args = vars(parser.parse_args(argv))
        command = args.pop("command")
        if command == "inspect":
            result = inspect_scene(**args).model_dump(mode="json")
        elif command == "prepare-cog":
            from .cog import prepare_cog

            args["source"] = args.pop("path")
            result = prepare_cog(**args).model_dump(mode="json")
        else:
            from .catalog import ingest_scene, load_scene

            args["root"] = args.pop("store")
            result = ingest_scene(**args) if command == "ingest" else load_scene(**args)
        print(json.dumps(result, allow_nan=False))
        return 0
    except InspectionError as error:
        print(json.dumps({"error": {"code": error.code, "message": str(error)}}), file=sys.stderr)
        return 2
    except (ValueError, OSError) as error:
        print(
            json.dumps({"error": {"code": "ingestion_failed", "message": str(error)}}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
