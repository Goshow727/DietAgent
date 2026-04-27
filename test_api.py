"""
后端 API 全量通信测试脚本
用法: python test_api.py [BASE_URL]
默认: http://8.138.22.3:8000
"""

import sys
import json
import time
import random
import string
import urllib.request
import urllib.error
from datetime import date

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://8.138.22.3:8000"
BASE_URL = BASE_URL.rstrip("/")

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

results = []


def rnd(n=6):
    return "".join(random.choices(string.ascii_lowercase, k=n))


def req(method, path, body=None, token=None, form=None, timeout=30):
    url = f"{BASE_URL}{path}"
    headers = {}
    data = None

    if token:
        headers["Authorization"] = f"Bearer {token}"

    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    elif form is not None:
        boundary = "----FormBoundary" + rnd(16)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        parts = []
        for k, v in form.items():
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
                f"{v}\r\n"
            )
        parts.append(f"--{boundary}--\r\n")
        data = "".join(parts).encode()

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw[:300]}
    except Exception as e:
        return 0, {"_error": str(e)}


def check(label, status, payload, expect_code=200, expect_ok=True):
    ok_flag = payload.get("code") == 0 if expect_ok else True
    passed = status == expect_code and ok_flag
    tag = PASS if passed else FAIL
    results.append((label, passed))
    data_preview = str(payload.get("data", ""))[:120]
    msg_preview = payload.get("message", payload.get("_error", payload.get("_raw", "")))
    if passed:
        print(f"  {tag} {label}")
        if data_preview:
            print(f"        data: {data_preview}")
    else:
        print(f"  {tag} {label}  HTTP {status}  msg={msg_preview!r}")
    return passed, payload


# ─────────────────────────────────────────────
print(f"\n{INFO} 目标服务: {BASE_URL}\n")

# ──────────── 0. 健康检查 ────────────
print("── 0. 服务可达性 ──────────────────────────────")
s, p = req("GET", "/docs")
if s == 200:
    print(f"  {PASS} GET /docs  (Swagger 可访问)")
    results.append(("GET /docs", True))
else:
    print(f"  {FAIL} GET /docs  HTTP {s}")
    results.append(("GET /docs", False))

# ──────────── 1. 注册 / 登录 ────────────
print("\n── 1. Auth ────────────────────────────────────")
uid = rnd(8)
test_user = {"username": f"test_{uid}", "password": "test_pass_123"}

s, p = req("POST", "/api/v1/auth/register", body={**test_user, "email": f"{uid}@test.com"})
ok, p = check("POST /auth/register", s, p)

s, p = req("POST", "/api/v1/auth/login", body=test_user)
ok, p = check("POST /auth/login", s, p)
TOKEN = p.get("data", {}).get("access_token", "") if ok else ""

if not TOKEN:
    print(f"  {FAIL} 无法获取 token，后续认证测试将全部失败")

# ──────────── 2. Users ────────────
print("\n── 2. Users ───────────────────────────────────")
s, p = req("GET", "/api/v1/users", token=TOKEN)
check("GET /users (me)", s, p)

s, p = req("PUT", "/api/v1/users", token=TOKEN, form={"nickname": "测试用户", "age": "25"})
check("PUT /users (update profile)", s, p)

s, p = req("GET", "/api/v1/users/status", token=TOKEN)
check("GET /users/status", s, p)

# 无 token 应返回 401
s, p = req("GET", "/api/v1/users")
check("GET /users (无 token → 401)", s, p, expect_code=401, expect_ok=False)

# ──────────── 3. Foods ────────────
print("\n── 3. Foods ───────────────────────────────────")
s, p = req("GET", "/api/v1/foods?q=鸡胸肉")
ok, p = check("GET /foods?q=鸡胸肉", s, p)
food_id = None
if ok and isinstance(p.get("data"), list) and p["data"]:
    food_id = p["data"][0]["id"]
    print(f"        首条: id={food_id}  name={p['data'][0].get('name')}")

s, p = req("GET", "/api/v1/foods?q=")
check("GET /foods?q= (空查询)", s, p)

s, p = req("GET", "/api/v1/foods?q=米饭")
check("GET /foods?q=米饭", s, p)

# ──────────── 4. Intakes ────────────
print("\n── 4. Intakes ─────────────────────────────────")
intake_id = None
today = str(date.today())

