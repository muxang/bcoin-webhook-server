# Bcoin Webhook 转发服务器

## 项目简介

这是一个高度可配置的 Webhook 转发服务器，用于接收 Bcoin 或其他系统的交易信号并转发到多个目标渠道，如微信群、企业微信、钉钉、飞书、Discord 等平台。

## 主要功能

- **多路由支持**：根据不同 URL 路径接收消息并转发到不同目标
- **多目标转发**：同时将消息发送到多个配置的目标渠道
- **消息过滤**：按事件类型、交易对等条件筛选转发消息
- **消息预处理**：支持字段映射、类型转换、内容提取等操作
- **模板系统**：使用预定义模板格式化不同类型的消息
- **自定义格式化**：支持针对不同目标自定义转发消息格式
- **灵活配置**：通过 JSON 配置文件轻松修改转发规则，无需修改代码
- **完整 REST API**：提供管理接口，可查询历史消息、管理目标渠道和路由

## 配置文件详细说明

Webhook 系统的配置主要通过`config/webhook_config.json`文件进行管理。该配置文件包含以下主要部分：

### 1. 配置文件结构

```json
{
  "targets": [...],      // 转发目标配置
  "routes": {...},       // 路由配置
  "templates": {...},    // 消息模板配置
  "message_format": {...} // 全局消息格式配置
}
```

### 2. 转发目标配置

`targets`部分定义了 webhook 消息可以被转发到的目标渠道：

```json
"targets": [
  {
    "id": "wechat_group",         // 目标唯一ID，用于在路由中引用
    "name": "交易通知微信群",      // 目标名称，便于识别
    "type": "wechat",            // 目标类型: wechat/feishu/dingtalk/discord/custom
    "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE", // 转发地址
    "enabled": true,             // 是否启用此目标
    "headers": {                 // 可选的HTTP请求头
      "Content-Type": "application/json"
    },
    "event_types": ["trade", "position_update", "error"], // 可选的事件类型过滤器
    "symbols": ["BTC/USDT", "ETH/USDT"],                  // 可选的交易对过滤器
    "format_type": "text",       // 格式化类型: text/template，可选
    "format": {                  // 自定义消息格式，根据format_type解释
      "trade": "🔔交易信号: {symbol} {operation} 价格:{price}",
      "error": "❌错误: {message}"
    }
  }
]
```

**目标类型说明：**

- `wechat`: 企业微信机器人
- `wechat_personal`: 普通微信个人号转发
- `feishu`: 飞书机器人
- `dingtalk`: 钉钉机器人
- `discord`: Discord Webhook
- 其他类型会按原始格式发送

**格式类型说明：**

- `text`: 文本格式化，根据事件类型使用不同文本模板
- `template`: JSON 模板格式化，支持复杂结构

### 3. 路由配置

`routes`部分定义了 URL 路径与转发目标的映射关系：

```json
"routes": {
  "/webhook": {                   // URL路径
    "target_ids": ["wechat_group"], // 要转发到的目标ID列表
    "description": "通用webhook路由，处理所有类型的消息", // 路由描述
    "methods": ["POST"],         // 支持的HTTP方法
    "headers": {                 // 可选的HTTP头部匹配条件
      "X-API-Key": "your-api-key-here"
    },
    "query_params": {            // 可选的查询参数匹配条件
      "token": "your-token-here"
    },
    "template": "trade",         // 可选的消息模板名称
    "preprocess": {              // 可选的消息预处理配置
      "field_mapping": {         // 字段映射
        "symbol": "data.symbol",
        "price": "data.price"
      },
      "transformations": {       // 字段转换
        "price": "to_float",
        "amount": "to_float"
      },
      "include_fields": ["symbol", "price", "amount"], // 字段过滤
      "add_fields": {            // 添加固定字段
        "source": "binance",
        "event_type": "trade"
      }
    }
  },
  "/webhook/error": {            // 另一个路由示例
    "target_ids": ["wechat_group"],
    "description": "错误通知路由",
    "methods": ["POST"],
    "template": "error"
  }
}
```

**路由配置参数说明：**

- `target_ids`: 消息将转发到的目标 ID 列表，必须在 targets 中定义
- `methods`: 支持的 HTTP 方法，默认为["POST"]
- `headers`: 必须匹配的请求头，可用于验证 API 密钥等
- `query_params`: 必须匹配的 URL 查询参数
- `template`: 应用的消息模板名称，定义在 templates 部分
- `preprocess`: 消息预处理配置，用于转换接收到的消息格式

