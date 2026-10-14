import unittest
from phone_utils import normalize_brazilian_phone, mask_phone, InvalidPhoneNumberError


class PhoneUtilsTests(unittest.TestCase):
    def test_normalizes_standard_mobile_with_ddd(self):
        self.assertEqual(normalize_brazilian_phone("(11) 98765-4321"), "5511987654321")
        self.assertEqual(normalize_brazilian_phone("+55 11 98765-4321"), "5511987654321")
        self.assertEqual(normalize_brazilian_phone("11987654321"), "5511987654321")
        self.assertEqual(normalize_brazilian_phone("5511987654321"), "5511987654321")

    def test_normalizes_landline(self):
        self.assertEqual(normalize_brazilian_phone("(21) 3232-4545"), "552132324545")
        self.assertEqual(normalize_brazilian_phone("552132324545"), "552132324545")

    def test_rejects_invalid_ddd(self):
        with self.assertRaises(InvalidPhoneNumberError):
            normalize_brazilian_phone("(20) 98765-4321")
        with self.assertRaises(InvalidPhoneNumberError):
            normalize_brazilian_phone("(00) 98765-4321")

    def test_rejects_invalid_length(self):
        with self.assertRaises(InvalidPhoneNumberError):
            normalize_brazilian_phone("12345")
        with self.assertRaises(InvalidPhoneNumberError):
            normalize_brazilian_phone("55119876543219999")

    def test_rejects_mobile_not_starting_with_9(self):
        with self.assertRaises(InvalidPhoneNumberError):
            normalize_brazilian_phone("11787654321")

    def test_mask_phone_protects_pii(self):
        masked = mask_phone("5511987654321")
        self.assertNotIn("98765", masked)
        self.assertEqual(masked, "+55 (11) *****-4321")


if __name__ == "__main__":
    unittest.main()
