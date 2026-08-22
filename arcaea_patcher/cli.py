import argparse
from pathlib import Path
from arcaea_patcher.config import PatchConfig
from arcaea_patcher.core.apk_toolchain import ApkToolchain
from arcaea_patcher.core.patch_pipeline import PatchPipeline
from arcaea_patcher.utils.logger import logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="apk_patcher",
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
        help="Optional YAML configuration file for custom settings",
    )
    parser.add_argument(
        "--api-host",
        type=str,
        default=None,
        help="Custom hostname to replace API endpoints",
    )
    parser.add_argument(
        "--auth-host",
        type=str,
        default=None,
        help="Custom hostname to replace Authentication endpoints",
    )
    return parser.parse_args()


def run_app() -> None:
    args = parse_args()

    config = PatchConfig.from_yaml_and_args(
        input_apk=args.input,
        output_apk=args.output,
        config_file=args.config,
        api_host=args.api_host,
        auth_host=args.auth_host,
    )

    toolchain = ApkToolchain()
    pipeline = PatchPipeline(config, toolchain)

    try:
        pipeline.execute()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise SystemExit(1)