#!/usr/bin/env python
"""
Webhook客户端模块
用于向Webhook服务器发送各类通知消息
"""

import json
import time
import aiohttp
from loguru import logger
from typing import Dict, Any, Optional, List, Union, Tuple
from enum import Enum

# 尝试导入配置，如果失败则使用默认值
try:
    from config.config import WEBHOOK_URL, WEBHOOK_ADDITIONAL_HEADERS
except ImportError:
    logger.warning("未找到配置模块，将使用默认值")
    WEBHOOK_URL = None
    WEBHOOK_ADDITIONAL_HEADERS = {}

class NotificationType(Enum):
    """通知类型枚举"""
    TRADE = "trade"
    POSITION = "position_update"
    ERROR = "error"
    STATUS = "status"
    SYSTEM = "system"
    CUSTOM = "custom"

class StatusType(Enum):
    """状态类型枚举"""
    INFO = "info"
    WARNING = "warning"
    SUCCESS = "success"
    ERROR = "error"

class TradeSide(Enum):
    """交易方向枚举"""
    BUY = "buy"
    SELL = "sell"

class WebhookClient:
    """Webhook客户端类，用于发送消息到webhook服务器"""
    
    def __init__(self, webhook_url: Optional[str] = None, additional_headers: Optional[Dict[str, str]] = None):
        """初始化webhook客户端
        
        Args:
            webhook_url: webhook URL，如果不提供则使用配置中的URL
            additional_headers: 额外的请求头
        """
        self.webhook_url = webhook_url or WEBHOOK_URL
        self.base_headers = {
            "Content-Type": "application/json",
            **(additional_headers or WEBHOOK_ADDITIONAL_HEADERS or {})
        }
    
    async def send(self, data: Dict[str, Any]) -> bool:
        """发送数据到webhook
        
        Args:
            data: 要发送的数据
            
        Returns:
            发送是否成功
        """
        if not self.webhook_url:
            logger.warning("⚠️ Webhook URL未配置，跳过通知")
            return False
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=data,
                    headers=self.base_headers,
                    timeout=10  # 添加超时设置
                ) as response:
                    response_text = await response.text()
                    if 200 <= response.status < 300:
                        logger.info(f"✅ Webhook通知发送成功: {response.status}")
                        return True
                    else:
                        logger.error(f"❌ 发送webhook通知失败. 状态码: {response.status}, 响应: {response_text}")
                        return False
        except aiohttp.ClientError as e:
            logger.error(f"❌ 发送webhook通知时出现网络错误: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ 发送webhook通知时出现未知错误: {e}")
            return False
    
    def _create_base_notification(self, 
                                event_type: Union[NotificationType, str], 
                                description: str = None, 
                                timestamp: int = None) -> Dict[str, Any]:
        """创建基础通知数据结构
        
        Args:
            event_type: 事件类型
            description: 描述信息
            timestamp: 时间戳（毫秒）
            
        Returns:
            基础通知数据
        """
        if isinstance(event_type, NotificationType):
            event_type = event_type.value
            
        notification = {
            "event_type": event_type,
            "timestamp": timestamp or int(time.time() * 1000)
        }
        
        if description:
            notification["description"] = description
            
        return notification
    
    async def send_trade(self,
                        symbol: str,
                        side: Union[TradeSide, str],
                        price: float,
                        amount: float,
                        operation: str = None,
                        trader_name: str = None,
                        is_close: bool = False,
                        skipped: bool = False,
                        skip_reason: str = None,
                        leverage: Optional[int] = None,
                        stop_loss_price: Optional[float] = None,
                        take_profit_price: Optional[float] = None,
                        additional_data: Dict[str, Any] = None) -> bool:
        """发送交易通知
        
        Args:
            symbol: 交易对符号
            side: 交易方向 ('buy' 或 'sell')
            price: 成交价格
            amount: 成交数量
            operation: 自定义操作名称（如不提供则自动生成）
            trader_name: 交易员名称
            is_close: 是否为平仓操作
            skipped: 是否跳过交易
            skip_reason: 跳过交易的原因
            leverage: 杠杆倍数
            stop_loss_price: 止损价格
            take_profit_price: 止盈价格
            additional_data: 额外数据
            
        Returns:
            发送是否成功
        """
        # 处理交易方向枚举
        if isinstance(side, TradeSide):
            side = side.value
            
        # 确定操作类型
        if not operation:
            operation = "平仓" if is_close else ("买入" if side == "buy" else "卖出")
            if skipped:
                operation = f"跳过{operation}"
        
        # 格式化交易数据
        value = price * amount
        
        trade_data = {
            "symbol": symbol,
            "side": side,
            "price": price,
            "amount": amount,
            "value": value,
            "operation": operation,
            "timestamp": int(time.time() * 1000),
            "skipped": skipped
        }
        
        # 添加可选数据
        if trader_name:
            trade_data["trader_name"] = trader_name
        if leverage:
            trade_data["leverage"] = leverage
        if stop_loss_price:
            trade_data["stop_loss_price"] = stop_loss_price
        if take_profit_price:
            trade_data["take_profit_price"] = take_profit_price
        if skip_reason:
            trade_data["skip_reason"] = skip_reason
        if additional_data:
            trade_data.update(additional_data)
        
        # 构建通知消息
        notification = self._create_base_notification(NotificationType.TRADE)
        notification["data"] = trade_data
        
        # 构建美观的描述信息
        emoji_prefix = "🔄" if is_close else ("🟢" if side == "buy" else "🔴")
        if skipped:
            emoji_prefix = "⏭️"
            
        # 添加换行并添加其他可选信息
        description_parts = [
            f"{emoji_prefix} **{operation}**: {symbol}",
            f"💰 数量: {amount} @ {price}",
            f"💵 总价值: ${value:.2f}"
        ]
        
        if leverage:
            description_parts.append(f"📊 杠杆: {leverage}x")
        if stop_loss_price:
            sl_percentage = abs((stop_loss_price - price) / price * 100)
            description_parts.append(f"🛑 止损: {stop_loss_price} ({sl_percentage:.2f}%)")
        if take_profit_price:
            tp_percentage = abs((take_profit_price - price) / price * 100)
            description_parts.append(f"🎯 止盈: {take_profit_price} ({tp_percentage:.2f}%)")
        if trader_name:
            description_parts.append(f"👤 交易员: {trader_name}")
        if skipped and skip_reason:
            description_parts.append(f"⚠️ 跳过原因: {skip_reason}")
        
        # 使用换行符连接信息
        notification["description"] = "\n".join(description_parts)
        
        return await self.send(notification)
    
    async def send_position_update(self,
                                  symbol: str,
                                  amount: float,
                                  entry_price: Optional[float] = None,
                                  current_price: Optional[float] = None,
                                  pnl: Optional[float] = None,
                                  pnl_percentage: Optional[float] = None,
                                  liquidation_price: Optional[float] = None,
                                  margin: Optional[float] = None,
                                  leverage: Optional[int] = None,
                                  additional_data: Dict[str, Any] = None) -> bool:
        """发送持仓更新通知
        
        Args:
            symbol: 交易对符号
            amount: 持仓数量
            entry_price: 入场价格
            current_price: 当前价格
            pnl: 盈亏金额
            pnl_percentage: 盈亏百分比
            liquidation_price: 强平价格
            margin: 保证金
            leverage: 杠杆倍数
            additional_data: 额外数据
            
        Returns:
            发送是否成功
        """
        # 格式化持仓数据
        position_data = {
            "symbol": symbol,
            "amount": amount,
            "timestamp": int(time.time() * 1000),
        }
        
        # 添加可选数据
        if entry_price is not None:
            position_data["entry_price"] = entry_price
        if current_price is not None:
            position_data["current_price"] = current_price
        if pnl is not None:
            position_data["pnl"] = pnl
        if pnl_percentage is not None:
            position_data["pnl_percentage"] = pnl_percentage
        if liquidation_price is not None:
            position_data["liquidation_price"] = liquidation_price
        if margin is not None:
            position_data["margin"] = margin
        if leverage is not None:
            position_data["leverage"] = leverage
        if additional_data:
            position_data.update(additional_data)
        
        # 构建通知消息
        notification = self._create_base_notification(NotificationType.POSITION)
        notification["data"] = position_data
        
        # 添加美观的描述信息
        position_type = "多头" if amount > 0 else "空头" if amount < 0 else "无持仓"
        emoji_prefix = "🟢" if amount > 0 else "🔴" if amount < 0 else "⚪"
        
        # 构建PNL展示
        pnl_display = ""
        if pnl is not None and pnl_percentage is not None:
            pnl_emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
            pnl_display = f"{pnl_emoji} 盈亏: ${pnl:.2f} ({pnl_percentage:.2f}%)"
        
        # 构建描述文本
        description_parts = [
            f"{emoji_prefix} **持仓更新**: {symbol} ({position_type})"
        ]
        
        if amount:
            description_parts.append(f"📊 数量: {abs(amount)}")
        if entry_price:
            description_parts.append(f"💲 入场价: {entry_price}")
        if current_price:
            description_parts.append(f"📈 当前价: {current_price}")
        if pnl_display:
            description_parts.append(pnl_display)
        if liquidation_price:
            description_parts.append(f"☢️ 强平价: {liquidation_price}")
        if leverage:
            description_parts.append(f"📊 杠杆: {leverage}x")
        if margin:
            description_parts.append(f"💰 保证金: ${margin:.2f}")
        
        notification["description"] = "\n".join(description_parts)
        
        return await self.send(notification)
    
    async def send_error(self,
                         error_message: str,
                         error_type: str = "system_error",
                         error_details: Dict[str, Any] = None) -> bool:
        """发送错误通知
        
        Args:
            error_message: 错误消息
            error_type: 错误类型
            error_details: 错误详情
            
        Returns:
            发送是否成功
        """
        # 格式化错误数据
        error_data = {
            "error_type": error_type,
            "message": error_message,
            "timestamp": int(time.time() * 1000)
        }
        
        if error_details:
            error_data["details"] = error_details
        
        # 构建通知消息
        notification = self._create_base_notification(NotificationType.ERROR)
        notification.update(error_data)
        
        # 添加美观的描述信息
        description_parts = [
            f"❌ **错误报告**",
            f"📋 类型: {error_type}",
            f"📝 消息: {error_message}"
        ]
        
        if error_details:
            details_str = json.dumps(error_details, ensure_ascii=False, indent=2)
            description_parts.append(f"🔍 详情: ```\n{details_str}\n```")
        
        notification["description"] = "\n".join(description_parts)
        
        return await self.send(notification)
    
    async def send_status(self,
                         status_message: str,
                         status_type: Union[StatusType, str] = StatusType.INFO,
                         additional_data: Dict[str, Any] = None) -> bool:
        """发送状态通知
        
        Args:
            status_message: 状态消息
            status_type: 状态类型
            additional_data: 额外数据
            
        Returns:
            发送是否成功
        """
        # 处理状态类型枚举
        if isinstance(status_type, StatusType):
            status_type_str = status_type.value
        else:
            status_type_str = status_type
        
        # 格式化状态数据
        status_data = {
            "status_type": status_type_str,
            "message": status_message,
            "timestamp": int(time.time() * 1000)
        }
        
        if additional_data:
            status_data.update(additional_data)
        
        # 构建通知消息
        notification = self._create_base_notification(NotificationType.STATUS)
        notification.update(status_data)
        
        # 根据状态类型设置前缀
        emoji_prefix = "ℹ️"
        type_display = "信息"
        
        if status_type_str == "warning":
            emoji_prefix = "⚠️"
            type_display = "警告"
        elif status_type_str == "success":
            emoji_prefix = "✅"
            type_display = "成功"
        elif status_type_str == "error":
            emoji_prefix = "❌"
            type_display = "错误"
        
        # 添加美观的描述信息
        description_parts = [
            f"{emoji_prefix} **{type_display}通知**",
            f"📝 {status_message}"
        ]
        
        if additional_data:
            additional_str = "\n".join([f"{k}: {v}" for k, v in additional_data.items()])
            description_parts.append(f"📊 附加信息:\n```\n{additional_str}\n```")
        
        notification["description"] = "\n".join(description_parts)
        
        return await self.send(notification)
    
    async def send_custom(self, 
                         event_type: str, 
                         description: str, 
                         data: Dict[str, Any] = None) -> bool:
        """发送自定义通知
        
        Args:
            event_type: 事件类型
            description: 描述信息
            data: 自定义数据
            
        Returns:
            发送是否成功
        """
        # 构建通知消息
        notification = self._create_base_notification(event_type, description)
        
        if data:
            notification["data"] = data
        
        return await self.send(notification)


