import unittest
from consent import evaluate_consent_eligibility


class ConsentTests(unittest.TestCase):
    def test_contact_always_eligible(self):
        record = {
            "ATIVO": 1,
            "CONSENTIMENTO_STATUS": "PENDENTE",
            "BLOQUEADO": 0,
        }
        res = evaluate_consent_eligibility(record)
        self.assertTrue(res.is_eligible)
        self.assertFalse(res.is_blocked)

    def test_contact_eligible_even_without_opt_in(self):
        record = {
            "ATIVO": 1,
            "CONSENTIMENTO_STATUS": "OPT_OUT",
            "BLOQUEADO": 1,
        }
        res = evaluate_consent_eligibility(record)
        self.assertTrue(res.is_eligible)


if __name__ == "__main__":
    unittest.main()