### 4. 消息模板配置

`templates`部分定义了可重用的消息模板：

```json
"templates": {
  "trade": {                     // 模板名称
    "event_type": "trade",       // 事件类型
    "description": "交易信号: {symbol} {operation} 价格: {price} 数量: {amount}", // 描述格式
    "data": {                    // 数据字段模板
      "symbol": "{symbol}",
      "operation": "{operation}",
      "price": "{price}",
      "amount": "{amount}"
    }
  },
  "error": {
    "event_type": "error",
    "description": "错误通知: {message}",
    "data": {
      "message": "{message}"
    }
  }
}
```

**模板用法说明：**

- 模板会应用于经过预处理后的消息
- 模板中的大括号`{}`里是变量，会被实际值替换
- 可以为不同类型的事件定义不同的模板

### 5. 预处理配置详解

预处理配置是路由的一部分，用于在应用模板前转换接收到的消息：

**字段映射 (field_mapping)**:

- 将源数据中的字段映射到新的字段名
- 支持嵌套字段路径，如`data.price`表示访问 data 对象中的 price 属性
- 源路径可以是复杂表达式，如计算`value`字段：`"value": "data.price * data.amount"`

**字段转换 (transformations)**:

- `to_string`: 转换为字符串
- `to_int`: 转换为整数
- `to_float`: 转换为浮点数
- `to_bool`: 转换为布尔值
- `format:格式字符串`: 使用格式字符串格式化，如`format:${value}元`

**字段过滤 (include_fields)**:

- 只保留指定的字段，丢弃其他所有字段

**添加固定字段 (add_fields)**:

- 为消息添加固定值的字段，不依赖输入消息

### 6. 完整配置示例

下面是一个完整的配置示例，包含多个目标和路由：

```json
{
  "targets": [
    {
      "id": "wechat_group",
      "name": "交易通知微信群",
      "type": "wechat",
      "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE",
      "enabled": true
    },
    {
      "id": "discord",
      "name": "Discord通知",
      "type": "discord",
      "url": "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL",
      "enabled": true,
      "format_type": "template",
      "format": {
        "content": "**{event_type}**: {description}",
        "embeds": [
          {
            "title": "{symbol} {operation}",
            "description": "价格: {price}\n数量: {amount}",
            "color": 3447003
          }
        ]
      }
    }
  ],
  "routes": {
    "/webhook": {
      "target_ids": ["wechat_group", "discord"],
      "description": "通用webhook路由，处理所有类型的消息",
      "methods": ["POST"]
    },
    "/webhook/trade": {
      "target_ids": ["wechat_group"],
      "description": "交易信号路由",
      "methods": ["POST"],
      "template": "trade",
      "preprocess": {
        "field_mapping": {
          "symbol": "data.symbol",
          "operation": "data.operation",
          "price": "data.price",
          "amount": "data.amount"
        },
        "transformations": {
          "price": "to_float",
          "amount": "to_float"
        }
      }
    }
  },
  "templates": {
    "trade": {
      "event_type": "trade",
      "description": "交易信号: {symbol} {operation} 价格: {price} 数量: {amount}",
      "data": {
        "symbol": "{symbol}",
        "operation": "{operation}",
        "price": "{price}",
        "amount": "{amount}"
      }
    },
    "error": {
      "event_type": "error",
      "description": "错误通知: {message}",
      "data": {
        "message": "{message}"
      }
    }
  },
  "message_format": {
    "trade": "交易信号: {symbol} {operation} 价格: {price} 数量: {amount}",
    "position_update": "持仓更新: {symbol} 数量: {amount} 价格: {current_price} 盈亏: {pnl}",
    "error": "错误通知: {message}",
    "status": "状态通知: {message}"
  }
}
```

### 7. 最简单的配置

如果你只需要一个简单的配置，可以使用以下最小配置：

```json
{
  "targets": [
    {
      "id": "wechat_group",
      "name": "交易通知微信群",
      "type": "wechat",
      "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE",
      "enabled": true
    }
  ],
  "routes": {
    "/webhook": {
      "target_ids": ["wechat_group"],
      "description": "通用webhook路由，处理所有类型的消息",
      "methods": ["POST"]
    }
  }
}
```

这个最小配置会将所有发送到`/webhook`路径的消息直接转发到指定的微信群。

### 普通微信个人号配置示例

如果你想将消息转发到普通微信个人号，可以使用以下配置：

