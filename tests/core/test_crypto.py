"""crypto 工具单测：AES-256-GCM 加解密与兼容行为（Task 10.5）"""

import pytest

from app.utils.crypto import decrypt_api_key, encrypt_api_key


def test_roundtrip() -> None:
    """加密后解密应还原明文"""
    secret = "sk-test-abc123"
    assert decrypt_api_key(encrypt_api_key(secret)) == secret


def test_same_plaintext_different_ciphertext() -> None:
    """随机 nonce：同一明文两次加密产生不同密文（防重放/比对）"""
    assert encrypt_api_key("sk-x") != encrypt_api_key("sk-x")


def test_ciphertext_has_version_prefix() -> None:
    """密文必须带 enc:v1: 前缀，便于识别与未来迁移"""
    assert encrypt_api_key("sk-x").startswith("enc:v1:")


def test_legacy_plaintext_passthrough() -> None:
    """历史明文行（无前缀）解密时原样返回，保证平滑兼容"""
    assert decrypt_api_key("sk-legacy-plain") == "sk-legacy-plain"


def test_tampered_ciphertext_raises() -> None:
    """密文被篡改 → GCM 认证失败抛异常，不返回脏数据"""
    ct = encrypt_api_key("sk-real")
    raw = ct[len("enc:v1:") :]
    # 篡改中间一个字符（保持 base64 填充合法）
    mid = 10
    flipped = "A" if raw[mid] != "A" else "B"
    tampered = raw[:mid] + flipped + raw[mid + 1 :]
    with pytest.raises(Exception):
        decrypt_api_key("enc:v1:" + tampered)
