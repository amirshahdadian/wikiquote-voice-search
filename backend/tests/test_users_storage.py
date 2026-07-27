import sqlite3
from types import SimpleNamespace

import numpy as np

from backend.config import Settings
from backend.users import UserService, get_tts_preferences, initialize_database


class FakeSpeaker:
    def __init__(self):
        self.enrolled: list[list[str]] = []

    def enroll_speaker(self, paths):
        self.enrolled.append(paths)
        return np.zeros(256, dtype=np.float32)

    @staticmethod
    def save_embedding(embedding, file_path):
        from backend.voice import SpeakerIdentificationService

        SpeakerIdentificationService.save_embedding(embedding, file_path)


def service(tmp_path) -> UserService:
    app_settings = Settings(
        _env_file=None, data_dir=tmp_path, db_path=tmp_path / "users.db"
    )
    return UserService(app_settings, speaker_service=FakeSpeaker())


def samples(count: int = 3) -> list[tuple[str, bytes]]:
    return [(f"s{index}.wav", b"RIFF") for index in range(count)]


def test_speaker_identification_dependency_imports():
    import resemblyzer

    assert resemblyzer is not None


def test_one_table_holds_the_profile_and_its_voice_settings(tmp_path):
    database = tmp_path / "users.db"

    initialize_database(database)

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(user_profiles)")
        }
    assert tables == {"user_profiles"}
    assert columns == {
        "user_id",
        "display_name",
        "group_identifier",
        "speaking_rate",
        "energy_scale",
        "style",
    }
    assert not {"created_at", "updated_at", "pitch_scale"} & columns


def test_registration_round_trip(tmp_path):
    users = service(tmp_path)

    profile = users.register_user(
        "Ada Lovelace", "group-a", {"speaking_rate": 0.9, "energy_scale": 1.2}, samples()
    )

    assert profile["user_id"] == "ada-lovelace"
    assert profile["display_name"] == "Ada Lovelace"
    assert profile["group_identifier"] == "group-a"
    assert profile["has_embedding"] is True
    assert profile["preferences"]["speaking_rate"] == 0.9
    assert profile["preferences"]["style"]
    assert users.get_user("ada-lovelace") == profile
    assert [item["user_id"] for item in users.list_users()] == ["ada-lovelace"]


def test_voice_preferences_are_readable_by_the_synthesizer(tmp_path):
    users = service(tmp_path)
    users.register_user("Ada", None, {"speaking_rate": 1.1, "energy_scale": 1.0}, samples())

    preferences = get_tts_preferences("ada", users.db_path)

    assert preferences["speaking_rate"] == 1.1
    assert set(preferences) == {"speaking_rate", "energy_scale", "style"}
    assert get_tts_preferences("nobody", users.db_path) is None


def test_each_user_is_given_a_different_voice(tmp_path):
    users = service(tmp_path)

    first = users.register_user("Ada", None, {}, samples())
    second = users.register_user("Grace", None, {}, samples())

    assert first["preferences"]["style"] != second["preferences"]["style"]


def test_deleting_a_user_removes_the_row_and_the_voice_vector(tmp_path):
    users = service(tmp_path)
    users.register_user("Ada", None, {}, samples())
    vector = tmp_path / "embeddings" / "ada.pkl"
    assert vector.exists()

    users.delete_user("ada")

    assert users.get_user("ada") is None
    assert not vector.exists()


def test_re_enrollment_replaces_the_vector_and_keeps_the_profile(tmp_path):
    users = service(tmp_path)
    users.register_user("Ada", None, {"speaking_rate": 0.8}, samples())
    voice = users.get_user("ada")["preferences"]["style"]

    users.re_enroll_user("ada", samples(4))

    assert users.speaker_service.enrolled[-1] and len(users.speaker_service.enrolled[-1]) == 4
    assert users.get_user("ada")["preferences"]["style"] == voice
    assert users.get_user("ada")["preferences"]["speaking_rate"] == 0.8


def test_unknown_and_duplicate_users_are_explicit(tmp_path):
    users = service(tmp_path)
    users.register_user("Ada", None, {}, samples())

    for call in (
        lambda: users.re_enroll_user("nobody", samples()),
        lambda: users.delete_user("nobody"),
    ):
        try:
            call()
        except KeyError:
            pass
        else:
            raise AssertionError("expected KeyError")

    try:
        users.register_user("Ada", None, {}, samples())
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_enrollment_temp_files_are_cleaned_up(tmp_path):
    users = service(tmp_path)

    users.register_user("Ada", None, {}, samples())

    from pathlib import Path

    assert all(not Path(p).exists() for p in users.speaker_service.enrolled[0])