# 创建默认客户端实例，方便直接调用
default_client = WebhookClient()

# 为了向后兼容提供的简便函数
async def send_webhook(data: Dict[str, Any]) -> bool:
    """发送数据到webhook (向后兼容函数)
    
    Args:
        data: 要发送的数据
        
    Returns:
        发送是否成功
    """
    return await default_client.send(data)

async def send_trade_notification(
    symbol: str,
    side: Union[str, TradeSide],
    price: float,
    amount: float,
    trader_name: str = None,
    is_close: bool = False,
    skipped: bool = False,
    skip_reason: str = None,
    leverage: int = None,
    stop_loss_price: float = None,
    take_profit_price: float = None
) -> bool:
    """发送交易通知 (向后兼容函数)
    
    Args:
        symbol: 交易对符号
        side: 交易方向 ('buy' 或 'sell')
        price: 成交价格
        amount: 成交数量
        trader_name: 交易员名称
        is_close: 是否为平仓操作
        skipped: 是否跳过交易
        skip_reason: 跳过交易的原因
        leverage: 杠杆倍数
        stop_loss_price: 止损价格
        take_profit_price: 止盈价格
        
    Returns:
        发送是否成功
    """
    return await default_client.send_trade(
        symbol=symbol,
        side=side,
        price=price,
        amount=amount,
        trader_name=trader_name,
        is_close=is_close,
        skipped=skipped,
        skip_reason=skip_reason,
        leverage=leverage,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price
    )

