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


if __name__ == "__main__":
    unittest.main()
