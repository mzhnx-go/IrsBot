"""API 密钥加解密工具 —— AES-256-GCM 落库加密（Task 10.5）。

设计要点：
- 密钥从 settings.SECRET_KEY 派生（sha256 → 32 字节），不额外引入新密钥配置
- 密文格式 `enc:v1:<base64(nonce + ciphertext)>`：
  - 版本前缀便于未来换密钥/算法时识别与迁移
  - 可据此区分"历史明文"行，读取时原样放行，实现平滑兼容
- GCM 自带认证：密文被篡改时解密直接抛异常，不会返回脏数据
"""

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

#: 密文版本前缀
_PREFIX = "enc:v1:"

#: GCM 推荐 12 字节 nonce
_NONCE_LEN = 12


def _derive_key() -> bytes:
    """从 SECRET_KEY 派生 32 字节（256 位）AES 密钥。"""
    return hashlib.sha256(settings.SECRET_KEY.encode()).digest()


def encrypt_api_key(plaintext: str) -> str:
    """加密 API 密钥。

    每次使用随机 nonce，同一明文两次加密会得到不同密文。
    """
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(_derive_key()).encrypt(nonce, plaintext.encode(), None)
    return _PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt_api_key(stored: str) -> str:
    """解密 API 密钥；无版本前缀的历史明文原样返回（兼容旧数据）。"""
    if not stored.startswith(_PREFIX):
        return stored
    raw = base64.urlsafe_b64decode(stored[len(_PREFIX) :])
    nonce, ciphertext = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    return AESGCM(_derive_key()).decrypt(nonce, ciphertext, None).decode()
