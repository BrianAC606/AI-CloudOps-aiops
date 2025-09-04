#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI-CloudOps-aiops
Author: Bamboo
Email: bamboocloudops@gmail.com
License: Apache 2.0
Description: 主应用程序入口
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

try:
    from ..config.settings import config
    from .server.mcp_server import MCPServer
    from .server.tools import tools as mcp_tools
except ImportError:
    try:
        from app.config.settings import config
        from app.mcp.server.mcp_server import MCPServer
        from app.mcp.server.tools import tools as mcp_tools
    except ImportError as e:
        logging.error(f"导入模块失败: {e}")
        sys.exit(1)

from app.config.logging import setup_logging

setup_logging()
logger = logging.getLogger("aiops.mcp.main")

mcp_server: Optional[MCPServer] = None
active_sse_connections: set = set()


class ToolRequest(BaseModel):
    """工具调用请求模型"""

    tool: str = Field(..., description="工具名称")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    request_id: Optional[str] = Field(None, description="请求ID")


class ToolResponse(BaseModel):
    """工具调用响应模型"""

    request_id: Optional[str] = Field(None, description="请求ID")
    tool: str = Field(..., description="工具名称")
    result: Any = Field(None, description="执行结果")
    error: Optional[str] = Field(None, description="错误信息")
    status: str = Field(default="success", description="执行状态")
    timestamp: float = Field(default_factory=time.time, description="时间戳")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global mcp_server

    # 启动时初始化
    logger.info("正在启动MCP服务端...")

    try:
        mcp_server = MCPServer()

        # 注册所有工具
        registered_count = 0
        if mcp_tools:
            for tool in mcp_tools:
                await mcp_server.register_tool(tool)
                registered_count += 1
                logger.info(f"已注册工具: {tool.name}")
        else:
            logger.warning("未找到可注册的工具")

        logger.info(f"MCP服务端启动完成，共注册 {registered_count} 个工具")

    except Exception as e:
        logger.error(f"MCP服务端启动失败: {e}")
        raise

    yield

    # 关闭时清理
    try:
        # 清理活跃的SSE连接
        active_sse_connections.clear()

        if mcp_server:
            await mcp_server.shutdown()
            logger.info("MCP服务端已关闭")
    except Exception as e:
        logger.error(f"关闭MCP服务端时出错: {e}")


