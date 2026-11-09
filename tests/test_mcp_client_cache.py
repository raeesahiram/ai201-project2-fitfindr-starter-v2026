import copy
import unittest
from unittest.mock import AsyncMock, patch

import mcp_client


class MCPClientCacheTests(unittest.TestCase):
    def setUp(self):
        mcp_client.clear_search_cache()

    def tearDown(self):
        mcp_client.clear_search_cache()

    def test_successful_search_is_cached_and_results_are_copied(self):
        expected = [{"id": "lst_002", "price": 18.0}]
        with patch.object(
            mcp_client,
            "_call",
            new=AsyncMock(return_value=copy.deepcopy(expected)),
        ) as call:
            first = mcp_client.call_tool(
                "search_listings",
                {"description": "graphic tee", "size": None, "max_price": 30},
            )
            first[0]["id"] = "mutated"
            second = mcp_client.call_tool(
                "search_listings",
                {"max_price": 30, "size": None, "description": "graphic tee"},
            )

        self.assertEqual(call.await_count, 1)
        self.assertEqual(second, expected)

    def test_non_search_tools_are_not_cached(self):
        with patch.object(
            mcp_client,
            "_call",
            new=AsyncMock(return_value={"ok": True}),
        ) as call:
            mcp_client.call_tool("other_tool", {})
            mcp_client.call_tool("other_tool", {})

        self.assertEqual(call.await_count, 2)

    def test_failed_searches_are_not_cached(self):
        with patch.object(
            mcp_client,
            "_call",
            new=AsyncMock(side_effect=mcp_client.MCPError("search failed")),
        ) as call:
            for _ in range(2):
                with self.assertRaisesRegex(mcp_client.MCPError, "search failed"):
                    mcp_client.call_tool(
                        "search_listings",
                        {"description": "graphic tee", "size": None, "max_price": 30},
                    )

        self.assertEqual(call.await_count, 2)


if __name__ == "__main__":
    unittest.main()
