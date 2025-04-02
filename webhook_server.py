#!/usr/bin/env python
"""
独立运行的Webhook转发服务器
用于接收交易信号并转发到多个目标（包括微信群）
"""

import os
import sys
import json
import time
import re
import asyncio
import argparse
import aiohttp
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from datetime import datetime
import uvicorn
from typing import Dict, List, Optional, Any, Union, Callable

# 确保日志目录存在
os.makedirs("logs", exist_ok=True)

class WebhookForwarder:
    """Webhook转发服务器，接收交易信号并转发到多个目标"""
    
    def __init__(self, config_path: str = "config/webhook_config.json"):
        """初始化webhook转发器
        
        Args:
            config_path: 配置文件路径
        """
        # 创建FastAPI应用
        self.app = FastAPI(
            title="Bcoin Webhook转发服务器",
            description="接收交易信号并转发到多个目标",
            version="1.0.0"
        )
        
        # 添加CORS中间件
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # 加载配置
        self.config_path = config_path
        self.config = self._load_config()
        
        # 消息历史记录
        self.message_history = []
        self.max_history_size = 100
        
        # 注册路由
        self._register_routes()
        
        logger.info(f"Webhook转发服务器初始化完成，配置路径: {config_path}")
    
    def _load_config(self) -> dict:
        """加载配置文件"""
        default_config = {
            "targets": [],
            "routes": {
                "/webhook": {
                    "target_ids": [],
                    "description": "默认webhook路由",
                    "methods": ["POST"],
                    "headers": {},
                    "query_params": {},
                    "template": None,
                    "preprocess": None
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
        
        try:
            # 确保配置目录存在
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    logger.info(f"已加载配置文件: {self.config_path}")
                    
                    # 确保配置中有routes字段
                    if "routes" not in config:
                        config["routes"] = default_config["routes"]
                        logger.warning("配置文件中缺少routes字段，已添加默认配置")
                    
                    # 确保配置中有templates字段
                    if "templates" not in config:
                        config["templates"] = default_config["templates"]
                        logger.warning("配置文件中缺少templates字段，已添加默认配置")
                    
                    return config
            else:
                # 创建默认配置文件
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, indent=4, ensure_ascii=False)
                logger.warning(f"未找到配置文件，已创建默认配置: {self.config_path}")
                return default_config
        except Exception as e:
            logger.error(f"加载配置文件出错: {e}")
            return default_config
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logger.info(f"配置已保存到: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False
    
    def _register_routes(self):
        """注册API路由"""
        
        # 动态注册webhook路由
        for route_path, route_config in self.config.get("routes", {}).items():
            self._register_route(route_path, route_config)
        
        @self.app.get("/targets")
        async def get_targets():
            """获取所有转发目标"""
            return {"targets": self.config.get("targets", [])}
        
        @self.app.post("/targets")
        async def add_target(target: dict):
            """添加新的转发目标"""
            if "name" not in target or "url" not in target:
                raise HTTPException(status_code=400, detail="目标必须包含name和url字段")
            
            # 生成唯一ID
            if "id" not in target:
                target["id"] = f"target_{int(time.time())}"
            
            # 默认启用
            if "enabled" not in target:
                target["enabled"] = True
            
            # 添加到配置
            self.config["targets"].append(target)
            self._save_config()
            
            return {
                "status": "success",
                "message": f"已添加转发目标: {target['name']}",
                "target": target
            }
        
        @self.app.delete("/targets/{target_id}")
        async def delete_target(target_id: str):
            """删除转发目标"""
            targets = self.config.get("targets", [])
            initial_count = len(targets)
            
            # 过滤掉要删除的目标
            self.config["targets"] = [t for t in targets if t.get("id") != target_id]
            
            if len(self.config["targets"]) < initial_count:
                self._save_config()
                return {"status": "success", "message": f"已删除转发目标 ID: {target_id}"}
            else:
                raise HTTPException(status_code=404, detail=f"未找到ID为 {target_id} 的转发目标")
        
        @self.app.put("/targets/{target_id}")
        async def update_target(target_id: str, target_update: dict):
            """更新转发目标"""
            for i, target in enumerate(self.config.get("targets", [])):
                if target.get("id") == target_id:
                    # 更新目标配置
                    self.config["targets"][i].update(target_update)
                    self._save_config()
                    return {
                        "status": "success",
                        "message": f"已更新转发目标: {target.get('name')}",
                        "target": self.config["targets"][i]
                    }
            
            raise HTTPException(status_code=404, detail=f"未找到ID为 {target_id} 的转发目标")
        
        # 添加路由管理API
        @self.app.get("/routes")
        async def get_routes():
            """获取所有路由配置"""
            return {"routes": self.config.get("routes", {})}
        
        @self.app.post("/routes")
        async def add_route(route: dict):
            """添加新的路由"""
            if "path" not in route:
                raise HTTPException(status_code=400, detail="路由必须包含path字段")
            
            path = route["path"]
            if not path.startswith('/'):
                path = f"/{path}"
            
            # 创建路由配置
            route_config = {
                "target_ids": route.get("target_ids", []),
                "description": route.get("description", f"路由 {path}"),
                "methods": route.get("methods", ["POST"]),
                "headers": route.get("headers", {}),
                "query_params": route.get("query_params", {})
            }
            
            # 添加到配置
            self.config["routes"][path] = route_config
            self._save_config()
            
            # 重新注册路由
            self._register_route(path, route_config)
            
            return {
                "status": "success",
                "message": f"已添加路由: {path}",
                "route": {
                    "path": path,
                    **route_config
                }
            }
        
        @self.app.delete("/routes/{path}")
        async def delete_route(path: str):
            """删除路由"""
            # 确保路径格式正确
            if not path.startswith('/'):
                path = f"/{path}"
            
            if path in self.config.get("routes", {}):
                del self.config["routes"][path]
                self._save_config()
                return {"status": "success", "message": f"已删除路由: {path}"}
            else:
                raise HTTPException(status_code=404, detail=f"未找到路由: {path}")
        
        @self.app.put("/routes/{path}")
        async def update_route(path: str, route_update: dict):
            """更新路由配置"""
            # 确保路径格式正确
            if not path.startswith('/'):
                path = f"/{path}"
            
            if path in self.config.get("routes", {}):
                # 更新路由配置
                self.config["routes"][path].update(route_update)
                self._save_config()
                
                # 重新注册路由
                self._register_route(path, self.config["routes"][path])
                
                return {
                    "status": "success",
                    "message": f"已更新路由: {path}",
                    "route": {
                        "path": path,
                        **self.config["routes"][path]
                    }
                }
            else:
                raise HTTPException(status_code=404, detail=f"未找到路由: {path}")
        
        @self.app.get("/history")
        async def get_history(limit: int = 10):
            """获取消息历史"""
            return {"history": self.message_history[:limit]}
        
        @self.app.post("/test")
        async def send_test_message(target_id: Optional[str] = None, route_path: Optional[str] = None):
            """发送测试消息"""
            test_message = {
                "event_type": "test",
                "description": "这是一条测试消息",
                "timestamp": int(time.time() * 1000),
                "data": {
                    "symbol": "BTC/USDT",
                    "operation": "测试",
                    "price": 50000,
                    "amount": 0.1
                }
            }
            
            if target_id:
                # 发送到指定目标
                target = None
                for t in self.config.get("targets", []):
                    if t.get("id") == target_id:
                        target = t
                        break
                
                if not target:
                    raise HTTPException(status_code=404, detail=f"未找到ID为 {target_id} 的转发目标")
                
                result = await self.forward_to_target(test_message, target)
                return {
                    "status": "success" if result else "error",
                    "message": f"测试消息已发送到: {target.get('name')}",
                    "result": result
                }
            elif route_path:
                # 使用指定路由发送
                if not route_path.startswith('/'):
                    route_path = f"/{route_path}"
                
                if route_path not in self.config.get("routes", {}):
                    raise HTTPException(status_code=404, detail=f"未找到路由: {route_path}")
                
                route_config = self.config["routes"][route_path]
                results = await self.process_message(test_message, target_ids=route_config.get("target_ids", []))
                
                return {
                    "status": "success",
                    "message": f"测试消息已通过路由 {route_path} 发送",
                    "results": results
                }
            else:
                # 发送到所有启用的目标
                results = await self.process_message(test_message)
                return {
                    "status": "success",
                    "message": "测试消息已发送到所有启用的目标",
                    "results": results
                }
    
    def _register_route(self, route_path: str, route_config: dict):
        """注册单个路由
        
        Args:
            route_path: 路由路径
            route_config: 路由配置
        """
        # 确保路径格式正确
        if not route_path.startswith('/'):
            route_path = f"/{route_path}"
        
        # 获取支持的HTTP方法
        methods = route_config.get("methods", ["POST"])
        if not methods or not isinstance(methods, list):
            methods = ["POST"]
        
        # 创建请求处理依赖
        def request_filter(request: Request):
            """验证请求是否符合路由条件"""
            # 校验请求头
            if "headers" in route_config and route_config["headers"]:
                for header_name, header_value in route_config["headers"].items():
                    if header_name not in request.headers:
                        raise HTTPException(status_code=400, detail=f"缺少必要的请求头: {header_name}")
                    
                    # 如果配置了值，则需要精确匹配
                    if header_value and request.headers.get(header_name) != header_value:
                        raise HTTPException(status_code=400, detail=f"请求头 {header_name} 的值不匹配")
            
            # 校验查询参数
            if "query_params" in route_config and route_config["query_params"]:
                for param_name, param_value in route_config["query_params"].items():
                    if param_name not in request.query_params:
                        raise HTTPException(status_code=400, detail=f"缺少必要的查询参数: {param_name}")
                    
                    # 如果配置了值，则需要精确匹配
                    if param_value and request.query_params.get(param_name) != param_value:
                        raise HTTPException(status_code=400, detail=f"查询参数 {param_name} 的值不匹配")
            
            # 通过验证
            return True
        
        # 创建处理函数
        async def webhook_handler(request: Request, _: bool = Depends(request_filter)):
            try:
                # 获取请求体
                content_type = request.headers.get("content-type", "").lower()
                
                if "application/json" in content_type:
                    payload = await request.json()
                elif "application/x-www-form-urlencoded" in content_type:
                    form_data = await request.form()
                    payload = dict(form_data)
                elif "multipart/form-data" in content_type:
                    form_data = await request.form()
                    payload = dict(form_data)
                elif "text/plain" in content_type:
                    text = await request.body()
                    payload = {"text": text.decode('utf-8')}
                else:
                    # 尝试作为JSON解析
                    try:
                        payload = await request.json()
                    except:
                        # 作为文本处理
                        text = await request.body()
                        payload = {"text": text.decode('utf-8', errors='ignore')}
                
                # 消息预处理
                if route_config.get("preprocess"):
                    try:
                        payload = self._preprocess_message(payload, route_config["preprocess"])
                    except Exception as e:
                        logger.error(f"消息预处理失败: {e}")
                
                # 应用消息模板
                if route_config.get("template"):
                    try:
                        payload = self._apply_template(payload, route_config["template"])
                    except Exception as e:
                        logger.error(f"应用消息模板失败: {e}")
                
                # 增强消息内容
                if isinstance(payload, dict):
                    # 添加路由信息
                    payload.setdefault("_route", {
                        "path": route_path,
                        "method": request.method,
                        "timestamp": int(time.time() * 1000)
                    })
                
                # 记录接收路径
                logger.info(f"从路径 {route_path} 接收到消息")
                
                # 处理消息，使用路由特定的目标
                result = await self.process_message(
                    payload, 
                    target_ids=route_config.get("target_ids", [])
                )
                
                return {
                    "status": "success",
                    "message": f"消息已接收并通过路由 {route_path} 处理",
                    "results": result
                }
            except Exception as e:
                logger.error(f"处理webhook消息失败 ({route_path}): {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # 为每个HTTP方法注册路由
        for method in methods:
            method = method.upper()
            if method == "GET":
                self.app.get(route_path, dependencies=[Depends(request_filter)])(webhook_handler)
            elif method == "POST":
                self.app.post(route_path, dependencies=[Depends(request_filter)])(webhook_handler)
            elif method == "PUT":
                self.app.put(route_path, dependencies=[Depends(request_filter)])(webhook_handler)
            elif method == "DELETE":
                self.app.delete(route_path, dependencies=[Depends(request_filter)])(webhook_handler)
            elif method == "PATCH":
                self.app.patch(route_path, dependencies=[Depends(request_filter)])(webhook_handler)
            else:
                logger.warning(f"不支持的HTTP方法: {method}")
                continue
            
            logger.info(f"已注册webhook路由: {method} {route_path}")
    
    def _preprocess_message(self, message: dict, preprocess_config: dict) -> dict:
        """根据预处理配置处理消息
        
        Args:
            message: 原始消息
            preprocess_config: 预处理配置
            
        Returns:
            处理后的消息
        """
        if not preprocess_config:
            return message
        
        result = message
        
        # 字段映射
        if "field_mapping" in preprocess_config:
            mappings = preprocess_config["field_mapping"]
            
            # 创建新的字典存储映射后的值
            mapped_message = {}
            
            # 处理字段映射
            for target_field, source_path in mappings.items():
                value = self._get_nested_value(message, source_path)
                if value is not None:
                    # 支持嵌套字段路径
                    parts = target_field.split('.')
                    current = mapped_message
                    for i, part in enumerate(parts):
                        if i == len(parts) - 1:
                            current[part] = value
                        else:
                            if part not in current:
                                current[part] = {}
                            current = current[part]
            
            # 合并映射后的字段
            if preprocess_config.get("merge_mapped", True):
                result = {**result, **mapped_message}
            else:
                result = mapped_message
        
        # 字段过滤
        if "include_fields" in preprocess_config:
            include_fields = preprocess_config["include_fields"]
            filtered = {}
            
            for field in include_fields:
                value = self._get_nested_value(result, field)
                if value is not None:
                    # 设置嵌套字段
                    parts = field.split('.')
                    current = filtered
                    for i, part in enumerate(parts):
                        if i == len(parts) - 1:
                            current[part] = value
                        else:
                            if part not in current:
                                current[part] = {}
                            current = current[part]
            
            result = filtered
        
        # 字段变换
        if "transformations" in preprocess_config:
            transformations = preprocess_config["transformations"]
            
            for field, transform_type in transformations.items():
                value = self._get_nested_value(result, field)
                
                if value is not None:
                    if transform_type == "to_string":
                        transformed = str(value)
                    elif transform_type == "to_int":
                        try:
                            transformed = int(value)
                        except (ValueError, TypeError):
                            transformed = 0
                    elif transform_type == "to_float":
                        try:
                            transformed = float(value)
                        except (ValueError, TypeError):
                            transformed = 0.0
                    elif transform_type == "to_bool":
                        if isinstance(value, str):
                            transformed = value.lower() in ("true", "yes", "1", "y")
                        else:
                            transformed = bool(value)
                    elif transform_type.startswith("format:"):
                        # 格式化字符串
                        format_str = transform_type[7:]
                        try:
                            transformed = format_str.format(value=value)
                        except:
                            transformed = value
                    else:
                        transformed = value
                    
                    # 设置转换后的值
                    parts = field.split('.')
                    current = result
                    for i, part in enumerate(parts):
                        if i == len(parts) - 1:
                            current[part] = transformed
                        else:
                            if part not in current:
                                current[part] = {}
                            current = current[part]
        
        # 添加固定字段
        if "add_fields" in preprocess_config:
            for field, value in preprocess_config["add_fields"].items():
                # 支持嵌套字段路径
                parts = field.split('.')
                current = result
                for i, part in enumerate(parts):
                    if i == len(parts) - 1:
                        current[part] = value
                    else:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
        
        return result
    
    def _apply_template(self, message: dict, template_name: str) -> dict:
        """应用消息模板
        
        Args:
            message: 原始消息
            template_name: 模板名称
            
        Returns:
            应用模板后的消息
        """
        if not template_name or template_name not in self.config.get("templates", {}):
            return message
        
        template = self.config["templates"][template_name]
        
        # 创建模板消息
        result = {}
        
        # 替换变量
        def replace_variables(template_value, data):
            if isinstance(template_value, dict):
                return {k: replace_variables(v, data) for k, v in template_value.items()}
            elif isinstance(template_value, list):
                return [replace_variables(item, data) for item in template_value]
            elif isinstance(template_value, str) and "{" in template_value:
                try:
                    return template_value.format(**data)
                except KeyError:
                    return template_value
            else:
                return template_value
        
        # 准备数据
        format_data = {}
        self._flatten_dict(message, format_data)
        
        # 应用模板
        for key, value in template.items():
            result[key] = replace_variables(value, format_data)
        
        return result
    
    def _get_nested_value(self, data: dict, path: str, default=None):
        """获取嵌套字典中的值
        
        Args:
            data: 字典数据
            path: 点分隔的路径
            default: 默认值
            
        Returns:
            路径对应的值
        """
        keys = path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current
    
    def _flatten_dict(self, data: dict, result: dict, prefix: str = ""):
        """将嵌套字典扁平化
        
        Args:
            data: 源字典
            result: 结果字典
            prefix: 前缀
        """
        if not data or not isinstance(data, dict):
            return
        
        for key, value in data.items():
            new_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                # 递归处理嵌套字典
                self._flatten_dict(value, result, new_key)
                
                # 同时保留完整对象
                result[new_key] = value
            else:
                result[new_key] = value
    
    async def process_message(self, message: dict, target_ids: List[str] = None) -> List[dict]:
        """处理并转发消息
        
        Args:
            message: 接收到的消息
            target_ids: 目标ID列表，如果为空则发送到所有符合条件的目标
            
        Returns:
            转发结果列表
        """
        # 添加到历史记录
        self._add_to_history(message)
        
        # 记录消息
        logger.info(f"接收到消息: {json.dumps(message, ensure_ascii=False)}")
        
        # 转发结果
        results = []
        
        # 如果指定了目标ID，则只转发到这些目标
        if target_ids and len(target_ids) > 0:
            logger.info(f"将消息转发到指定目标: {target_ids}")
            for target in self.config.get("targets", []):
                if target.get("id") in target_ids and target.get("enabled", True):
                    result = await self.forward_to_target(message, target)
                    results.append({
                        "target_id": target.get("id"),
                        "target_name": target.get("name"),
                        "success": result
                    })
        else:
        # 转发到所有启用的目标
            logger.info("将消息转发到所有符合条件的目标")
        for target in self.config.get("targets", []):
            if target.get("enabled", True) and self._should_forward(message, target):
                result = await self.forward_to_target(message, target)
                results.append({
                    "target_id": target.get("id"),
                    "target_name": target.get("name"),
                    "success": result
                })
        
        return results
    
    def _should_forward(self, message: dict, target: dict) -> bool:
        """判断消息是否应该转发到目标
        
        Args:
            message: 消息内容
            target: 目标配置
            
        Returns:
            是否应转发
        """
        # 检查目标是否启用
        if not target.get("enabled", True):
            return False
        
        # 检查消息类型过滤器
        event_type = message.get("event_type")
        if "event_types" in target and event_type not in target["event_types"]:
            return False
        
        # 检查交易对过滤器
        if "symbols" in target and event_type in ["trade", "position_update"]:
            symbol = message.get("data", {}).get("symbol")
            if symbol and symbol not in target["symbols"]:
                return False
        
        return True
    
    async def forward_to_target(self, message: dict, target: dict) -> bool:
        """转发消息到目标
        
        Args:
            message: 消息内容
            target: 目标配置
            
        Returns:
            是否成功
        """
        try:
            # 获取目标URL
            url = target.get("url")
            if not url:
                logger.warning(f"目标 {target.get('name')} 没有URL配置")
                return False
            
            # 转换消息格式
            payload = self._format_message(message, target)
            
            # 获取请求头
            headers = {
                "Content-Type": "application/json",
                **(target.get("headers") or {})
            }
            
            # 发送请求
            logger.debug(f"发送消息到 {target.get('name')}: {json.dumps(payload, ensure_ascii=False)}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=target.get("timeout", 10)
                ) as response:
                    if 200 <= response.status < 300:
                        logger.info(f"消息已成功发送到 {target.get('name')}")
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(f"发送到 {target.get('name')} 失败: [{response.status}] {response_text}")
                        return False
        except Exception as e:
            logger.error(f"转发消息到 {target.get('name')} 时出错: {e}")
            return False
    
    def _format_message(self, message: dict, target: dict) -> dict:
        """根据目标配置格式化消息
        
        Args:
            message: 原始消息
            target: 目标配置
            
        Returns:
            格式化后的消息
        """
        # 检查是否有自定义格式
        if "format" in target:
            format_type = target.get("format_type", "default")
            
            if format_type == "template":
                # 使用模板格式
                template = target["format"]
                
                # 替换变量
                def replace_vars(template, data):
                    if isinstance(template, dict):
                        return {k: replace_vars(v, data) for k, v in template.items()}
                    elif isinstance(template, list):
                        return [replace_vars(item, data) for item in template]
                    elif isinstance(template, str) and "$" in template:
                        # 替换变量
                        for key, value in data.items():
                            template = template.replace(f"${key}", str(value))
                        return template
                    else:
                        return template
                
                # 准备数据
                data = {}
                # 添加顶级字段
                for key, value in message.items():
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        data[key] = value
                
                # 添加嵌套数据字段
                if "data" in message and isinstance(message["data"], dict):
                    for key, value in message["data"].items():
                        if isinstance(value, (str, int, float, bool)) or value is None:
                            data[key] = value
                
                return replace_vars(template, data)
            
            elif format_type == "text":
                # 使用文本格式
                event_type = message.get("event_type", "unknown")
                
                # 获取格式化模板
                format_template = target["format"].get(event_type)
                if not format_template:
                    format_template = target["format"].get("default", "{description}")
                
                # 准备格式化数据
                format_data = {}
                
                # 添加顶级字段
                for key, value in message.items():
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        format_data[key] = value
                
                # 添加嵌套数据字段
                if "data" in message and isinstance(message["data"], dict):
                    for key, value in message["data"].items():
                        if isinstance(value, (str, int, float, bool)) or value is None:
                            format_data[key] = value
                
                # 格式化文本
                try:
                    text = format_template.format(**format_data)
                    return {"text": text}
                except KeyError as e:
                    logger.warning(f"格式化文本时缺少字段 {e}")
                    return {"text": message.get("description", str(message))}
        
        # 微信/企业微信格式
        if target.get("type") == "wechat" or "wechat" in target.get("url", "").lower():
            return {
                "msgtype": "text",
                "text": {
                    "content": message.get("description", str(message))
                }
            }
            
        # 普通微信个人号格式
        if target.get("type") == "wechat_personal":
            wxid = target.get("wxid", "")
            if not wxid:
                logger.warning(f"目标 {target.get('name')} 缺少wxid参数")
                return {}
            
            return {
                "type": "sendText",
                "data": {
                    "wxid": wxid,
                    "msg": message.get("description", str(message))
                }
            }
        
        # 飞书格式
        if target.get("type") == "feishu" or "feishu" in target.get("url", "").lower():
            return {
                "msg_type": "text",
                "content": {
                    "text": message.get("description", str(message))
                }
            }
        
        # 钉钉格式
        if target.get("type") == "dingtalk" or "dingtalk" in target.get("url", "").lower():
            return {
                "msgtype": "text",
                "text": {
                    "content": message.get("description", str(message))
                }
            }
        
        # 默认情况下，直接返回原始消息
        return message
    
    def _add_to_history(self, message: dict):
        """添加消息到历史记录
        
        Args:
            message: 消息内容
        """
        self.message_history.insert(0, {
            "timestamp": datetime.now().isoformat(),
            "message": message
        })
        
        # 限制历史记录大小
        if len(self.message_history) > self.max_history_size:
            self.message_history = self.message_history[:self.max_history_size]

def create_app(config_path: str = "config/webhook_config.json"):
    """创建FastAPI应用
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        FastAPI应用实例
    """
    forwarder = WebhookForwarder(config_path)
    return forwarder.app

async def run_server(host: str, port: int, config_path: str):
    """运行服务器
    
    Args:
        host: 监听地址
        port: 监听端口
        config_path: 配置文件路径
    """
    app = create_app(config_path)
    
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info"
    )
    
    server = uvicorn.Server(config)
    await server.serve()

def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Bcoin Webhook转发服务器")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8080, help="监听端口")
    parser.add_argument("--config", default="config/webhook_config.json", help="配置文件路径")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                       help="日志级别")
    
    args = parser.parse_args()
    
    # 配置日志
    logger.remove()
    logger.add(sys.stderr, level=args.log_level)
    logger.add("logs/webhook_server.log", level="INFO", rotation="10 MB", compression="zip")
    
    # 输出配置信息
    logger.info("启动Webhook转发服务器:")
    logger.info(f"  监听地址: {args.host}")
    logger.info(f"  监听端口: {args.port}")
    logger.info(f"  配置文件: {args.config}")
    logger.info(f"  日志级别: {args.log_level}")
    
    # 运行服务器
    try:
        asyncio.run(run_server(args.host, args.port, args.config))
    except KeyboardInterrupt:
        logger.info("服务器已停止")
    except Exception as e:
        logger.error(f"服务器运行出错: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()