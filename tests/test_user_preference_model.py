def test_user_preference_tablename() -> None:
    from app.models.user_preference import UserPreference

    assert UserPreference.__tablename__ == "user_preferences"
