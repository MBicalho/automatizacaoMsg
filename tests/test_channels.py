import tempfile
from pathlib import Path
import unittest

from channels import DryRunWhatsAppChannel, get_channel


class ChannelsTests(unittest.TestCase):
    def test_dry_run_text_simulation(self):
        channel = DryRunWhatsAppChannel(simulated_delay_seconds=0.0)
        res = channel.send_text("5511987654321", "Ola teste de simulacao")
        self.assertTrue(res.success)
        self.assertEqual(res.status, "SUCESSO")
        self.assertEqual(res.channel_name, "SIMULACAO")
        self.assertIn("+55 (11) *****-4321", res.detail)
        self.assertNotIn("987654321", res.detail)

    def test_dry_run_file_simulation(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            channel = DryRunWhatsAppChannel(simulated_delay_seconds=0.0)
            res = channel.send_file("5511987654321", Path(f.name), caption="Legenda teste", is_image=False)
            self.assertTrue(res.success)
            self.assertEqual(res.status, "SUCESSO")
            self.assertEqual(res.channel_name, "SIMULACAO")
            self.assertIn("documento", res.detail)

    def test_dry_run_video_simulation(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            channel = DryRunWhatsAppChannel(simulated_delay_seconds=0.0)
            res = channel.send_file("5511987654321", Path(f.name), caption="Video teste", is_image=False)
            self.assertTrue(res.success)
            self.assertEqual(res.status, "SUCESSO")
            self.assertEqual(res.channel_name, "SIMULACAO")
            self.assertIn("video", res.detail)

    def test_factory_defaults_to_dry_run(self):
        with unittest.mock.patch("channels.load_dotenv"), unittest.mock.patch.dict("os.environ", {"WHATSAPP_DRY_RUN": "true"}):
            channel = get_channel()
            self.assertIsInstance(channel, DryRunWhatsAppChannel)


    def test_desktop_channel_prepare_chat_and_execution(self):
        from unittest.mock import MagicMock
        from channels import DesktopWhatsAppChannel
        channel = DesktopWhatsAppChannel()
        mock_functions = MagicMock()
        channel._functions = mock_functions

        res = channel.send_text("5531983282759", "Ola")
        self.assertTrue(res.success)
        self.assertEqual(channel._current_phone, "5531983282759")

        # Segunda chamada com mesmo numero deve reutilizar chat
        res2 = channel.send_text("5531983282759", "Segunda mensagem")
        self.assertTrue(res2.success)

    def test_evolution_channel_send_presence(self):
        from unittest.mock import patch, MagicMock
        from channels import EvolutionApiWhatsAppChannel

        channel = EvolutionApiWhatsAppChannel(base_url="http://localhost:8080", api_key="secret", instances=["conta_1"])

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            success = channel.send_presence("5531983282759", presence="composing", delay_ms=1200, instance="conta_1")
            self.assertTrue(success)
            mock_urlopen.assert_called_once()
            req = mock_urlopen.call_args[0][0]
            self.assertIn("/chat/sendPresence/conta_1", req.full_url)

    def test_evolution_channel_send_text_triggers_presence(self):
        from unittest.mock import patch, MagicMock
        from channels import EvolutionApiWhatsAppChannel

        channel = EvolutionApiWhatsAppChannel(base_url="http://localhost:8080", api_key="secret", instances=["conta_1"], simulate_presence=True)

        with patch.object(channel, "send_presence", return_value=True) as mock_presence, \
             patch("time.sleep") as mock_sleep, \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"status": "ok"}'
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            res = channel.send_text("5531983282759", "Mensagem de teste anti-ban", instance="conta_1")
            self.assertTrue(res.success)
            mock_presence.assert_called_once_with("5531983282759", presence="composing", delay_ms=mock_presence.call_args[1]["delay_ms"], instance="conta_1")
            mock_sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
