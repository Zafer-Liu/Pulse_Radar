"""小红书 X-s 签名算法（XYS_ 格式，mns0301 版本）

纯 Python 实现，不依赖任何第三方库（仅使用 Python 标准库）。
基于 Cloxl/xhshow 逆向分析。

主要导出：
    sign(uri, a1, params=None, method="GET")  -- 生成 X-s 签名
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import random
import struct
import time
from typing import Optional
from urllib.parse import urlencode, quote

logger = logging.getLogger("xhs_sign")

# ============================================================
# 常量
# ============================================================

HEX_KEY = bytes.fromhex(
    "71a302257793271ddd273bcee3e4b98d"
    "9d7935e1da33f5765e2ea8afb6dc77a5"
    "1a499d23b67c20660025860cbf13d454"
    "0d92497f58686c574e508f46e1956344"
    "f39139bf4faf22a3eef120b79258145b"
    "2feb5193b6478669961298e79bedca64"
    "6e1a693a926154a5a7a1bd1cf0dedb74"
    "2f917a747a1e388b234f2277516db711"
    "6035439730fa61e9822a0eca7bff72d8"
)

CUSTOM_B64 = "ZmserbBoHQtNP+wOcza/LpngG8yJq42KWYj0DSfdikx3VT16IlUAFM97hECvuRX5"

X3_B64 = "MfgqrsbcyzPQRStuvC7mn501HIJBo2DEFTKdeNOwxWXYZap89+/A4UVLhijkl63G"

STD_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

ENV_TABLE = [115, 248, 83, 102, 103, 201, 181, 131, 99, 94, 4, 68, 250, 132, 21]

ENV_CHECKS = [0, 1, 18, 1, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0]

HASH_IV = (1831565813, 461845907, 2246822507, 3266489909)

VERSION_BYTES = [121, 104, 96, 41]

A3_PREFIX = [2, 97, 51, 16]


# ============================================================
# 辅助函数
# ============================================================

def rotl32(v: int, n: int) -> int:
    """32 位循环左移。"""
    return ((v << n) | (v >> (32 - n))) & 0xFFFFFFFF


def int_to_le(val: int, length: int) -> list[int]:
    """整数转小端字节列表。"""
    result = []
    for _ in range(length):
        result.append(val & 0xFF)
        val >>= 8
    return result


def b64_custom(data: bytes, alphabet: str) -> str:
    """使用自定义字母表进行 Base64 编码。"""
    std = base64.b64encode(data).decode()
    table = str.maketrans(STD_B64, alphabet)
    return std.translate(table)


def custom_hash_v2(data: bytes) -> list[int]:
    """自定义哈希函数 v2，返回 16 字节列表。"""
    s0, s1, s2, s3 = HASH_IV
    length = len(data)
    s0 ^= length
    s1 ^= (length << 8) & 0xFFFFFFFF
    s2 ^= (length << 16) & 0xFFFFFFFF
    s3 ^= (length << 24) & 0xFFFFFFFF

    # 按 8 字节块处理
    for i in range(length // 8):
        chunk = bytes(data[i * 8 : (i + 1) * 8])
        v0, v1 = struct.unpack("<II", chunk)
        s0 = rotl32(((s0 + v0) & 0xFFFFFFFF) ^ s2, 7)
        s1 = rotl32(((v0 ^ s1) + s3) & 0xFFFFFFFF, 11)
        s2 = rotl32(((s2 + v1) & 0xFFFFFFFF) ^ s0, 13)
        s3 = rotl32(((s3 ^ v1) + s1) & 0xFFFFFFFF, 17)

    # 最终混淆
    t0 = s0 ^ length
    t1 = s1 ^ t0
    t2 = (s2 + t1) & 0xFFFFFFFF
    t3 = s3 ^ t2

    r0 = rotl32(t0, 9)
    r1 = rotl32(t1, 13)
    r2 = rotl32(t2, 17)
    r3 = rotl32(t3, 19)

    s0 = (r0 + r2) & 0xFFFFFFFF
    s1 = r1 ^ r3
    s2 = (r2 + s0) & 0xFFFFFFFF
    s3 = r3 ^ s1

    result: list[int] = []
    for s in [s0, s1, s2, s3]:
        result.extend(int_to_le(s, 4))
    return result


# ============================================================
# 签名主函数
# ============================================================

def sign(
    uri: str,
    a1: str,
    params: Optional[dict] = None,
    method: str = "GET",
) -> str:
    """生成小红书 X-s 签名（XYS_ 格式）。

    Args:
        uri: 请求路径（如 /api/sns/web/v1/feed）
        a1: Cookie 中的 a1 值
        params: GET 请求的查询参数字典（POST 时忽略）
        method: HTTP 方法，"GET" 或 "POST"

    Returns:
        X-s 签名字符串，格式为 "XYS_..."
    """
    now_ms = int(time.time() * 1000)
    seed = random.randint(0, 0xFFFFFFFF)
    seed_byte = seed & 0xFF

    # ----------------------------------------------------------
    # 1. 构建 content_string
    # ----------------------------------------------------------
    if method.upper() == "GET" and params:
        # 排序参数并 URL 编码
        sorted_params = sorted(params.items())
        query = urlencode(sorted_params, quote_via=quote)
        content_string = f"{uri}?{query}"
    elif method.upper() == "GET":
        content_string = uri
    else:
        # POST: content_string = uri（不含 body，body 签名在 m_value 中体现）
        content_string = uri

    # ----------------------------------------------------------
    # 2. 计算 MD5
    # ----------------------------------------------------------
    d_value = hashlib.md5(content_string.encode("utf-8")).hexdigest()

    if method.upper() == "GET":
        m_value = d_value
    else:
        m_value = hashlib.md5(uri.encode("utf-8")).hexdigest()

    # ----------------------------------------------------------
    # 3. 构建 144 字节 payload
    # ----------------------------------------------------------
    payload = bytearray(144)

    # [0:4] VERSION_BYTES
    payload[0:4] = VERSION_BYTES

    # [4:8] seed（小端序）
    payload[4:8] = int_to_le(seed, 4)

    # [8:16] timestamp_ms（小端序）
    payload[8:16] = int_to_le(now_ms, 8)

    # [16:24] page_load_timestamp（时间偏移后的毫秒时间戳）
    page_load_ts = now_ms - random.randint(1000, 300000)
    payload[16:24] = int_to_le(page_load_ts, 8)

    # [24:28] sequence_value（15~50 之间的随机数）
    seq_val = random.randint(15, 50)
    payload[24:28] = int_to_le(seq_val, 4)

    # [28:32] window_props_length（1000~1200）
    win_props = random.randint(1000, 1200)
    payload[28:32] = int_to_le(win_props, 4)

    # [32:36] uri_length（content_string 的 UTF-8 字节长度）
    uri_len = len(content_string.encode("utf-8"))
    payload[32:36] = int_to_le(uri_len, 4)

    # [36:44] MD5 前 8 字节 ^ seed_byte
    md5_bytes = bytes.fromhex(d_value[:16])
    for i in range(8):
        payload[36 + i] = md5_bytes[i] ^ seed_byte

    # [44] a1 长度标记
    a1_bytes = a1.encode("utf-8")[:52]
    payload[44] = 52

    # [45:97] a1 值（补零到 52 字节）
    a1_padded = a1_bytes.ljust(52, b"\x00")
    payload[45:97] = a1_padded

    # [97] app_id 长度标记
    payload[97] = 10

    # [98:108] app_identifier（"xhs-pc-web" 补零到 10 字节）
    app_id = b"xhs-pc-web".ljust(10, b"\x00")
    payload[98:108] = app_id

    # [108:123] ENV_TABLE ^ ENV_CHECKS（第一个元素特殊处理）
    env_checks = ENV_CHECKS[:]
    env_checks[0] = 1
    env_checks[1] = seed_byte ^ ENV_TABLE[0]
    for i in range(15):
        payload[108 + i] = ENV_TABLE[i] ^ env_checks[i]

    # [123:127] A3_PREFIX
    payload[123:127] = A3_PREFIX

    # [127:140] custom_hash_v2(timestamp_bytes + md5_path_bytes) 前 13 字节 ^ seed_byte
    timestamp_bytes = int_to_le(now_ms, 8)
    md5_path_bytes = list(d_value.encode("utf-8"))
    hash_input = bytes(timestamp_bytes + md5_path_bytes)
    hash_result = custom_hash_v2(hash_input)
    for i in range(13):
        payload[127 + i] = hash_result[i] ^ seed_byte

    # [140:144] 补零（已有默认值 0）

    # ----------------------------------------------------------
    # 4. XOR 变换
    # ----------------------------------------------------------
    for i in range(144):
        payload[i] ^= HEX_KEY[i]

    # ----------------------------------------------------------
    # 5. X3 Base64 编码
    # ----------------------------------------------------------
    x3_sig = b64_custom(bytes(payload), X3_B64)

    # ----------------------------------------------------------
    # 6. 组装最终签名
    # ----------------------------------------------------------
    sig_data = {
        "x0": "4.3.5",
        "x1": "xhs-pc-web",
        "x2": "Windows",
        "x3": f"mns0301_{x3_sig}",
        "x4": "object",
    }
    json_str = json.dumps(sig_data, separators=(",", ":"))
    signature = "XYS_" + b64_custom(json_str.encode("utf-8"), CUSTOM_B64)

    logger.debug(f"签名生成完成 method={method} uri={uri}")
    return signature


# ============================================================
# Legacy 签名（ReaJason/xhs 风格，生成 x-s / x-t / x-s-common）
# 用于扫码登录等场景
# ============================================================

# CRC32 查找表
_CRC_TABLE = [
    0, 1996959894, 3993919788, 2567524794, 124634137, 1886057615, 3915621685,
    2657392035, 249268274, 2044508324, 3772115230, 2547177864, 162941995,
    2125561021, 3887607047, 2428444049, 498536548, 1789927666, 4089016648,
    2227061214, 450548861, 1843258603, 4107580753, 2211677639, 325883990,
    1684777152, 4251122042, 2321926636, 335633487, 1661365465, 4195302755,
    2366115317, 997073096, 1281953886, 3579855332, 2724688242, 1006888145,
    1258607687, 3524101629, 2768942443, 901097722, 1119000684, 3686517206,
    2898065728, 853044451, 1172266101, 3705015759, 2882616665, 651767980,
    1373503546, 3369554304, 3218104598, 565507253, 1454621731, 3485111705,
    3099436303, 671266974, 1594198024, 3322730930, 2970347812, 795835527,
    1483230225, 3244367275, 3060149565, 1994146192, 31158534, 2563907772,
    4023717930, 1907459465, 112637215, 2680153253, 3904427059, 2013776290,
    251722036, 2517215374, 3775830040, 2137656763, 141376813, 2439277719,
    3865271297, 1802195444, 476864866, 2238001368, 4066508878, 1812370925,
    453092731, 2181625025, 4111451223, 1706088902, 314042704, 2344532202,
    4240017532, 1658658271, 366619977, 2362670323, 4224994405, 1303535960,
    984961486, 2747007092, 3569037538, 1256170817, 1037604311, 2765210733,
    3554079995, 1131014506, 879679996, 2909243462, 3663771856, 1141124467,
    855842277, 2852801631, 3708648649, 1342533948, 654459306, 3188396048,
    3373015174, 1466479909, 544179635, 3110523913, 3462522015, 1591671054,
    702138776, 2966460450, 3352799412, 1504918807, 783551873, 3082640443,
    3233442989, 3988292384, 2596254646, 62317068, 1957810842, 3939845945,
    2647816111, 81470997, 1943803523, 3814918930, 2489596804, 225274430,
    2053790376, 3826175755, 2466906013, 167816743, 2097651377, 4027552580,
    2265490386, 503444072, 1762050814, 4150417245, 2154129355, 426522225,
    1852507879, 4275313526, 2312317920, 282753626, 1742555852, 4189708143,
    2394877945, 397917763, 1622183637, 3604390888, 2714866558, 953729732,
    1340076626, 3518719985, 2797360999, 1068828381, 1219638859, 3624741850,
    2936675148, 906185462, 1090812512, 3747672003, 2825379669, 829329135,
    1181335161, 3412177804, 3160834842, 628085408, 1382605366, 3423369109,
    3138078467, 570562233, 1426400815, 3317316542, 2998733608, 733239954,
    1555261956, 3268935591, 3050360625, 752459403, 1541320221, 2607071920,
    3965973030, 1969922972, 40735498, 2617837225, 3943577151, 1913087877,
    83908371, 2512341634, 3803740692, 2075208622, 213261112, 2463272603,
    3855990285, 2094854071, 198958881, 2262029012, 4057260610, 1759359992,
    534414190, 2176718541, 4139329115, 1873836001, 414664567, 2282248934,
    4279200368, 1711684554, 285281116, 2405801727, 4167216745, 1634467795,
    376229701, 2685067896, 3608007406, 1308918612, 956543938, 2808555105,
    3495958263, 1231636301, 1047427035, 2932959818, 3654703836, 1088359270,
    936918000, 2847714899, 3736837829, 1202900863, 817233897, 3183342108,
    3401237130, 1404277552, 615818150, 3134207493, 3453421203, 1423857449,
    601450431, 3009837614, 3294710456, 1567103746, 711928724, 3020668471,
    3272380065, 1510334235, 755167117,
]

# 自定义 Base64 查找表
_B64_LOOKUP = [
    "Z", "m", "s", "e", "r", "b", "B", "o", "H", "Q", "t", "N", "P", "+",
    "w", "O", "c", "z", "a", "/", "L", "p", "n", "g", "G", "8", "y", "J",
    "q", "4", "2", "K", "W", "Y", "j", "0", "D", "S", "f", "d", "i", "k",
    "x", "3", "V", "T", "1", "6", "I", "l", "U", "A", "F", "M", "9", "7",
    "h", "E", "C", "v", "u", "R", "X", "5",
]

# sign_legacy 使用的 MD5 编码表
_LEGACY_B64 = "A4NjFqYu5wPHsO0XTdDgMa2r1ZQocVte9UJBvk6/7=yRnhISGKblCWi+LpfE8xzm3"


def _mrc(e: str) -> int:
    """CRC32 变种（用于 x-s-common 的 x9 字段）。"""
    import ctypes
    o = -1
    for n in range(min(57, len(e))):
        o = _CRC_TABLE[(o & 255) ^ ord(e[n])] ^ (ctypes.c_uint32(o).value >> 8)
    return o ^ -1 ^ 3988292384


def _encode_utf8_bytes(e: str) -> list[int]:
    """URL 编码后转为字节列表（用于 x-s-common 编码）。"""
    b = []
    m = __import__("urllib").parse.quote(e, safe="~()*!.\\'")
    w = 0
    while w < len(m):
        t = m[w]
        if t == "%":
            s = int(m[w + 1] + m[w + 2], 16)
            b.append(s)
            w += 2
        else:
            b.append(ord(t[0]))
        w += 1
    return b


def _b64_encode_custom(e: list[int]) -> str:
    """自定义 Base64 编码（用于 x-s-common）。"""
    p = len(e)
    w = p % 3
    u = []
    z = 16383
    h = 0
    zlen = p - w
    while h < zlen:
        u.append(_encode_chunk(e, h, zlen if h + z > zlen else h + z))
        h += z
    if 1 == w:
        f = e[p - 1]
        u.append(_B64_LOOKUP[f >> 2] + _B64_LOOKUP[(f << 4) & 63] + "==")
    elif 2 == w:
        f = (e[p - 2] << 8) + e[p - 1]
        u.append(_B64_LOOKUP[f >> 10] + _B64_LOOKUP[63 & (f >> 4)] + _B64_LOOKUP[(f << 2) & 63] + "=")
    return "".join(u)


def _encode_chunk(e: list[int], t: int, r: int) -> str:
    m = []
    for b in range(t, r, 3):
        n = (16711680 & (e[b] << 16)) + ((e[b + 1] << 8) & 65280) + (e[b + 2] & 255)
        m.append(_triplet_to_base64(n))
    return "".join(m)


def _triplet_to_base64(e: int) -> str:
    return (
        _B64_LOOKUP[63 & (e >> 18)]
        + _B64_LOOKUP[63 & (e >> 12)]
        + _B64_LOOKUP[(e >> 6) & 63]
        + _B64_LOOKUP[e & 63]
    )


def _legacy_h(n: str) -> str:
    """sign_legacy 的 MD5 编码函数。"""
    m = ""
    d = _LEGACY_B64
    for i in range(0, 32, 3):
        o = ord(n[i])
        g = ord(n[i + 1]) if i + 1 < 32 else 0
        h_val = ord(n[i + 2]) if i + 2 < 32 else 0
        x = ((o & 3) << 4) | (g >> 4)
        p = ((15 & g) << 2) | (h_val >> 6)
        v = o >> 2
        b = h_val & 63 if h_val else 64
        if not g:
            p = b = 64
        m += d[v] + d[x] + d[p] + d[b]
    return m


def sign_legacy(uri: str, data: dict | None = None, a1: str = "", b1: str = "") -> dict[str, str]:
    """生成小红书 Legacy 签名（x-s / x-t / x-s-common）。

    基于 ReaJason/xhs 项目的签名算法，适用于扫码登录等场景。

    Args:
        uri: 请求路径（如 /api/sns/web/v1/login/qrcode/create）
        data: POST body 字典（GET 请求传 None）
        a1: Cookie 中的 a1 值
        b1: localStorage 中的 b1 值（可为空）

    Returns:
        {"x-s": str, "x-t": str, "x-s-common": str}
    """
    v = int(round(time.time() * 1000))
    raw_str = (
        f"{v}test{uri}"
        f"{json.dumps(data, separators=(',', ':'), ensure_ascii=False) if isinstance(data, dict) else ''}"
    )
    md5_str = hashlib.md5(raw_str.encode("utf-8")).hexdigest()
    x_s = _legacy_h(md5_str)
    x_t = str(v)

    common = {
        "s0": 5,
        "s1": "",
        "x0": "1",
        "x1": "3.2.0",
        "x2": "Windows",
        "x3": "xhs-pc-web",
        "x4": "2.3.1",
        "x5": a1,
        "x6": x_t,
        "x7": x_s,
        "x8": b1,
        "x9": _mrc(x_t + x_s),
        "x10": 1,
    }
    encode_str = _encode_utf8_bytes(json.dumps(common, separators=(",", ":")))
    x_s_common = _b64_encode_custom(encode_str)

    logger.debug(f"Legacy 签名生成完成 uri={uri}")
    return {"x-s": x_s, "x-t": x_t, "x-s-common": x_s_common}
