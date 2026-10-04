import argparse
from pathlib import Path
import sys

from arcaea_patcher import __version__
from arcaea_patcher.config import PatchConfig
from arcaea_patcher.core.apk_toolchain import ApkToolchain, ToolchainError
from arcaea_patcher.core.patch_pipeline import PatchPipeline
from arcaea_patcher.utils.logger import logger


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="arcaea_patcher",
        description="Modular Android APK Security & Network Routing Patcher",
    )
    parser.add_argument("input", type=Path, help="Path to original input APK file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Destination path for the patched APK file",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Optional YAML configuration file (defaults to config.yml if present)",
    )
    parser.add_argument(
        "--api-host",
        type=str,
        default=None,
        help="Custom hostname or IP for API endpoints",
    )
    parser.add_argument(
        "--auth-host",
        type=str,
        default=None,
        help="Custom hostname or IP for Authentication endpoints",
    )
    parser.add_argument(
        "--package-name",
        type=str,
        default=None,
        help="Custom package name for the patched APK",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args(argv)


def run_app() -> None:
    args = parse_args()

    config = PatchConfig.from_yaml_and_args(
        input_apk=args.input,
        output_apk=args.output,
        config_file=args.config,
        api_host=args.api_host,
        auth_host=args.auth_host,
        package_name=args.package_name,
    )

    toolchain = ApkToolchain()
    pipeline = PatchPipeline(config, toolchain)

    try:
        pipeline.execute()
    except ToolchainError as e:
        logger.error(f"Toolchain failure: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_app()