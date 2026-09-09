import unittest
from unittest.mock import patch

import get_match_ids


class GetMatchIdsTest(unittest.TestCase):
    def test_configured_puuid_uses_the_shared_riot_account_resolver(self):
        with patch.object(get_match_ids, "GAME_NAME", " Player "), patch.object(
            get_match_ids, "TAG_LINE", " TAG "), patch.object(
            get_match_ids, "get_puuid", return_value="resolved-puuid"
        ) as resolver:
            self.assertEqual(get_match_ids.configured_puuid(), "resolved-puuid")
        resolver.assert_called_once_with("Player", "TAG")

    def test_missing_riot_id_configuration_stops_without_a_fallback(self):
        with patch.object(get_match_ids, "GAME_NAME", ""), patch.object(
            get_match_ids, "get_puuid"
        ) as resolver:
            with self.assertRaisesRegex(RuntimeError, "RIOT_GAME_NAME"):
                get_match_ids.configured_puuid()
        resolver.assert_not_called()

    def test_missing_tag_line_stops_without_a_fallback(self):
        with patch.object(get_match_ids, "TAG_LINE", None), patch.object(
            get_match_ids, "get_puuid"
        ) as resolver:
            with self.assertRaisesRegex(RuntimeError, "RIOT_TAG_LINE"):
                get_match_ids.configured_puuid()
        resolver.assert_not_called()

    def test_main_never_prints_the_resolved_puuid(self):
        with patch.object(get_match_ids, "configured_puuid", return_value="secret-puuid"), patch.object(
            get_match_ids, "get_match_ids", return_value=["JP1_TEST"]
        ), patch("builtins.print") as printer:
            get_match_ids.main()
        self.assertNotIn("secret-puuid", str(printer.call_args_list))
