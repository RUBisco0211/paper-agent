"""弱密钥检查：占位符与低熵密钥不能带进生产。"""

import pytest

from app.platform.config import MIN_JWT_SECRET_CHARS, Settings

# 形如 `openssl rand -hex 32` 的真实随机值
STRONG = "3f9a1c7e5b2d8046af93c1e7b5d20a84" + "6c0f9b3e7a1d5428ec93b6f01a7d2e58"


@pytest.mark.parametrize(
    ("secret", "problem"),
    [
        ("", "placeholder"),
        ("change-me", "placeholder"),
        ("replace-with-openssl-rand-hex-32", "placeholder"),
        ("12345", "too_short"),
        # 长度先判定：短密钥无论字符多杂都不合格
        ("x" * (MIN_JWT_SECRET_CHARS - 1), "too_short"),
        ("a" * 64, "low_entropy"),
        (STRONG, None),
    ],
)
def test_jwt_secret_problem(secret: str, problem: str | None) -> None:
    assert Settings(jwt_secret_key=secret).jwt_secret_problem == problem


def test_strong_secret_is_accepted() -> None:
    assert Settings(jwt_secret_key=STRONG).jwt_secret_problem is None


def test_startup_refuses_a_weak_secret_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开发环境只记错误日志，生产环境必须拒绝启动。"""
    from app import main

    monkeypatch.setattr(main.settings, "jwt_secret_key", "12345", raising=False)

    monkeypatch.setattr(main.settings, "environment", "development", raising=False)
    main.check_jwt_secret()  # 不抛异常

    monkeypatch.setattr(main.settings, "environment", "production", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        main.check_jwt_secret()


def test_startup_accepts_a_strong_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main

    monkeypatch.setattr(main.settings, "jwt_secret_key", STRONG, raising=False)
    monkeypatch.setattr(main.settings, "environment", "production", raising=False)

    main.check_jwt_secret()
