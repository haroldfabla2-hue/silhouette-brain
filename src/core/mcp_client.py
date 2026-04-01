"""
MCP Client for Silhouette Brain
Simplified implementation based on Claude Code's MCP client
Model Context Protocol - StreamableHTTP transport

Supports:
- n8n (workflow automation)
- GitHub (code review, PRs)
- Notion (docs and databases)
"""

import json
import httpx
import asyncio
from typing import Any, Optional, List, Dict
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TransportType(Enum):
    STREAMABLE_HTTP = "streamable-http"
    SSE = "sse"
    STDIO = "stdio"
    WEBSOCKET = "websocket"


class MCPErrorCode(Enum):
    CONNECTION_CLOSED = -32000
    SESSION_NOT_FOUND = -32001
    REQUEST_TIMEOUT = -32002
    URL_ELICITATION = -32042


@dataclass
class MCPTool:
    """Represents an MCP tool exposed by a server"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    annotations: Optional[Dict[str, Any]] = None


@dataclass
class MCPResource:
    """Represents an MCP resource exposed by a server"""
    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None


@dataclass
class MCPPrompt:
    """Represents an MCP prompt template exposed by a server"""
    name: str
    description: Optional[str] = None
    arguments: Optional[List[Dict[str, Any]]] = None


@dataclass
class MCPConnectionConfig:
    """Configuration for an MCP server connection"""
    server_url: str
    transport: TransportType = TransportType.STREAMABLE_HTTP
    auth_token: Optional[str] = None
    auth_type: str = "bearer"  # bearer, api-key, oauth
    timeout: float = 30.0
    headers: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.transport, str):
            self.transport = TransportType(self.transport)


class MCPClientError(Exception):
    """Base exception for MCP client errors"""
    pass


class MCPAuthError(MCPClientError):
    """Raised when authentication fails"""
    pass


class MCPSessionExpiredError(MCPClientError):
    """Raised when MCP session has expired"""
    pass


class MCPTimeoutError(MCPClientError):
    """Raised when request times out"""
    pass


class MCPClient:
    """
    MCP Client for Silhouette Brain
    
    Simplified implementation of Claude Code's MCP client, supporting:
    - StreamableHTTP transport (most common for remote servers)
    - Tool listing and calling
    - Session management
    - Error handling with specific error codes
    """
    
    def __init__(self, config: MCPConnectionConfig):
        self.config = config
        self.session_id: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._connected = False
        self._request_id = 0
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    def _get_next_id(self) -> int:
        """Generate unique request ID"""
        self._request_id += 1
        return self._request_id
    
    def _get_headers(self) -> Dict[str, str]:
        """Build request headers"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        
        # Add auth header
        if self.config.auth_token:
            if self.config.auth_type == "bearer":
                headers["Authorization"] = f"Bearer {self.config.auth_token}"
            elif self.config.auth_type == "api-key":
                headers["X-API-Key"] = self.config.auth_token
        
        # Merge custom headers
        headers.update(self.config.headers)
        
        return headers
    
    async def connect(self) -> bool:
        """
        Connect to MCP server using StreamableHTTP transport.
        
        Sends initial handshake to establish session.
        
        Returns:
            bool: True if connection successful
        """
        if self._connected:
            return True
        
        try:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
            
            # Send initialize request to establish session
            init_params = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {}
                },
                "clientInfo": {
                    "name": "silhouette-brain",
                    "version": "1.0.0"
                }
            }
            
            response = await self._send_request("initialize", init_params)
            
            # Server returns session_id in response headers or body
            # StreamableHTTP uses the session_id for subsequent requests
            if isinstance(response, dict):
                self.session_id = response.get("sessionId") or response.get("session_id")
            
            # Check for session ID in response headers (some servers use this)
            # This is handled by httpx internals for cookies/set-cookies
            
            self._connected = True
            logger.info(f"MCP client connected to {self.config.server_url}, session: {self.session_id}")
            
            # Send initialized notification (fire-and-forget)
            await self._send_notification("initialized", {})
            
            return True
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise MCPAuthError(f"Authentication failed: {e}")
            raise MCPClientError(f"Connection failed: {e}")
        except Exception as e:
            raise MCPClientError(f"Failed to connect: {e}")
    
    async def disconnect(self) -> None:
        """Disconnect from MCP server"""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False
        self.session_id = None
        logger.info(f"MCP client disconnected from {self.config.server_url}")
    
    async def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send JSON-RPC request and return response.
        
        Args:
            method: JSON-RPC method name
            params: Method parameters
            
        Returns:
            Response data as dict
        """
        if not self._client:
            raise MCPClientError("Client not connected. Call connect() first.")
        
        request_id = self._get_next_id()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": request_id
        }
        
        # Include session_id if we have one
        headers = self._get_headers()
        if self.session_id:
            headers["MCP-Session-ID"] = self.session_id
        
        try:
            response = await self._client.post(
                f"{self.config.server_url}/message",
                json=payload,
                headers=headers
            )
            
            # Handle HTTP-level errors
            if response.status_code == 404:
                # Session not found - need to reconnect
                error_data = response.json() if response.text else {}
                error_msg = str(error_data)
                if "-32001" in error_msg or "Session not found" in error_msg:
                    raise MCPSessionExpiredError(f"Session expired: {error_msg}")
                raise MCPClientError(f"Not found: {response.url}")
            
            if response.status_code == 401:
                raise MCPAuthError("Authentication failed - check your token")
            
            response.raise_for_status()
            
            # Handle SSE responses (text/event-stream)
            content_type = response.headers.get("content-type", "")
            
            if "text/event-stream" in content_type:
                return self._parse_sse_response(response.text)
            
            # Regular JSON response
            return response.json()
            
        except httpx.TimeoutException:
            raise MCPTimeoutError(f"Request timed out after {self.config.timeout}s")
        except MCPSessionExpiredError:
            raise
        except MCPAuthError:
            raise
        except Exception as e:
            if "Session not found" in str(e) or "-32001" in str(e):
                raise MCPSessionExpiredError(str(e))
            raise MCPClientError(f"Request failed: {e}")
    
    async def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """
        Send JSON-RPC notification (no response expected).
        
        Args:
            method: JSON-RPC method name
            params: Method parameters
        """
        if not self._client:
            return
        
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        headers = self._get_headers()
        if self.session_id:
            headers["MCP-Session-ID"] = self.session_id
        
        try:
            # Fire and forget - don't wait for response
            await self._client.post(
                f"{self.config.server_url}/message",
                json=payload,
                headers=headers
            )
        except Exception as e:
            logger.debug(f"Notification {method} failed (non-critical): {e}")
    
    def _parse_sse_response(self, text: str) -> Dict[str, Any]:
        """
        Parse Server-Sent Events response.
        
        MCP servers can return SSE format where each line is:
        event: message
        data: {"jsonrpc": "2.0", ...}
        
        Args:
            text: Raw SSE text
            
        Returns:
            Parsed JSON-RPC message
        """
        lines = text.strip().split("\n")
        for line in lines:
            if line.startswith("data:"):
                data = line[5:].strip()
                if data and data.startswith("{"):
                    try:
                        return json.loads(data)
                    except json.JSONDecodeError:
                        continue
        return {}
    
    async def list_tools(self) -> List[MCPTool]:
        """
        List available tools from MCP server.
        
        Returns:
            List of MCPTool objects
        """
        if not self._connected:
            await self.connect()
        
        response = await self._send_request("tools/list", {})
        
        tools = []
        if isinstance(response, dict) and "result" in response:
            result = response["result"]
            if isinstance(result, dict) and "tools" in result:
                for tool_data in result["tools"]:
                    tools.append(MCPTool(
                        name=tool_data.get("name", ""),
                        description=tool_data.get("description", ""),
                        input_schema=tool_data.get("inputSchema", tool_data.get("input_schema", {})),
                        annotations=tool_data.get("annotations")
                    ))
            elif isinstance(result, list):
                # Direct array response
                for tool_data in result:
                    tools.append(MCPTool(
                        name=tool_data.get("name", ""),
                        description=tool_data.get("description", ""),
                        input_schema=tool_data.get("inputSchema", tool_data.get("input_schema", {})),
                        annotations=tool_data.get("annotations")
                    ))
        
        logger.debug(f"Listed {len(tools)} tools from MCP server")
        return tools
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool by name with arguments.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool-specific arguments
            
        Returns:
            Tool execution result as dict
        """
        if not self._connected:
            await self.connect()
        
        params = {
            "name": tool_name,
            "arguments": arguments
        }
        
        response = await self._send_request("tools/call", params)
        
        # Handle error responses
        if isinstance(response, dict):
            if "error" in response:
                error = response["error"]
                raise MCPClientError(f"Tool call failed: {error.get('message', error)}")
            
            if "result" in response:
                result = response["result"]
                # Check if tool returned an error
                if isinstance(result, dict) and result.get("isError"):
                    raise MCPClientError(f"Tool returned error: {result.get('content', result)}")
                return result
        
        return response
    
    async def list_resources(self) -> List[MCPResource]:
        """
        List available resources from MCP server.
        
        Returns:
            List of MCPResource objects
        """
        if not self._connected:
            await self.connect()
        
        response = await self._send_request("resources/list", {})
        
        resources = []
        if isinstance(response, dict) and "result" in response:
            result = response["result"]
            if isinstance(result, dict) and "resources" in result:
                for res_data in result["resources"]:
                    resources.append(MCPResource(
                        uri=res_data.get("uri", ""),
                        name=res_data.get("name", ""),
                        description=res_data.get("description"),
                        mime_type=res_data.get("mimeType", res_data.get("mime_type"))
                    ))
        
        logger.debug(f"Listed {len(resources)} resources from MCP server")
        return resources
    
    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """
        Read a resource by URI.
        
        Args:
            uri: Resource URI
            
        Returns:
            Resource contents
        """
        if not self._connected:
            await self.connect()
        
        params = {"uri": uri}
        response = await self._send_request("resources/read", params)
        
        if isinstance(response, dict) and "result" in response:
            return response["result"]
        return response
    
    async def list_prompts(self) -> List[MCPPrompt]:
        """
        List available prompts from MCP server.
        
        Returns:
            List of MCPPrompt objects
        """
        if not self._connected:
            await self.connect()
        
        response = await self._send_request("prompts/list", {})
        
        prompts = []
        if isinstance(response, dict) and "result" in response:
            result = response["result"]
            if isinstance(result, dict) and "prompts" in result:
                for prompt_data in result["prompts"]:
                    prompts.append(MCPPrompt(
                        name=prompt_data.get("name", ""),
                        description=prompt_data.get("description"),
                        arguments=prompt_data.get("arguments")
                    ))
        
        return prompts
    
    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get a prompt template by name.
        
        Args:
            name: Prompt name
            arguments: Optional prompt arguments
            
        Returns:
            Prompt with resolved content
        """
        if not self._connected:
            await self.connect()
        
        params = {"name": name}
        if arguments:
            params["arguments"] = arguments
        
        response = await self._send_request("prompts/get", params)
        
        if isinstance(response, dict) and "result" in response:
            return response["result"]
        return response


class MCPServerRegistry:
    """
    Registry for managing multiple MCP server connections.
    """
    
    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}
    
    def add_server(self, name: str, config: MCPConnectionConfig) -> None:
        """Add and configure an MCP server"""
        self._clients[name] = MCPClient(config)
    
    async def connect(self, name: str) -> bool:
        """Connect to a registered server"""
        if name not in self._clients:
            raise MCPClientError(f"Server '{name}' not found in registry")
        return await self._clients[name].connect()
    
    async def disconnect(self, name: str) -> None:
        """Disconnect from a registered server"""
        if name in self._clients:
            await self._clients[name].disconnect()
    
    async def disconnect_all(self) -> None:
        """Disconnect from all servers"""
        for client in self._clients.values():
            await client.disconnect()
    
    def get_client(self, name: str) -> MCPClient:
        """Get a client by server name"""
        if name not in self._clients:
            raise MCPClientError(f"Server '{name}' not found in registry")
        return self._clients[name]
    
    async def list_server_tools(self, name: str) -> List[MCPTool]:
        """List tools from a specific server"""
        client = self.get_client(name)
        return await client.list_tools()
    
    async def call_server_tool(self, name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on a specific server"""
        client = self.get_client(name)
        return await client.call_tool(tool_name, arguments)
    
    def list_servers(self) -> List[str]:
        """List all registered server names"""
        return list(self._clients.keys())


