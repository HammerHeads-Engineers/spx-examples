import asyncio
import unittest
from unittest.mock import Mock

from mcp.server.fastmcp import FastMCP

from spx_mcp.toolsets.server_write_tools import register_server_write_tools


class TextAttributeToolTest(unittest.TestCase):
    def test_json_text_is_not_converted_to_a_mapping(self):
        instance = Mock()
        runtime = Mock()
        runtime.create_client.return_value = {"instances": {"demo": instance}}
        server = FastMCP("test")
        register_server_write_tools(server, runtime)
        value = '{"id":0,"tC":26.1}'

        async def call():
            return await server.call_tool("server_set_text_attr", {
                "instance_key": "demo", "attr_path": "attributes/status", "value": value,
            })

        asyncio.run(call())
        runtime.require_write.assert_called_once()
        instance.put_attr.assert_called_once_with("attributes/status/internal_value", value)


if __name__ == "__main__":
    unittest.main()
