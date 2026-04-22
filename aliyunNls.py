import os, json
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

client = AcsClient(
    os.getenv("ALIYUN_AK_ID"),
    os.getenv("ALIYUN_AK_SECRET"),
    "cn-shanghai",
)
req = CommonRequest()
req.set_method("POST")
req.set_domain("nls-meta.cn-shanghai.aliyuncs.com")
req.set_version("2019-02-28")
req.set_action_name("CreateToken")

resp = json.loads(client.do_action_with_exception(req))
print("Token:", resp["Token"]["Id"])
print("Expire:", resp["Token"]["ExpireTime"])
print("AppKey in env:", os.getenv("ALIYUN_NLS_APPKEY"))