# 创建FastAPI应用
app = FastAPI(
    title="AI-CloudOps MCP服务端",
    description="提供MCP工具调用能力的SSE服务端",
    version="1.0.0",
    lifespan=lifespan,
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 统一注册错误处理器（与主应用一致）
try:
    from app.api.middleware.error_handler import setup_error_handlers

    setup_error_handlers(app)
    logger.info("MCP 应用已注册统一错误处理器")
except Exception as e:
    logger.warning(f"MCP 错误处理器注册失败: {e}")


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """健康检查接口"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "tools_count": len(mcp_server.tools) if mcp_server else 0,
        "active_connections": len(active_sse_connections),
        "server_info": {
            "version": "1.0.0",
            "python_version": sys.version,
            "pid": os.getpid(),
            "startup_command": "python -m app.mcp.main",
        },
    }


@app.get("/sse")
async def sse_endpoint(request: Request) -> StreamingResponse:
    """SSE端点，提供实时数据流"""
    if not mcp_server:
        raise HTTPException(status_code=503, detail="MCP服务器未初始化")

    async def event_generator() -> AsyncGenerator[str, None]:
        """事件生成器"""
        connection_id = id(request)
        active_sse_connections.add(connection_id)

        try:
            # 发送连接事件
            yield f"data: {json.dumps({'type': 'connected', 'message': 'MCP连接已建立', 'connection_id': connection_id})}\n\n"

            # 发送可用工具列表
            tools_info = {
                "type": "tools_list",
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    }
                    for tool in mcp_server.tools.values()
                ],
                "timestamp": time.time(),
            }
            yield f"data: {json.dumps(tools_info)}\n\n"

            # 保持连接活跃
            while True:
                # 检查客户端是否断开连接
                if await request.is_disconnected():
                    logger.info(f"客户端连接 {connection_id} 已断开")
                    break

                from app.config.settings import config

                # 根据配置发送心跳
                await asyncio.sleep(config.mcp.health_check_interval)
                heartbeat = {
                    "type": "heartbeat",
                    "timestamp": time.time(),
                    "connection_id": connection_id,
                }
                yield f"data: {json.dumps(heartbeat)}\n\n"

        except asyncio.CancelledError:
            logger.info(f"SSE连接 {connection_id} 已取消")
        except Exception as e:
            logger.error(f"SSE连接 {connection_id} 错误: {str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e), 'connection_id': connection_id})}\n\n"
        finally:
            # 清理连接
            active_sse_connections.discard(connection_id)
            yield f"data: {json.dumps({'type': 'disconnected', 'message': 'MCP连接已断开', 'connection_id': connection_id})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用nginx缓冲
        },
    )


@app.post("/tools/execute")
async def execute_tool(request: ToolRequest) -> ToolResponse:
    """执行工具调用"""
    if not mcp_server:
        raise HTTPException(status_code=503, detail="MCP服务器未初始化")

    start_time = time.time()

    try:
        logger.info(f"执行工具调用: {request.tool}, 参数: {request.parameters}")

        # 验证工具是否存在
        if request.tool not in mcp_server.tools:
            return ToolResponse(
                request_id=request.request_id,
                tool=request.tool,
                result=None,
                error=f"工具 '{request.tool}' 不存在",
                status="error",
            )

        # 执行工具
        result = await mcp_server.execute_tool(
            tool_name=request.tool, parameters=request.parameters
        )

        execution_time = time.time() - start_time
        logger.info(f"工具 {request.tool} 执行完成，耗时: {execution_time:.2f}秒")

        return ToolResponse(
            request_id=request.request_id,
            tool=request.tool,
            result=result,
            status="success",
        )

    except Exception as err:
        execution_time = time.time() - start_time
        logger.error(f"工具调用失败: {str(err)}, 耗时: {execution_time:.2f}秒")

        return ToolResponse(
            request_id=request.request_id,
            tool=request.tool,
            result=None,
            error=str(err),
            status="error",
        )


@app.get("/tools")
async def list_tools() -> Dict[str, Any]:
    """获取可用工具列表"""
    if not mcp_server:
        raise HTTPException(status_code=503, detail="MCP服务器未初始化")

    tools = [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "metadata": getattr(tool, "metadata", {}),
        }
        for tool in mcp_server.tools.values()
    ]

    return {"tools": tools, "total_count": len(tools), "timestamp": time.time()}


@app.get("/tools/{tool_name}")
async def get_tool_info(tool_name: str) -> Dict[str, Any]:
    """获取特定工具信息"""
    if not mcp_server:
        raise HTTPException(status_code=503, detail="MCP服务器未初始化")

    if tool_name not in mcp_server.tools:
        raise HTTPException(status_code=404, detail=f"工具 '{tool_name}' 不存在")

    tool = mcp_server.tools[tool_name]
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
        "metadata": getattr(tool, "metadata", {}),
        "timestamp": time.time(),
    }


def parse_server_url(url: str) -> tuple[str, int]:
    """解析服务器URL，返回主机和端口"""
    from app.config.settings import config

    try:
        if "://" not in url:
            url = f"http://{url}"

        parsed = urlparse(url)
        host = parsed.hostname or config.host
        default_mcp_port = getattr(config, "mcp_default_port", 9000)
        port = parsed.port or config.mcp.server_url.split(":")[-1] or default_mcp_port

        return host, port
    except Exception as e:
        logger.warning(f"解析URL失败: {e}，使用默认配置")
        default_port = (
            config.mcp.server_url.split(":")[-1]
            if config.mcp.server_url
            else getattr(config, "mcp_default_port", 9000)
        )
        return config.host, (
            int(default_port) if str(default_port).isdigit() else default_port
        )


def signal_handler(signum, frame):
    """信号处理器"""
    logger.info(f"接收到信号 {signum}，正在优雅关闭...")
    # 清理全局资源
    active_sse_connections.clear()
    sys.exit(0)


def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(description="AI-CloudOps MCP服务端")
    parser.add_argument("--host", default=None, help="服务器主机地址")
    parser.add_argument("--port", type=int, default=None, help="服务器端口")
    parser.add_argument("--log-level", default=None, help="日志级别")
    parser.add_argument("--reload", action="store_true", help="开发模式，自动重载")

    args = parser.parse_args()

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 启动服务
        logger.info("正在启动MCP服务端...")

        server_host = args.host or config.host
        if args.port:
            server_port = args.port
        else:
            _, server_port = parse_server_url(config.mcp.server_url)
        log_level = (args.log_level or config.log_level).lower()
        reload_enabled = args.reload or config.debug

        logger.info(f"服务器将在 {server_host}:{server_port} 启动")
        logger.info(f"启动命令: python -m app.mcp.main")

        uvicorn.run(
            "app.mcp.main:app",
            host=server_host,
            port=server_port,
            log_level=log_level,
            access_log=True,
            reload=reload_enabled,
        )

    except Exception as e:
        logger.error(f"启动服务失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
