# 郑铁文创自动签到 🎫

每日自动签到郑铁文创小程序，支持 **GitHub Actions** 和 **青龙面板** 运行。

## ✨ 功能特性

- ✅ 每日自动签到，领取积分
- ✅ 多账号支持
- ✅ 签到前检测，避免重复签到（幂等，重复触发安全）
- ✅ **启动随机延迟**：默认随机等 0~30 分钟再签到，规避「每天固定时刻」机器特征
- ✅ **随机 User-Agent**：6 个真实微信 UA 中随机选取（单账号单次运行内保持一致）
- ✅ **拟人化请求节奏**：查询 → 停顿数秒 → 提交 → 停顿 → 回查结果
- ✅ 多种推送通知 (Server酱 / Telegram / Bark / PushPlus)
- ✅ 支持 GitHub Actions 定时运行
- ✅ 支持 青龙面板 运行

---

## 📱 获取 session-id

### 方法：微信小程序抓包

1. 安装抓包工具 (推荐 [Charles](https://www.charlesproxy.com/) 或 [Fiddler](https://www.telerik.com/fiddler))
2. 配置手机代理，安装 HTTPS 证书
3. 打开微信 → 搜索「**郑铁文创**」小程序
4. 进入 **积分签到** 页面，点击签到
5. 在抓包工具中找到 `www.renrenshoping.com` 的请求
6. 复制**请求头**中的 `session-id` 值（形如 `5vupvlenh0t1g67fkhss9e7gna`）

> ⚠️ 注意：鉴权走的是请求头 `session-id` + `shop-id`，**不是 Cookie**。
> session-id 有时效性，失效后需要重新抓包。

---

## 🚀 部署方式

### 方式一：GitHub Actions (推荐)

1. **Fork 本仓库**

2. **设置 Secrets / Variables**

   进入仓库 → `Settings` → `Secrets and variables` → `Actions`

   **Secrets 页签**（敏感信息，必填项）：

   | Secret 名称 | 说明 | 必填 |
   |---|---|---|
   | `ZTWC_SESSION` | session-id，多账号用 `&` 或换行分隔 | ✅ |
   | `PUSH_KEY` | Server酱推送Key | ❌ |
   | `TG_BOT_TOKEN` | Telegram Bot Token | ❌ |
   | `TG_CHAT_ID` | Telegram Chat ID | ❌ |
   | `BARK_KEY` | Bark推送Key | ❌ |
   | `PUSHPLUS_TOKEN` | PushPlus推送Token | ❌ |

   **Variables 页签**（非敏感配置，全部可选，不填就用默认值）：

   | Variable 名称 | 默认值 | 说明 |
   |---|---|---|
   | `ZTWC_SHOP_ID` | `1391` | 店铺ID，一般不用改 |
   | `ZTWC_DELAY_MIN` | `0` | 随机延迟下限（秒） |
   | `ZTWC_DELAY_MAX` | `1800` | 随机延迟上限（秒），设 `0` 彻底关闭延迟 |
   | `ZTWC_RANDOM_UA` | `true` | 是否随机 UA，设 `false` 用固定 UA |

3. **启用 Actions**

   进入仓库 → `Actions` → 点击 `I understand my workflows, go ahead and enable them`

4. **手动测试**

   进入 `Actions` → `郑铁文创自动签到` → `Run workflow` → 点击运行

> 📅 默认每天北京时间 **07:00** 触发，脚本内部再随机延迟，**真实签到落在 07:00~07:30**。
> ⚠️ GitHub Actions 的 cron 用的是 **UTC**，北京时间 07:00 = UTC 前一日 23:00。

---

### 方式二：青龙面板

1. **添加脚本**

   在青龙面板中，选择「脚本管理」，上传 `zhengtie_checkin.py` 文件。

   或者通过「订阅管理」拉取仓库：
   ```
   名称: 郑铁文创签到
   类型: 公开仓库
   链接: <你的仓库地址>
   定时类型: crontab
   定时规则: 0 7 * * *
   文件后缀: py
   ```

2. **配置环境变量**

   进入「环境变量」，添加：

   | 名称 | 值 | 必填 |
   |---|---|---|
   | `ZTWC_SESSION` | 你的 session-id | ✅ |
   | `ZTWC_SHOP_ID` | 店铺ID，默认 1391 | ❌ |
   | `ZTWC_DELAY_MIN` | 随机延迟下限（秒），默认 0 | ❌ |
   | `ZTWC_DELAY_MAX` | 随机延迟上限（秒），默认 1800 | ❌ |
   | `ZTWC_RANDOM_UA` | 是否随机 UA，默认 true | ❌ |
   | `PUSH_KEY` | Server酱Key | ❌ |

   > 多账号在同一个变量中用 `&` 或换行分隔

3. **创建定时任务**

   进入「定时任务」，新建任务：
   ```
   名称: 郑铁文创签到
   命令: task zhengtie_checkin.py
   定时规则: 0 7 * * *
   ```

   > ⏱️ **注意超时设置**：开启随机延迟后最坏情况耗时约 30 分钟。
   > 请把青龙任务的「超时」设置为 **35 分钟以上**，否则延迟还没睡完任务就被杀掉了。
   > 也可以调小 `ZTWC_DELAY_MAX` 来缩短窗口。
   >
   > ⚠️ **不要再用 `0 8 * * *` 这种每天同一分钟的固定时刻**，那是最明显的机器特征。

---

### 方式三：本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量
# Windows PowerShell
$env:ZTWC_SESSION="你的session-id"

# Linux/Mac
export ZTWC_SESSION="你的session-id"

# 运行
python zhengtie_checkin.py
```

---

## 📋 多账号配置

多个账号的 session-id 用 `&` 或换行符分隔：

```
session1内容&session2内容&session3内容
```

多账号之间会随机等待 15~45 秒，避免同秒并发。

---

## 🔔 推送通知配置

| 渠道 | 环境变量 | 获取方式 |
|---|---|---|
| Server酱 | `PUSH_KEY` | [sct.ftqq.com](https://sct.ftqq.com/) |
| Telegram | `TG_BOT_TOKEN` + `TG_CHAT_ID` | [@BotFather](https://t.me/BotFather) |
| Bark | `BARK_KEY` | iOS Bark App |
| PushPlus | `PUSHPLUS_TOKEN` | [pushplus.plus](https://www.pushplus.plus/) |

> 在青龙面板中，如果存在 `/ql/data/scripts/notify.py`，脚本会优先走青龙自带的推送通道。

---

## 📁 项目结构

```
dailyzhengtie/
├── zhengtie_checkin.py        # 主签到脚本
├── requirements.txt           # Python依赖
├── README.md                  # 说明文档
├── .gitignore                 # Git忽略文件
└── .github/
    └── workflows/
        └── checkin.yml        # GitHub Actions 工作流
```

---

## 🛡️ 防封说明

本脚本的防封是「时间维度」的，不做任何绕过风控的对抗行为：

| 机制 | 做法 |
|---|---|
| 时间随机化 | 定时触发后再随机延迟 0~30 分钟，真实签到时刻每天不同 |
| UA 多样化 | 6 个真实微信 UA 中随机选，同一账号单次运行内保持一致 |
| 请求节奏 | 查询 → 停 1.5~5s → 提交前再停 2~8s → 提交 → 停 3~10s 回查 |
| 多账号错峰 | 账号之间随机等 15~45 秒 |
| 幂等 | 查询到当天已签到直接跳过，重复触发不会重复请求签到接口 |

> 建议把 `ZTWC_DELAY_MAX` 适当调大（如 5400 = 1.5 小时），窗口越大越不规律。

---

## 🔧 版本说明

- Python 3.8+（Actions 中使用 3.11）
- 仅依赖 `requests`

---

## ⚠️ 免责声明

- 本项目仅供学习交流使用
- 使用本脚本产生的一切后果由使用者自行承担
- 请勿用于商业用途或恶意用途
- 如有侵权，请联系删除

---

## 📝 更新日志

### v1.1.1 (2026-09-19)
- 🐛 修复空环境变量把默认值顶掉的 BUG：GitHub Actions 中未配置的 Secret / Var 会被导出为**空字符串**，
  原实现用 `os.environ.get(name, default)` 会拿到 `""` 而非默认值，导致 `ZTWC_SHOP_ID` 变成空串、
  `ZTWC_RANDOM_UA` 被误判为 `false`（随机 UA 静默失效）。新增 `_env_str()` 统一把空串视为「未设置」

### v1.1.0 (2026-08-12)
- 🛡️ 新增启动随机延迟：`ZTWC_DELAY_MIN` / `ZTWC_DELAY_MAX`，默认 0~1800 秒，把真实签到时刻打散到时间窗内
- 🎭 新增 UA 池随机化：6 个真实微信 UA 变体，`ZTWC_RANDOM_UA` 可关闭
- ⏱️ 新增拟人化请求节奏：查询/提交/回查之间插入随机停顿
- 🔀 多账号抖动由 3~8 秒提升到 15~45 秒
- 📝 Cron 建议由 `0 8 * * *` 改为 `0 7 * * *`，并提醒超时设置

### v1.0.0
- 🎉 初始版本
- ✅ 支持每日自动签到
- ✅ 支持多账号
- ✅ 支持 GitHub Actions + 青龙面板
- ✅ 支持多种推送通知
