#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
郑铁文创小程序自动签到脚本
支持: GitHub Actions / 青龙面板 / 本地运行

【Cron 建议】
  0 7 * * *      # 7 点启动，脚本内部再随机延迟，真实签到落在 7:00~7:30
  0 7 * * *      # 想拉大窗口就调大 ZTWC_DELAY_MAX，例如 5400 -> 7:00~8:30
  ⚠️ 不要再用 0 8 * * * 这种「每天同一分钟」的固定时刻，那是最明显的机器特征
  ⚠️ 青龙「任务超时」需大于 ZTWC_DELAY_MAX + 60 秒，否则延迟没睡完就被杀
  ⚠️ 若在 GitHub Actions 运行，注意 6 小时作业上限，1800 秒延迟完全够用

【防封机制】
  1. 启动随机延迟：在 [ZTWC_DELAY_MIN, ZTWC_DELAY_MAX] 秒之间随机取一个值，
     先把真实签到时间打散到一个时间窗内，规避「每天固定时刻」特征
  2. 随机 User-Agent：从真实微信 UA 池中随机选取（同一账号单次运行内保持一致）
  3. 拟人化请求节奏：先「浏览」查询接口，停顿数秒后再提交签到，再停顿回查结果
  4. 账号间随机抖动：多账号不会在同一秒并发
  5. 幂等保护：查询到当天已签到则直接跳过，重复触发也不会重复签到

环境变量:
  ZTWC_SESSION:    郑铁文创 session-id，多账号用 & 或换行分隔 (必填)
  ZTWC_SHOP_ID:    店铺ID，默认 1391 (一般不用改)
  ZTWC_DELAY_MIN:  启动随机延迟下限(秒)，默认 0
  ZTWC_DELAY_MAX:  启动随机延迟上限(秒)，默认 1800 (30分钟)；设 0 关闭延迟
  ZTWC_RANDOM_UA:  是否随机 User-Agent，默认 true；设 false 用固定 UA
  PUSH_KEY:        Server酱推送Key (可选)
  TG_BOT_TOKEN:    Telegram Bot Token (可选)
  TG_CHAT_ID:      Telegram Chat ID (可选)
  BARK_KEY:        Bark推送Key (可选)
  PUSHPLUS_TOKEN:  PushPlus推送Token (可选)

  说明: 空字符串（例如 GitHub Actions 中未配置的 Secret/Var）一律按「未设置」处理，
        会回落到上面的默认值，不会因为空串把默认值顶掉。

获取 session-id 方法:
  1. 使用抓包工具(Charles/Fiddler/Stream)
  2. 打开微信 -> 郑铁文创小程序 -> 积分签到页面，点击签到
  3. 找到 www.renrenshoping.com 的请求
  4. 复制请求头中的 session-id 值 (形如 5vupvlenh0t1g67fkhss9e7gna)

签到接口 (从抓包分析得到):
  GET  /shop/apps/creditsign/client/index/index   查询签到状态/活动ID
  POST /shop/apps/creditsign/client/index/sign    执行签到 {"activity_id": "4409"}