```json
{
  "targets": [
    {
      "id": "wx_personal",
      "name": "微信个人号",
      "type": "wechat_personal",
      "url": "http://your-wechat-bot-api/send", // 你的微信机器人API地址
      "wxid": "wxid_xxxxxxxx", // 接收消息的微信ID
      "enabled": true,
      "format_type": "text",
      "format": {
        "trade": "🔔 交易信号\n交易对: {symbol}\n操作: {operation}\n价格: {price}\n数量: {amount}",
        "error": "❌ 错误通知: {message}",
        "default": "{description}"
      }
    }
  ],
  "routes": {
    "/webhook/wx": {
      "target_ids": ["wx_personal"],
      "description": "微信个人号通知路由",
      "methods": ["POST"]
    }
  }
}
```

**注意事项:**

1. `wxid` 参数是必须的，用于指定接收消息的微信 ID
2. `url` 应指向你的微信机器人 API 服务地址
3. 消息将以 `{"type": "sendText", "data": {"wxid": "wxid_xxx", "msg": "消息内容"}}` 格式发送
4. 需要有一个运行中的微信机器人 API 服务（比如基于 WeChat PC Hook 的机器人）

这种配置适用于一些常见的微信机器人框架，如 WeChatFerry、wxbot 等。

## 安装与启动

```bash
# 克隆项目
git clone https://github.com/yourusername/bcoin-webhook-server.git
cd bcoin-webhook-server

# 安装依赖
pip install -r requirements.txt

# 启动服务器
python webhook_server.py --host 0.0.0.0 --port 8080 --config config/webhook_config.json --log-level INFO
```

## 命令行参数

- `--host`: 监听地址，默认为`0.0.0.0`
- `--port`: 监听端口，默认为`8080`
- `--config`: 配置文件路径，默认为`config/webhook_config.json`
- `--log-level`: 日志级别，可选值为`DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`，默认为`INFO`

## API 接口

### Webhook 接收接口

- `POST /webhook`: 默认的 webhook 接收路径
- 自定义路径: 根据配置文件中的`routes`配置动态生成

### 目标管理接口

- `GET /targets`: 获取所有转发目标
- `POST /targets`: 添加新的转发目标
- `PUT /targets/{target_id}`: 更新转发目标
- `DELETE /targets/{target_id}`: 删除转发目标

### 路由管理接口

- `GET /routes`: 获取所有路由配置
- `POST /routes`: 添加新的路由
- `PUT /routes/{path}`: 更新路由配置
- `DELETE /routes/{path}`: 删除路由

### 测试接口

- `POST /test?target_id={target_id}`: 向指定目标发送测试消息
- `POST /test?route_path={route_path}`: 通过指定路由发送测试消息
- `POST /test`: 向所有启用的目标发送测试消息

### 历史记录接口

- `GET /history?limit={limit}`: 获取最近的消息历史，limit 参数指定返回条数

## 高级功能

### 消息预处理

预处理配置可以对接收到的消息进行变换，支持以下操作：

- **字段映射**: 将源字段映射到目标字段，支持嵌套路径
- **字段过滤**: 只保留需要的字段
- **字段变换**: 对字段进行类型转换或格式化
- **添加固定字段**: 为每个消息添加固定内容

示例:

```json
{
  "preprocess": {
    "field_mapping": {
      "symbol": "data.pair",
      "price": "data.price"
    },
    "transformations": {
      "price": "to_float",
      "amount": "format:${value}个"
    },
    "include_fields": ["symbol", "price", "amount"],
    "add_fields": {
      "source": "binance",
      "timestamp": 1621234567890
    }
  }
}
```

### 自定义消息格式

每个目标可以配置自己的消息格式化规则：

- **text 格式**: 直接使用文本模板，适用于微信、钉钉等
- **template 格式**: 使用 JSON 模板，支持复杂结构，适用于 Discord 等

示例:

```json
{
  "format_type": "text",
  "format": {
    "trade": "🔔交易提醒: {symbol} {operation} 价格:{price}",
    "error": "❌错误: {message}"
  }
}
```

## 目标渠道支持

已内置支持以下渠道的消息格式:

- **企业微信**: 通过企业微信机器人 webhook 发送消息
- **钉钉**: 通过钉钉机器人 webhook 发送消息
- **飞书**: 通过飞书机器人 webhook 发送消息
- **Discord**: 通过 Discord webhook 发送消息

对于其他渠道，可通过配置自定义格式进行支持。

## 日志

服务器日志保存在`logs/webhook_server.log`文件中，会自动按大小进行轮转。

