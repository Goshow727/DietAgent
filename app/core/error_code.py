from enum import IntEnum


class ErrorCode(IntEnum):
    SUCCESS = 0

    PARAM_INVALID = 10001
    UNAUTHORIZED = 10002
    FORBIDDEN = 10003
    NOT_FOUND = 10004
    METHOD_NOT_ALLOWED = 10005
    INTERNAL_ERROR = 10500

    USER_NOT_FOUND = 20001
    USER_ALREADY_EXISTS = 20002
    PASSWORD_INCORRECT = 20003
    TOKEN_EXPIRED = 20004
    TOKEN_INVALID = 20005

    AGENT_INVOKE_FAILED = 30001

    FOOD_NOT_FOUND = 40001
    LOG_NOT_FOUND = 40002


ERROR_MESSAGES: dict[int, str] = {
    ErrorCode.SUCCESS: "ok",
    ErrorCode.PARAM_INVALID: "参数错误",
    ErrorCode.UNAUTHORIZED: "未登录或登录已过期",
    ErrorCode.FORBIDDEN: "无权限访问",
    ErrorCode.NOT_FOUND: "资源不存在",
    ErrorCode.METHOD_NOT_ALLOWED: "方法不允许",
    ErrorCode.INTERNAL_ERROR: "服务器内部错误",
    ErrorCode.USER_NOT_FOUND: "用户不存在",
    ErrorCode.USER_ALREADY_EXISTS: "用户已存在",
    ErrorCode.PASSWORD_INCORRECT: "密码错误",
    ErrorCode.TOKEN_EXPIRED: "令牌已过期",
    ErrorCode.TOKEN_INVALID: "令牌无效",
    ErrorCode.AGENT_INVOKE_FAILED: "Agent 调用失败",
    ErrorCode.FOOD_NOT_FOUND: "食物不存在",
    ErrorCode.LOG_NOT_FOUND: "日志不存在",
}


def message_of(code: ErrorCode | int) -> str:
    key = int(code)
    return ERROR_MESSAGES.get(key, "error")