"""

import os
import sys
import json
import time
import random
import logging
from datetime import datetime, timedelta
from urllib.parse import quote

__version__ = "1.1.1"

try:
    import requests
except ImportError:
    print("正在安装 requests 库...")
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ztwc")

# ============================================================
# API 地址 (从抓包分析得到)
# ============================================================
BASE_URL = "https://www.renrenshoping.com"
INDEX_URL = f"{BASE_URL}/shop/apps/creditsign/client/index/index"   # GET, 签到状态
SIGN_URL = f"{BASE_URL}/shop/apps/creditsign/client/index/sign"     # POST, 执行签到

# 郑铁文创店铺ID（一般不用改）
DEFAULT_SHOP_ID = "1391"

# ============================================================
# 防封参数 (可通过环境变量覆盖)
# ============================================================
def _env_int(name, default):
    """读整数环境变量。空字符串（如 GitHub Actions 未设置的 Secret）也回落到默认值。"""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_str(name, default=""):
    """读字符串环境变量。空字符串/纯空白一律视为「未设置」，回落到默认值。

    注意：GitHub Actions 里未配置的 Secret/Var 会导出为空字符串而不是不存在，
    所以不能直接用 os.environ.get(name, default)，否则默认值会被空串顶掉。
    """
    val = os.environ.get(name)
    if val is None:
        return default
    val = val.strip()
    return val if val else default


ZTWC_DELAY_MIN = _env_int("ZTWC_DELAY_MIN", 0)
ZTWC_DELAY_MAX = _env_int("ZTWC_DELAY_MAX", 1800)
ZTWC_RANDOM_UA = _env_str("ZTWC_RANDOM_UA", "true").lower() not in (
    "0", "false", "no", "off"
)

# 真实微信小程序 UA 池（结构与抓包一致，仅设备/版本维度做合理浮动）
# 说明：同一个账号在一次运行内始终使用同一个 UA，符合「同一台设备」的真实特征
_UA_TPL = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS {ios} like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "MicroMessenger/{mm} NetType/{net} Language/zh_CN"
)
UA_POOL = [
    _UA_TPL.format(ios="26_6", mm="8.0.76(0x18004c31)", net="WIFI"),
    _UA_TPL.format(ios="26_5", mm="8.0.75(0x18004b31)", net="WIFI"),
    _UA_TPL.format(ios="26_6", mm="8.0.75(0x18004b31)", net="4G"),
    _UA_TPL.format(ios="26_4", mm="8.0.74(0x18004a31)", net="WIFI"),
    _UA_TPL.format(ios="26_5", mm="8.0.76(0x18004c31)", net="WIFI"),
    _UA_TPL.format(ios="26_3", mm="8.0.73(0x18004931)", net="4G"),
]

# 固定 UA（ZTWC_RANDOM_UA=false 时使用，保持与抓包完全一致）
FIXED_UA = UA_POOL[0]

DEFAULT_HEADERS = {
    "content-type": "application/json",
    "versionCode": "821",
    "api-version": "1",
    "client-type": "wxapp",
    "mxcommon": "",
    "version": "6.19.7",
    "x-requested-with": "XMLHttpRequest",
    "Accept-Encoding": "gzip,compress,br,deflate",
    "Referer": "https://servicewechat.com/wxa72c5f3b4f96bac9/2/page-frame.html",
}


def build_headers(ua=None):
    """构造一份独立的请求头（避免多账号间互相污染）"""
    headers = dict(DEFAULT_HEADERS)
    headers["User-Agent"] = ua or (random.choice(UA_POOL) if ZTWC_RANDOM_UA else FIXED_UA)
    return headers


# 消息收集
notify_messages = []


def log_and_notify(msg):
    """记录日志并收集通知消息"""
    logger.info(msg)
    notify_messages.append(msg)


def fmt_duration(seconds):
    """秒 -> 人类可读"""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}秒"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}分{s}秒" if s else f"{m}分"
    h, m = divmod(m, 60)
    return f"{h}小时{m}分"


def random_startup_delay():
    """
    启动随机延迟：把真实签到时间打散到一个时间窗内。
    返回实际等待秒数（并已 sleep）。
    """
    lo = max(0, ZTWC_DELAY_MIN)
    hi = max(lo, ZTWC_DELAY_MAX)

    if hi <= 0:
        log_and_notify("⏱️ 随机延迟已关闭 (ZTWC_DELAY_MAX=0)，立即签到")
        return 0

    delay = random.uniform(lo, hi)
    start = datetime.now()
    fire_at = start + timedelta(seconds=delay)

    log_and_notify(
        f"⏱️ 启动随机延迟: {fmt_duration(delay)} "
        f"(窗口 {fmt_duration(lo)}~{fmt_duration(hi)})"
    )
    log_and_notify(f"🎯 预计签到时刻: {fire_at.strftime('%H:%M:%S')}")

    time.sleep(delay)
    return delay


# ============================================================
# 推送通知
# ============================================================
def send_notify(title, content):
    """发送推送通知 (兼容青龙 notify.py + 多渠道直推)"""
    # 优先使用青龙面板的 notify.py
    try:
        sys.path += ["/ql/data/scripts", "/ql/scripts"]
        from notify import send as ql_send
        ql_send(title, content)
        return
    except Exception:
        pass

    # Server酱推送
    push_key = os.environ.get("PUSH_KEY", "")
    if push_key:
        try:
            url = f"https://sctapi.ftqq.com/{push_key}.send"
            data = {"title": title, "desp": content.replace("\n", "\n\n")}
            resp = requests.post(url, data=data, timeout=10)
            if resp.status_code == 200:
                logger.info("Server酱推送成功")
        except Exception as e:
            logger.warning(f"Server酱推送异常: {e}")

    # Telegram Bot推送
    tg_token = os.environ.get("TG_BOT_TOKEN", "")
    tg_chat_id = os.environ.get("TG_CHAT_ID", "")
    if tg_token and tg_chat_id:
        try:
            url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            data = {"chat_id": tg_chat_id, "text": f"{title}\n\n{content}"}
            resp = requests.post(url, json=data, timeout=10)
            if resp.status_code == 200:
                logger.info("Telegram推送成功")
        except Exception as e:
            logger.warning(f"Telegram推送异常: {e}")

    # Bark推送
    bark_key = os.environ.get("BARK_KEY", "")
    if bark_key:
        try:
            url = f"https://api.day.app/{bark_key}/{quote(title)}/{quote(content)}"
            requests.get(url, timeout=10)
        except Exception as e:
            logger.warning(f"Bark推送异常: {e}")

    # PushPlus推送
    pushplus_token = os.environ.get("PUSHPLUS_TOKEN", "")
    if pushplus_token:
        try:
            url = "https://www.pushplus.plus/send"
            data = {"token": pushplus_token, "title": title, "content": content}
            requests.post(url, json=data, timeout=10)
        except Exception as e:
            logger.warning(f"PushPlus推送异常: {e}")


# ============================================================
# 郑铁文创签到类
# ============================================================
class ZtwcCheckin:
    """郑铁文创自动签到"""

    def __init__(self, session_id, shop_id=DEFAULT_SHOP_ID):
        self.session_id = session_id.strip()
        self.session = requests.Session()
        # 本账号本次运行固定使用一个 UA（模拟「同一台设备」）
        self.ua = random.choice(UA_POOL) if ZTWC_RANDOM_UA else FIXED_UA
        self.session.headers.update(build_headers(self.ua))
        self.session.headers["session-id"] = self.session_id
        self.session.headers["shop-id"] = str(shop_id)

    def _request(self, method, url, **kwargs):
        """封装请求，增加重试"""
        kwargs.setdefault("timeout", 30)
        for attempt in range(3):
            try:
                resp = self.session.request(method, url, **kwargs)
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"请求失败 (尝试 {attempt + 1}/3): {e}")
                if attempt < 2:
                    time.sleep(random.uniform(2, 6))
                else:
                    raise
        return None

    def get_index(self):
        """获取签到状态/活动信息"""
        try:
            resp = self._request("GET", INDEX_URL)
            data = resp.json()

            # 登录失效: error 非 0 且提示登录
            error = data.get("error")
            if error not in (0, None) and ("登录" in str(data.get("message", "")) or "login" in str(data.get("message", "")).lower()):
                log_and_notify(f"❌ session-id 已失效! (error={error}, msg={data.get('message')})")
                log_and_notify(f"   请重新抓包获取新的 session-id")
                return {"token_expired": True}

            today_sign = data.get("today_sign", 0)
            sign_num = data.get("sign_num", "?")
            activity_id = data.get("activity_id", "")
            continuity = data.get("continuity_reward", {}) or {}
            reward = data.get("reward", {}) or {}

            cont_days = continuity.get("days", "")
            cont_credit = continuity.get("credit", "")
            reward_credit = reward.get("sign_reward", "?")

            status = "已签到" if today_sign else "未签到"
            msg = f"📋 签到状态: {status} | 已累计签到{sign_num}天 | 今日奖励: {reward_credit}积分"
            if cont_days and cont_credit:
                msg += f" | 连签{cont_days}天可额外得{cont_credit}积分"
            log_and_notify(msg)

            return {
                "today_sign": bool(today_sign),
                "sign_num": sign_num,
                "activity_id": activity_id,
            }
        except Exception as e:
            log_and_notify(f"⚠️ 获取签到状态异常: {e}")
            return None

    def do_checkin(self, activity_id):
        """执行签到 - POST /shop/apps/creditsign/client/index/sign"""
        try:
            payload = {"activity_id": str(activity_id)}
            resp = self._request("POST", SIGN_URL, json=payload)
            data = resp.json()

            error = data.get("error")
            message = str(data.get("message", ""))

            if error == 0:
                log_and_notify(f"✅ 签到成功! {message}")
                return True
            elif "已签" in message or "重复" in message or "already" in message.lower():
                log_and_notify(f"📌 今日已签到，无需重复签到")
                return True
            elif "登录" in message or "login" in message.lower():
                log_and_notify(f"❌ 签到失败: session-id 已失效! (error={error}, msg={message})")
                log_and_notify(f"   请重新抓包获取新的 session-id")
                return False
            else:
                log_and_notify(f"❌ 签到失败: error={error}, msg={message}")
                log_and_notify(f"   完整响应: {json.dumps(data, ensure_ascii=False)[:300]}")
                return False

        except Exception as e:
            log_and_notify(f"❌ 签到异常: {e}")
            return False

    def run(self):
        """运行签到流程"""
        log_and_notify(f"{'='*40}")
        log_and_notify(f"🎫 郑铁文创自动签到")
        log_and_notify(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # session-id 打码展示
        sid = self.session_id
        masked = sid[:6] + "***" + sid[-4:] if len(sid) > 12 else sid[:4] + "***"
        log_and_notify(f"🔑 session-id: {masked}")
        if ZTWC_RANDOM_UA:
            # UA 只打码展示关键片段，便于排错但不泄露完整指纹
            log_and_notify(f"🖥️ UA: {self.ua[:58]}...{self.ua[-22:]}")
        log_and_notify(f"{'='*40}")

        # 0. 账号级小抖动（拟人：进入小程序前的一点停顿）
        time.sleep(random.uniform(1.5, 5))

        # 1. 获取签到状态
        info = self.get_index()
        if not info:
            return False
        if info.get("token_expired"):
            return False

        # 已签到则跳过（幂等，重复触发安全）
        if info.get("today_sign"):
            log_and_notify("✅ 今日已完成签到，跳过")
            return True

        activity_id = info.get("activity_id", "")
        if not activity_id:
            log_and_notify("❌ 未获取到活动ID (activity_id)，可能活动已结束")
            return False

        # 随机延迟，模拟人工「看完页面再点签到」
        delay = random.uniform(2, 8)
        logger.info(f"浏览页面中，{delay:.1f} 秒后提交签到...")
        time.sleep(delay)

        # 2. 执行签到
        result = self.do_checkin(activity_id)

        # 3. 签到后回查状态确认累计天数
        if result:
            time.sleep(random.uniform(3, 10))
            self.get_index()

        log_and_notify("")
        return result


# ============================================================
# 主入口
# ============================================================
def main():
    """主函数"""
    global notify_messages
    notify_messages = []

    log_and_notify("🎫 郑铁文创自动签到程序启动")
    log_and_notify(f"⏰ 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 从环境变量获取 session-id
    session_str = _env_str("ZTWC_SESSION", "")
    shop_id = _env_str("ZTWC_SHOP_ID", DEFAULT_SHOP_ID)

    if not session_str:
        log_and_notify("❌ 未配置 ZTWC_SESSION 环境变量!")
        log_and_notify("请设置环境变量 ZTWC_SESSION 为郑铁文创小程序的 session-id")
        log_and_notify("抓包 www.renrenshoping.com 请求头中的 session-id 值")
        log_and_notify("多账号请用 & 或换行符分隔")
        send_notify("郑铁文创签到失败", "\n".join(notify_messages))
        sys.exit(1)

    # 支持多账号，用 & 或换行分隔
    sessions = [s.strip() for s in session_str.replace("&", "\n").split("\n") if s.strip()]

    log_and_notify(f"📊 共检测到 {len(sessions)} 个账号\n")

    # ★ 防封核心：启动随机延迟，把真实签到时间打散到时间窗内
    log_and_notify("🛡️ 防封策略: 时间随机化 + UA 多样化 + 拟人化节奏")
    random_startup_delay()
    log_and_notify("")

    success_count = 0
    fail_count = 0
    start_ts = time.time()

    for idx, sid in enumerate(sessions, 1):
        log_and_notify(f"🔄 开始处理第 {idx}/{len(sessions)} 个账号")

        try:
            checkin = ZtwcCheckin(sid, shop_id)
            result = checkin.run()
            if result:
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            log_and_notify(f"❌ 第 {idx} 个账号处理异常: {e}")
            fail_count += 1

        # 多账号间随机抖动（避免同秒并发，像是不同人各自操作）
        if idx < len(sessions):
            delay = random.uniform(15, 45)
            logger.info(f"账号间等待 {delay:.1f} 秒...")
            time.sleep(delay)

    # 汇总
    elapsed = time.time() - start_ts
    log_and_notify(f"\n{'='*40}")
    log_and_notify(f"📊 签到汇总: 成功 {success_count} | 失败 {fail_count} | 总计 {len(sessions)}")
    log_and_notify(f"⏱️ 本次签到耗时: {fmt_duration(elapsed)}")
    log_and_notify(f"🕐 完成时刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_and_notify(f"{'='*40}")

    # 发送通知
    title = f"郑铁文创签到 - 成功{success_count}/{len(sessions)}"
    send_notify(title, "\n".join(notify_messages))

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
