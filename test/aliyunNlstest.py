"""
Aliyun NLS token smoke test using aliyunsdkcore.

Usage:
    ALIYUN_AK_ID=xxx ALIYUN_AK_SECRET=yyy ALIYUN_NLS_APPKEY=zzz python test/aliyunNlstest.py

Or set in environment and run directly.
"""

import os
import json

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

AK_ID = os.getenv("ALIYUN_AK_ID", "")
AK_SECRET = os.getenv("ALIYUN_AK_SECRET", "")
APP_KEY = os.getenv("ALIYUN_NLS_APPKEY", "")

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

print("=" * 50)
print("Aliyun NLS token test (aliyunsdkcore)")
print(f"  AK_ID   : {AK_ID[:8]}..." if AK_ID else "  AK_ID   : (not set)")
print(f"  APP_KEY : {APP_KEY}" if APP_KEY else "  APP_KEY : (not set)")
print("=" * 50)

if not AK_ID or not AK_SECRET:
    print(f"\n{FAIL}  ALIYUN_AK_ID / ALIYUN_AK_SECRET not set in environment.")
    raise SystemExit(1)

client = AcsClient(AK_ID, AK_SECRET, "cn-shanghai")

req = CommonRequest()
req.set_method("POST")
req.set_domain("nls-meta.cn-shanghai.aliyuncs.com")
req.set_version("2019-02-28")
req.set_action_name("CreateToken")

try:
    resp = json.loads(client.do_action_with_exception(req))
    token = resp["Token"]["Id"]
    expire = resp["Token"]["ExpireTime"]
    print(f"\n{PASS}  Token  : {token[:12]}...")
    print(f"         Expire : {expire}")
    print(f"         AppKey : {APP_KEY or '(not set — pass ALIYUN_NLS_APPKEY)'}")
except Exception as e:
    print(f"\n{FAIL}  {e}")
    raise SystemExit(1)
