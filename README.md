# Dify + 飞书机器人 · SRE 运维问答助手

基于 **Dify（知识库 + 工作流）** 与 **飞书机器人（WebSocket 长连接）** 的 SRE 运维问答助手。
研发/测试同学在飞书群或私聊中 `@SRE助手` 提问，机器人调用 Dify 工作流（问题分类 → 知识检索 → LLM 生成 → 格式化输出），实时返回基于运维知识库的回答。

## 架构

```
飞书用户 ──HTTPS──> 飞书开放平台 ──WebSocket长连接──> 本中间服务(Python)
                                                        │  Dify Chat API
                                                        ▼
                                                      Dify 平台
                                                    (Workflow → Knowledge Base → LLM)
```

采用 **WebSocket 长连接模式**：无需公网 IP / 域名 / 内网穿透，直接由 SDK 订阅飞书事件，本地即可跑通。

## 目录结构

```
Dify_base_SRE_bot/
├── main.py                 # 服务入口：启动飞书长连接客户端
├── config.py               # 配置管理：从 .env 读取密钥与参数
├── dify_client.py          # Dify Chat API 调用封装
├── feishu_handler.py       # 飞书事件接收 + 消息回复（文本/卡片）
├── conversation_store.py   # 会话管理：维持多轮上下文
├── requirements.txt        # 依赖声明
├── .env.example            # 环境变量模板（复制为 .env 后填写）
├── .gitignore
├── knowledge_samples/      # 示例运维文档（可导入 Dify 知识库）
│   ├── CPU使用率过高排查手册.md
│   ├── Prometheus告警配置指南.md
│   └── 发布回滚操作流程.md
└── README.md
```

## 前置准备

### 1. Dify 侧（知识库 + 工作流）

1. 在 Dify 中创建知识库（如 `SRE-运维知识库`），导入运维文档（可将 `knowledge_samples/` 下示例文档导入）。
   - 分段建议：自动分段，长度 500~800 tokens，重叠 50~100 tokens，索引选「高质量（Embedding）」，检索选「混合检索」。
2. 创建 **工作流（Workflow）** 应用，编排：`开始 → 问题分类(LLM) → 条件分支 → 知识检索 → LLM 生成回答 → 输出`，另接一条「超出范围」的兜底回复分支。
3. 调试通过后 **发布**，进入「访问 API」页面，记录：
   - `DIFY_API_BASE`（如 `https://api.dify.ai/v1`，自部署则填你的 Dify 地址）
   - `DIFY_API_KEY`（`app-` 开头）

### 2. 飞书侧（应用 + 机器人）

1. 在 [飞书开放平台](https://open.feishu.cn) 创建 **企业自建应用**，名称如「SRE 运维助手」。
2. 记录 **App ID / App Secret**（凭证与基础信息页）。
3. 「添加应用能力」→ 启用 **机器人**。
4. 「权限管理」开通：
   - `im:message`（获取消息 / 接收消息）
   - `im:message:receive_v1`（接收消息）
   - `im:message:send_as_bot_v1`（以机器人身份发消息）
5. 「事件订阅」→ 订阅方式选 **使用长连接接收事件**，添加事件 **接收消息 `im.message.receive_v1`**。
6. 创建应用版本并 **发布**，等待企业管理员审核通过。
7. 将机器人加入目标群，或在私聊中与机器人对话。

## 快速开始

```bash
# 1. 安装依赖（建议使用虚拟环境）
cd Dify_base_SRE_bot
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt

# 2. 准备配置
cp .env.example .env        # Windows: copy .env.example .env
# 编辑 .env，填入 FEISHU_APP_ID / FEISHU_APP_SECRET / DIFY_API_BASE / DIFY_API_KEY

# 3. 启动
python main.py
```

启动成功后，在飞书群 `@SRE助手 <问题>` 或私聊发送问题，即可收到回复。

## 配置项说明（.env）

| 变量 | 必填 | 说明 |
|------|------|------|
| `FEISHU_APP_ID` | ✅ | 飞书应用 App ID（`cli_` 开头） |
| `FEISHU_APP_SECRET` | ✅ | 飞书应用 App Secret |
| `FEISHU_DOMAIN` | ❌ | `feishu`（国内，默认）/ `lark`（国际版） |
| `DIFY_API_BASE` | ✅ | Dify API 地址，默认 `https://api.dify.ai/v1` |
| `DIFY_API_KEY` | ✅ | Dify 应用 API Key（`app-` 开头） |
| `DIFY_TIMEOUT_SECONDS` | ❌ | Dify 接口超时，默认 60 |
| `CONVERSATION_TTL_SECONDS` | ❌ | 会话上下文有效期（秒），默认 1800 |
| `FEISHU_USE_CARD` | ❌ | 是否用卡片消息回复，默认 `true` |

## 会话（多轮上下文）

- 默认按 `user_id` 缓存 Dify `conversation_id`，实现追问上下文（如「如果是 Java 应用呢？」）。
- 超过 `CONVERSATION_TTL_SECONDS` 无交互自动开启新会话。
- 用户发送「新对话 / 清除上下文 / /reset /new」可手动重置上下文。

## 里程碑对照

| 里程碑 | 对应实现 |
|--------|----------|
| Dify 知识库搭建 | 在 Dify UI 完成；示例文档见 `knowledge_samples/` |
| Dify 工作流调试 | 在 Dify UI 完成 |
| Dify API 联调 | `dify_client.py`（blocking 模式 + conversation_id） |
| 飞书机器人开发 | `feishu_handler.py`（长连接 + 后台线程 + 卡片回复） |
| 打磨交付 | `conversation_store.py`（会话过期）+ 消息去重 + 错误兜底 |

## 常见问题

- **启动报「缺少必要配置」**：未填写 `.env`，请复制 `.env.example` 并补全三项必填配置。
- **收不到消息**：确认事件订阅选的是「长连接」、已添加 `im.message.receive_v1`、应用已发布并通过审核、机器人已加入群。
- **收到重复回复**：本服务已内置 `message_id` 去重，若仍重复请检查是否部署了多个客户端实例（长连接为集群模式，多实例会随机派发，建议单实例运行）。
- **回答体验差**：优先优化知识库文档结构与分段策略，再调整工作流系统提示词。