## Docker 支持

```bash
# 构建Docker镜像
docker build -t bcoin-webhook-server .

# 运行Docker容器
docker run -p 8080:8080 -v $(pwd)/config:/app/config -v $(pwd)/logs:/app/logs bcoin-webhook-server
```

## 问题反馈

如有问题或建议，请提交 Issue。

## 开源协议

MIT

## 客户端配置说明

### 1. 配置文件

客户端可以通过`config/config.py`文件进行配置:

```python
# config/config.py

# Webhook服务器URL
WEBHOOK_URL = "http://your-webhook-server:8080/webhook"

# 额外的请求头（如果需要）
WEBHOOK_ADDITIONAL_HEADERS = {
    "Authorization": "Bearer your-token-here",
    "X-API-Key": "your-api-key-here"
}
```

### 2. 客户端用法

以下是详细的客户端使用方法：

#### 基本使用

```python
from webhook_client import WebhookClient, TradeSide, StatusType

# 创建客户端实例
client = WebhookClient(webhook_url="http://your-webhook-server:8080/webhook")

# 发送交易通知
await client.send_trade(
    symbol="BTC/USDT",
    side=TradeSide.BUY,
    price=50000.50,
    amount=0.1
)

# 发送持仓更新
await client.send_position_update(
    symbol="ETH/USDT",
    amount=2.0,
    entry_price=3000.75,
    current_price=3200.25,
    pnl=399.00,
    pnl_percentage=6.65
)

# 发送错误通知
await client.send_error(
    error_message="API连接超时",
    error_type="connection_error"
)

# 发送状态通知
await client.send_status(
    status_message="交易系统已启动",
    status_type=StatusType.SUCCESS
)
```

#### 使用兼容函数

对于现有代码，可以使用向后兼容的函数：

```python
from webhook_client import (
    send_trade_notification,
    send_position_notification,
    send_error_notification,
    send_status_notification
)

# 发送交易通知
await send_trade_notification(
    symbol="BTC/USDT",
    side="buy",
    price=50000.50,
    amount=0.1
)

# 发送持仓更新
await send_position_notification({
    "symbol": "ETH/USDT",
    "amount": 2.0,
    "entry_price": 3000.75,
    "current_price": 3200.25,
    "pnl": 399.00,
    "pnl_percentage": 6.65
})

# 发送错误通知
await send_error_notification(
    error_message="API连接超时",
    error_type="connection_error"
)

# 发送状态通知
await send_status_notification(
    status_message="交易系统已启动",
    status_type="success"
)
```

#### 自定义通知

也可以发送自定义类型的通知：

```python
# 发送自定义通知
await client.send_custom(
    event_type="system_start",
    description="交易系统启动完成",
    data={
        "version": "1.2.3",
        "mode": "production",
        "startup_time_ms": 1250
    }
)
```

### 3. 消息格式

客户端自动为不同类型的消息生成美观的格式：

#### 交易通知格式

```
🟢 **买入**: BTC/USDT
💰 数量: 0.5 @ 50000.0
💵 总价值: $25000.00
📊 杠杆: 10x
🛑 止损: 48000.0 (4.00%)
🎯 止盈: 55000.0 (10.00%)
```

#### 持仓更新格式

```
🟢 **持仓更新**: ETH/USDT (多头)
📊 数量: 2.0
💲 入场价: 3000.75
📈 当前价: 3200.25
🟢 盈亏: $399.00 (6.65%)
📊 杠杆: 5x
```

#### 错误通知格式

```
❌ **错误报告**
📋 类型: connection_error
📝 消息: API连接超时
```

#### 状态通知格式

```
✅ **成功通知**
📝 交易系统已启动
```

### 4. 直接发送到企业微信

如果想直接发送到企业微信，无需经过 webhook 服务器：

```python
from webhook_client import WebhookClient

# 直接使用企业微信webhook URL
client = WebhookClient(
    webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE"
)

# 发送消息
await client.send_trade(
    symbol="BTC/USDT",
    side="buy",
    price=50000,
    amount=0.1
)
```

### 5. 消息类型说明

客户端支持以下主要消息类型：

- **交易消息** (`trade`): 用于发送交易信号，如开仓、平仓等
- **持仓更新** (`position_update`): 用于发送持仓状态变化
- **错误通知** (`error`): 用于发送系统或交易错误
- **状态通知** (`status`): 用于发送系统状态信息，如启动、停止等
- **自定义消息** (`custom`): 用于发送自定义类型的消息
