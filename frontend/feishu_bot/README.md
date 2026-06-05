# Feishu Bot 方案 A

本目录提供一套可直接改造的飞书 Bot 示例方案，包含：
- 3 张飞书交互式卡片 JSON 模板
- 1 张三案例合集卡片 JSON 模板
- 1 个 Python 推送脚本 `send_feishu_card.py`
- 1 份使用说明文档

## 目录结构

```text
feishu_bot/
├── case_01_card.json
├── case_02_card.json
├── case_03_card.json
├── combined_card.json
├── send_feishu_card.py
└── README.md
```

## 1. 配置 Webhook URL

打开 `send_feishu_card.py`，找到下面这行：

```python
WEBHOOK_URL = "YOUR_WEBHOOK_URL"
```

将 `YOUR_WEBHOOK_URL` 替换为你的飞书群机器人 Webhook 地址，例如：

```python
WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

> 注意：请不要把真实 Webhook 地址提交到公共代码仓库中。

## 2. 替换占位符内容

### 卡片文件说明

- `case_01_card.json`：Case 01 卡片
- `case_02_card.json`：Case 02 卡片
- `case_03_card.json`：Case 03 卡片

### 需要替换的字段

每张卡片都包含以下占位符内容，你可以直接编辑对应 JSON 文件进行替换：

1. **直播间标题**
   - 示例占位符：`Placeholder Case Title 01`
   - 对应位置：卡片 header 标题、正文中的“直播间标题”字段

2. **内容概括**
   - 示例占位符：`一段对该直播间内容的简要描述，2~3 句话。`
   - 建议填写为该直播间案例亮点、玩法、转化特征等简述

3. **评语**
   - 示例占位符：`评委对该 Case 的点评`
   - 建议填写为评审结论、亮点点评或优化建议

4. **跳转链接**
   - 当前默认值：`http://localhost:8000/tiktok-live-case-demo.html`
   - 如果后续 HTML 页面地址变更，可同步修改卡片 JSON 文件中的 `url`

## 3. 如何运行脚本

请先确保本机安装 Python 3。

进入目录后执行：

```bash
cd feishu_bot
python3 send_feishu_card.py 1
```

### 参数说明

脚本支持以下参数：

- `1`：发送 Case 01
- `2`：发送 Case 02
- `3`：发送 Case 03
- `all`：发送 1 张三案例合集卡片

### 运行示例

发送单张卡片：

```bash
python3 send_feishu_card.py 2
```

发送全部卡片：

```bash
python3 send_feishu_card.py all
```

## 4. 补充说明

- 当前脚本通过 **飞书群机器人 Webhook** 发送消息。
- 如果 Webhook 未替换，脚本会直接报错并提示你先配置。
- 如果卡片 JSON 格式被误改，飞书可能会返回参数错误；这时建议先检查 JSON 结构是否完整。
- 当前方案适合你这次的“卡片消息 + 跳转 HTML 页面”场景，后续也可以继续扩展为：
  - 增加更多 Case 模板
  - 把占位符改为从 Excel / JSON / CMS 动态读取
  - 接入本地 HTML 服务或线上落地页地址
