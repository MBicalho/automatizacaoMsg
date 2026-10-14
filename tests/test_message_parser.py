import unittest
from message_parser import parse_message_codes, render_message_text, extract_first_name


class MessageParserTests(unittest.TestCase):
    def test_preserves_order_and_does_not_sort_alphabetically(self):
        input_raw = "boas-vindas, apresentacao, interesse"
        codes = parse_message_codes(input_raw)
        self.assertEqual(codes, ["boas-vindas", "apresentacao", "interesse"])
        self.assertNotEqual(codes, sorted(codes))

    def test_handles_newlines_and_semicolons(self):
        input_raw = "etapa1;\netapa2,\netapa3"
        codes = parse_message_codes(input_raw)
        self.assertEqual(codes, ["etapa1", "etapa2", "etapa3"])

    def test_handles_empty_or_whitespace(self):
        self.assertEqual(parse_message_codes(""), [])
        self.assertEqual(parse_message_codes(None), [])
        self.assertEqual(parse_message_codes("   ,  , "), [])

    def test_extract_first_name(self):
        self.assertEqual(extract_first_name("maria fernanda da silva"), "Maria")
        self.assertEqual(extract_first_name("JOAO"), "Joao")
        self.assertEqual(extract_first_name(""), "")

    def test_renders_template_with_name(self):
        tpl = "Ola {{nome}}, tudo bem? Mensagem para {{nome_completo}}."
        res = render_message_text(tpl, {"nome": "carlos eduardo"})
        self.assertEqual(res, "Ola Carlos, tudo bem? Mensagem para carlos eduardo.")

    def test_renders_template_when_name_missing(self):
        tpl = "Ola {{nome}}, tudo bem?"
        res = render_message_text(tpl, {})
        self.assertEqual(res, "Ola , tudo bem?")


if __name__ == "__main__":
    unittest.main()