# Pre-configured server factories

def create_n8n_client(
    server_url: str,
    api_key: Optional[str] = None,
    timeout: float = 30.0
) -> MCPClient:
    """
    Create MCP client for n8n workflow automation server.
    
    Args:
        server_url: n8n instance URL (e.g., http://localhost:5678/mcp)
        api_key: n8n API key (optional, for auth)
        timeout: Request timeout in seconds
    """
    config = MCPConnectionConfig(
        server_url=server_url,
        transport=TransportType.STREAMABLE_HTTP,
        auth_token=api_key,
        auth_type="bearer" if api_key else "none",
        timeout=timeout
    )
    return MCPClient(config)


def create_github_client(
    personal_access_token: str,
    timeout: float = 30.0
) -> MCPClient:
    """
    Create MCP client for GitHub MCP server.
    
    Args:
        personal_access_token: GitHub personal access token
        timeout: Request timeout in seconds
    """
    config = MCPConnectionConfig(
        server_url="https://api.github.com/mcp",
        transport=TransportType.STREAMABLE_HTTP,
        auth_token=personal_access_token,
        auth_type="bearer",
        timeout=timeout
    )
    return MCPClient(config)


def create_notion_client(
    api_token: str,
    timeout: float = 30.0
) -> MCPClient:
    """
    Create MCP client for Notion MCP server.
    
    Note: Notion typically uses stdio transport with the official SDK.
    This creates an HTTP client for servers that expose HTTP transport.
    
    Args:
        api_token: Notion API token
        timeout: Request timeout in seconds
    """
    config = MCPConnectionConfig(
        server_url="https://api.notion.com/v1/mcp",
        transport=TransportType.STREAMABLE_HTTP,
        auth_token=api_token,
        auth_type="bearer",
        timeout=timeout
    )
    return MCPClient(config)


