import unittest

from search_engine import SmartSearchEngine, _clean_noise_terms


class SearchEngineBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = SmartSearchEngine()

    def test_clean_noise_terms_multilang(self):
        terms = ["je", "veux", "want", "اريد", "print", "scanner", "ورقة"]
        cleaned = _clean_noise_terms(terms)

        self.assertIn("print", cleaned)
        self.assertIn("scanner", cleaned)
        self.assertIn("ورقة", cleaned)
        self.assertNotIn("je", cleaned)
        self.assertNotIn("veux", cleaned)
        self.assertNotIn("want", cleaned)
        self.assertNotIn("اريد", cleaned)

    def test_intent_type_detection_printing_sentence(self):
        available_types = ["Imprimante", "Scanner", "Projecteur"]
        q = "اريد شي لطباعة ورقة"

        inferred = self.engine._infer_type_from_intent_patterns(q, available_types)
        self.assertEqual(inferred, "Imprimante")

    def test_typo_type_detection(self):
        available_types = ["Scanner", "Imprimante"]
        inferred = self.engine._infer_type_from_terms(["sanne"], available_types, "sanne")
        self.assertEqual(inferred, "Scanner")

    def test_extract_filters_detects_type_marque_floor(self):
        available_types = ["Scanner", "Imprimante"]
        available_marques = ["HP", "Canon"]
        available_fonctions = ["Scan A4", "PDF"]
        tokens = ["je", "veux", "scanner", "hp", "etage", "1"]

        filters, cleaned = self.engine._extract_filters(
            query="je veux scanner hp etage 1",
            tokens=tokens,
            available_types=available_types,
            available_marques=available_marques,
            available_fonctions=available_fonctions,
        )

        self.assertEqual(filters.get("type_objet"), "Scanner")
        self.assertEqual(filters.get("nom_marque"), "HP")
        self.assertEqual(filters.get("num_etage"), 1)
        self.assertIn("scanner", cleaned)
        self.assertIn("hp", cleaned)


if __name__ == "__main__":
    unittest.main()