if food_id:
    s, p = req("POST", "/api/v1/intakes", token=TOKEN,
               body={"food_id": food_id, "weight_grams": 150.0})
    ok, p = check("POST /intakes (food_id)", s, p)
    if ok and p.get("data"):
        intake_id = p["data"].get("id")
else:
    print(f"  {WARN} 跳过 POST /intakes (food_id) — 未找到 food_id")

s, p = req("POST", "/api/v1/intakes", token=TOKEN, body={
    "inline_food": {
        "name": "自定义测试食物",
        "kcal_per_100g": 200.0,
        "protein_per_100g": 20.0,
        "carb_per_100g": 10.0,
        "fat_per_100g": 5.0,
    },
    "weight_grams": 100.0,
})
ok2, p2 = check("POST /intakes (inline_food)", s, p)
if ok2 and p2.get("data") and not intake_id:
    intake_id = p2["data"].get("id")

s, p = req("GET", f"/api/v1/intakes?date={today}", token=TOKEN)
check(f"GET /intakes?date={today}", s, p)

if intake_id:
    s, p = req("DELETE", f"/api/v1/intakes/{intake_id}", token=TOKEN)
    check(f"DELETE /intakes/{intake_id}", s, p)
else:
    print(f"  {WARN} 跳过 DELETE /intakes — 无可删除记录")

# ──────────── 5. Burns ────────────
print("\n── 5. Burns ───────────────────────────────────")
burn_id = None
s, p = req("POST", "/api/v1/burns", token=TOKEN,
           body={"exercise_type": "cardio", "intensity": 3, "duration_minutes": 30, "kcal": 250.0})
ok, p = check("POST /burns (cardio)", s, p)
if ok and p.get("data"):
    burn_id = p["data"].get("id")

s, p = req("POST", "/api/v1/burns", token=TOKEN,
           body={"exercise_type": "anaerobic", "intensity": 4, "duration_minutes": 45, "kcal": 300.0})
check("POST /burns (anaerobic)", s, p)

s, p = req("GET", f"/api/v1/burns?date={today}", token=TOKEN)
check(f"GET /burns?date={today}", s, p)

if burn_id:
    s, p = req("DELETE", f"/api/v1/burns/{burn_id}", token=TOKEN)
    check(f"DELETE /burns/{burn_id}", s, p)

# ──────────── 6. Insight ────────────
print("\n── 6. Insight ─────────────────────────────────")
s, p = req("GET", "/api/v1/users/me/home-insight", token=TOKEN, timeout=30)
check("GET /users/me/home-insight", s, p)

# ──────────── 7. Banner ────────────
print("\n── 7. Banner ──────────────────────────────────")
s, p = req("POST", "/api/v1/banners/init", token=TOKEN)
check("POST /banners/init", s, p)

# init 触发后台任务生成卡片，短暂等待
print(f"  {INFO} 等待 3s 后拉取 banner …")
time.sleep(3)

s, p = req("GET", "/api/v1/banners?count=1", token=TOKEN, timeout=15)
ok, p = check("GET /banners?count=1", s, p)
card_id = None
if ok and p.get("data", {}).get("cards"):
    card_id = p["data"]["cards"][0].get("id")
    print(f"        card_id={card_id}  title={p['data']['cards'][0].get('title','')[:40]}")
else:
    print(f"  {WARN} banner 暂无就绪卡片（后台可能仍在生成，属正常现象）")

if card_id:
    s, p = req("PUT", f"/api/v1/banners/{card_id}/red-cut", token=TOKEN, body={})
    check(f"PUT /banners/{card_id}/red-cut", s, p)

# ──────────── 8. Agent Chat ────────────
print("\n── 8. Agent /chat ─────────────────────────────")
s, p = req("POST", "/api/v1/agent/chat", token=TOKEN,
           body={"message": "你好，请推荐今天的饮食计划"}, timeout=30)
check("POST /agent/chat", s, p)

# ──────────── 汇总 ────────────
print("\n" + "=" * 55)
total = len(results)
passed = sum(1 for _, ok in results if ok)
failed = total - passed
print(f"  测试结果: {passed}/{total} 通过  |  {failed} 失败")
print("=" * 55)
if failed:
    print(f"\n{FAIL} 失败项:")
    for name, ok in results:
        if not ok:
            print(f"    • {name}")
print()
sys.exit(0 if failed == 0 else 1)
