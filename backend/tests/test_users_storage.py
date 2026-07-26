import sqlite3

from backend.app.integrations.sqlite_users import (
    delete_tts_preferences,
    delete_user_profile,
    get_tts_preferences,
    get_user_profile,
    initialize_database,
    list_tts_preference_users,
    list_user_profiles,
    save_tts_preferences,
    save_user_profile,
)


def test_user_database_has_only_profiles_and_voice_preferences(tmp_path):
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
    assert tables == {"user_profiles", "user_tts_preferences"}


def test_profile_and_preferences_round_trip(tmp_path):
    database = tmp_path / "users.db"
    initialize_database(database)

    assert save_user_profile("ada", "Ada", "group-a", database)
    assert save_tts_preferences(
        "ada",
        {
            "pitch_scale": 1.1,
            "speaking_rate": 0.9,
            "energy_scale": 1.2,
            "style": "af_heart",
        },
        database,
    )

    assert get_user_profile("ada", database)["display_name"] == "Ada"
    assert get_tts_preferences("ada", database)["style"] == "af_heart"
    assert [row["user_id"] for row in list_user_profiles(database)] == ["ada"]
    assert list_tts_preference_users(database) == ["ada"]

    assert delete_tts_preferences("ada", database)
    assert delete_user_profile("ada", database)
    assert get_user_profile("ada", database) is None