# Example usage and testing

async def main():
    """Example usage of MCP client"""
    import os
    
    # Example: Connect to GitHub
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        print("Connecting to GitHub MCP...")
        client = create_github_client(github_token)
        
        try:
            await client.connect()
            tools = await client.list_tools()
            print(f"GitHub MCP tools: {[t.name for t in tools]}")
            
            # Example: Call a tool (search code)
            # result = await client.call_tool("search_code", {"q": "test", "per_page": 5})
            # print(f"Search result: {result}")
            
            await client.disconnect()
        except MCPAuthError as e:
            print(f"Auth error: {e}")
        except MCPSessionExpiredError as e:
            print(f"Session expired: {e}")
        except MCPClientError as e:
            print(f"MCP error: {e}")
    
    # Example: Connect to n8n
    n8n_url = os.environ.get("N8N_URL", "http://localhost:5678/mcp")
    n8n_key = os.environ.get("N8N_API_KEY")
    if n8n_key:
        print(f"Connecting to n8n at {n8n_url}...")
        client = create_n8n_client(n8n_url, n8n_key)
        
        try:
            await client.connect()
            tools = await client.list_tools()
            print(f"n8n MCP tools: {[t.name for t in tools]}")
            await client.disconnect()
        except MCPClientError as e:
            print(f"n8n MCP error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
