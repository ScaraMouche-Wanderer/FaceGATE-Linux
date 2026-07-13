import unittest
import numpy as np
from unittest.mock import patch, MagicMock
from recognition.matcher import cosine_similarity, match_face

class TestMatcher(unittest.TestCase):
    def test_cosine_similarity(self):
        # Orthogonal vectors -> 0
        v1 = np.array([1, 0, 0], dtype=np.float32)
        v2 = np.array([0, 1, 0], dtype=np.float32)
        self.assertAlmostEqual(cosine_similarity(v1, v2), 0.0)

        # Same vectors -> 1
        self.assertAlmostEqual(cosine_similarity(v1, v1), 1.0)

        # Opposite vectors -> -1
        v3 = np.array([-1, 0, 0], dtype=np.float32)
        self.assertAlmostEqual(cosine_similarity(v1, v3), -1.0)

    @patch('recognition.matcher.get_config')
    @patch('recognition.matcher.cosine_similarity')
    def test_match_face_ambiguity_rejection(self, mock_cos, mock_get_config):
        # Mock config with threshold 0.65 and ambiguity margin 0.03
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda key, default=None: {
            "recognition.similarity_threshold": 0.65,
            "recognition.ambiguity_margin": 0.03
        }.get(key, default)
        mock_get_config.return_value = mock_config

        # 2 enrolled users
        enrolled = {
            "user1": np.zeros(512),
            "user2": np.zeros(512)
        }

        # Case 1: Ambiguity rejection (user1=0.66, user2=0.64, margin=0.02 < 0.03, user2 is below threshold)
        mock_cos.side_effect = lambda live, stored: 0.66 if stored is enrolled["user1"] else 0.64
        matched_name, confidence = match_face(np.zeros(512), enrolled=enrolled)
        self.assertIsNone(matched_name)
        self.assertEqual(confidence, 0.66)

    @patch('recognition.matcher.get_config')
    @patch('recognition.matcher.cosine_similarity')
    def test_match_face_dual_match_acceptance(self, mock_cos, mock_get_config):
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda key, default=None: {
            "recognition.similarity_threshold": 0.65,
            "recognition.ambiguity_margin": 0.03
        }.get(key, default)
        mock_get_config.return_value = mock_config

        # 2 enrolled users
        enrolled = {
            "user1": np.zeros(512),
            "user2": np.zeros(512)
        }

        # Case 2: Dual match acceptance (both are above threshold, e.g. user1=0.85, user2=0.84)
        mock_cos.side_effect = lambda live, stored: 0.85 if stored is enrolled["user1"] else 0.84
        matched_name, confidence = match_face(np.zeros(512), enrolled=enrolled)
        self.assertEqual(matched_name, "user1")
        self.assertEqual(confidence, 0.85)

if __name__ == "__main__":
    unittest.main()