async def send_position_notification(position_data: Dict[str, Any]) -> bool:
    """发送持仓更新通知 (向后兼容函数)
    
    Args:
        position_data: 持仓数据
        
    Returns:
        发送是否成功
    """
    return await default_client.send_position_update(
        symbol=position_data.get("symbol", "未知交易对"),
        amount=position_data.get("amount", 0),
        entry_price=position_data.get("entry_price"),
        current_price=position_data.get("current_price"),
        pnl=position_data.get("pnl"),
        pnl_percentage=position_data.get("pnl_percentage"),
        liquidation_price=position_data.get("liquidation_price"),
        margin=position_data.get("margin"),
        leverage=position_data.get("leverage"),
        additional_data=position_data
    )

async def send_error_notification(error_message: str, error_type: str = "system_error") -> bool:
    """发送错误通知 (向后兼容函数)
    
    Args:
        error_message: 错误消息
        error_type: 错误类型
        
    Returns:
        发送是否成功
    """
    return await default_client.send_error(error_message, error_type)

async def send_status_notification(status_message: str, status_type: str = "info") -> bool:
    """发送状态通知 (向后兼容函数)
    
    Args:
        status_message: 状态消息
        status_type: 状态类型
        
    Returns:
        发送是否成功
    """
    return await default_client.send_status(status_message, status_type) 