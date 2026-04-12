"""User management CLI backed by the canonical backend services."""
from __future__ import annotations

import argparse
from pathlib import Path

from backend.app.container import AppContainer
from backend.app.core.logging import configure_logging
from backend.app.core.settings import settings


def _prompt(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default


def _load_samples(paths: list[str]) -> list[tuple[str, bytes]]:
    uploads: list[tuple[str, bytes]] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise ValueError(f"Audio file not found: {path}")
        uploads.append((path.name, path.read_bytes()))
    return uploads


def _collect_interactive_audio_paths() -> list[str]:
    print("Enter at least 3 audio file paths. Submit an empty line to finish.")
    paths: list[str] = []
    while True:
        value = input(f"Audio file {len(paths) + 1}: ").strip()
        if not value:
            if len(paths) >= 3:
                return paths
            print("At least 3 audio samples are required.")
            continue
        paths.append(value)


def _preferences_from_args(args: argparse.Namespace) -> dict[str, float]:
    return {
        "pitch_scale": args.pitch_scale,
        "speaking_rate": args.speaking_rate,
        "energy_scale": args.energy_scale,
    }


def list_users() -> None:
    container = AppContainer(settings)
    try:
        users = container.users.list_users()
    finally:
        container.close()

    if not users:
        print("No enrolled users found.")
        return

    for user in users:
        embedding = "yes" if user["has_embedding"] else "no"
        print(f'{user["user_id"]}\t{user["display_name"]}\tembedding={embedding}')


def register_user(
    display_name: str,
    audio_paths: list[str],
    group_identifier: str | None,
    preferences: dict[str, float],
    replace: bool = False,
) -> None:
    uploads = _load_samples(audio_paths)
    container = AppContainer(settings)
    try:
        existing = container.users.get_user(container.users._slugify_user_id(display_name))
        if existing and not replace:
            raise ValueError(f"User '{existing['user_id']}' already exists. Use --replace to overwrite.")
        if existing and replace:
            container.users.delete_user(existing["user_id"])
        user = container.users.register_user(display_name, group_identifier, preferences, uploads)
    finally:
        container.close()

    print(f"Enrolled {user['display_name']} ({user['user_id']})")


def interactive_register() -> None:
    display_name = _prompt("Display name")
    group_identifier = _prompt("Group identifier", "") or None
    pitch_scale = float(_prompt("Pitch scale", "1.0"))
    speaking_rate = float(_prompt("Speaking rate", "1.0"))
    energy_scale = float(_prompt("Energy scale", "1.0"))
    replace = _prompt("Replace existing user? (yes/no)", "no").lower() in {"y", "yes"}
    audio_paths = _collect_interactive_audio_paths()
    register_user(
        display_name=display_name,
        audio_paths=audio_paths,
        group_identifier=group_identifier,
        preferences={
            "pitch_scale": pitch_scale,
            "speaking_rate": speaking_rate,
            "energy_scale": energy_scale,
        },
        replace=replace,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage enrolled voice users.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list", help="List enrolled users")

    enroll = subparsers.add_parser("register", help="Register a user from audio samples")
    enroll.add_argument("display_name")
    enroll.add_argument("audio_paths", nargs="+")
    enroll.add_argument("--group-identifier")
    enroll.add_argument("--pitch-scale", type=float, default=1.0)
    enroll.add_argument("--speaking-rate", type=float, default=1.0)
    enroll.add_argument("--energy-scale", type=float, default=1.0)
    enroll.add_argument("--replace", action="store_true")

    batch = subparsers.add_parser("batch", help="Alias for register")
    batch.add_argument("display_name")
    batch.add_argument("audio_paths", nargs="+")
    batch.add_argument("--group-identifier")
    batch.add_argument("--pitch-scale", type=float, default=1.0)
    batch.add_argument("--speaking-rate", type=float, default=1.0)
    batch.add_argument("--energy-scale", type=float, default=1.0)
    batch.add_argument("--replace", action="store_true")

    return parser


def main() -> None:
    configure_logging(settings.log_level)
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        interactive_register()
        return

    if args.command == "list":
        list_users()
        return

    if args.command in {"register", "batch"}:
        register_user(
            display_name=args.display_name,
            audio_paths=args.audio_paths,
            group_identifier=args.group_identifier,
            preferences=_preferences_from_args(args),
            replace=args.replace,
        )
        return

    parser.error(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
