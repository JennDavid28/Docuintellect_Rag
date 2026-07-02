import os
import unittest
from backend.auth import hash_password, verify_password
from backend.ml_classifier import classify_document
from backend.document_parser import extract_document_pages

class TestDocuIntellectBackend(unittest.TestCase):

    def test_password_hashing(self):
        """Test that passwords hash securely and verify correctly."""
        password = "SecurePassword123"
        hashed = hash_password(password)
        
        # Verify the format contains a salt and key split
        self.assertIn(":", hashed)
        
        # Verify correctness
        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

    def test_ml_classification(self):
        """Test document category classifier predictions."""
        # Tech snippet
        tech_text = "programming developer database cloud kubernetes container docker microservice REST api"
        tech_cat = classify_document(tech_text)
        self.assertEqual(tech_cat, "Technology")
        
        # Finance snippet
        fin_text = "revenue balance sheet profit asset fiscal quarter audit ledger stock index"
        fin_cat = classify_document(fin_text)
        self.assertEqual(fin_cat, "Finance")
        
        # Legal snippet
        legal_text = "contract liability lawsuit legal counsel trademark copyright patent agreement"
        legal_cat = classify_document(legal_text)
        self.assertEqual(legal_cat, "Legal")

    def test_document_parsers(self):
        """Test that plain text and URL parsing returns expected structures."""
        # Create temp file
        temp_file = "test_doc.txt"
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write("This is a simple test document for docuintellect.")
            
        try:
            pages = extract_document_pages(temp_file, "txt")
            self.assertEqual(len(pages), 1)
            self.assertEqual(pages[0]["page_number"], 1)
            self.assertIn("simple test document", pages[0]["text"])
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

        # Test invalid youtube URL extraction
        yt_pages = extract_document_pages("https://youtube.com/invalid_link", "youtube")
        self.assertEqual(len(yt_pages), 1)
        self.assertIn("Invalid YouTube URL", yt_pages[0]["text"])

if __name__ == "__main__":
    unittest.main()
