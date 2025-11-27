"""
Speaker Identification Service using NVIDIA NeMo TitaNet
Enables user enrollment and recognition based on voice embeddings
"""

import logging
import numpy as np
import torch
import pickle
from pathlib import Path
from typing import Dict, Optional, Tuple, List
import soundfile as sf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SpeakerIdentificationService:
    """
    Speaker Identification using NVIDIA NeMo TitaNet model
    Supports user enrollment and real-time speaker recognition
    """
    
    def __init__(self, threshold: float = 0.7, device: str = "cpu"):
        """
        Initialize Speaker ID service
        
        Args:
            threshold: Similarity threshold for identification (0-1)
            device: Device to run on (cpu or cuda)
        """
        self.threshold = threshold
        self.device = device
        self.model = None
        logger.info(f"Initializing Speaker ID Service (threshold={threshold}, device={device})")
        
    def load_model(self):
        """Load TitaNet speaker recognition model from NeMo"""
        if self.model is None:
            try:
                from nemo.collections.asr.models import EncDecSpeakerLabelModel
                
                logger.info("Loading NeMo TitaNet model...")
                # Load pre-trained TitaNet model
                self.model = EncDecSpeakerLabelModel.from_pretrained("nvidia/speakerverification_en_titanet_large")
                self.model.eval()
                self.model.to(self.device)
                
                logger.info("✅ TitaNet model loaded successfully")
                
            except Exception as e:
                logger.error(f"Failed to load TitaNet model: {e}")
                raise
    
    def extract_embedding(self, audio_path: str) -> np.ndarray:
        """
        Extract speaker embedding from audio file
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Speaker embedding as numpy array
        """
        self.load_model()
        
        logger.info(f"Extracting embedding from: {audio_path}")
        
        try:
            # Get embedding from model
            embedding = self.model.get_embedding(audio_path)
            
            # Convert to numpy
            if torch.is_tensor(embedding):
                embedding_np = embedding.cpu().detach().numpy()
            else:
                embedding_np = np.array(embedding)
            
            # Ensure 1D array
            embedding_np = embedding_np.flatten()
            
            logger.info(f"Embedding shape: {embedding_np.shape}")
            return embedding_np
            
        except Exception as e:
            logger.error(f"Error extracting embedding: {e}")
            raise
    
    def enroll_speaker(self, user_id: str, audio_files: List[str]) -> np.ndarray:
        """
        Enroll a new speaker by averaging embeddings from multiple audio samples
        
        Args:
            user_id: Unique identifier for the user
            audio_files: List of paths to audio files (3-5 recommended)
            
        Returns:
            Average embedding for the user
        """
        logger.info(f"Enrolling user '{user_id}' with {len(audio_files)} audio samples")
        
        if len(audio_files) < 1:
            raise ValueError("At least 1 audio file required for enrollment")
        
        # Extract embeddings from all audio files
        embeddings = []
        for audio_file in audio_files:
            try:
                emb = self.extract_embedding(audio_file)
                embeddings.append(emb)
            except Exception as e:
                logger.warning(f"Failed to process {audio_file}: {e}")
        
        if not embeddings:
            raise ValueError("Failed to extract any valid embeddings")
        
        # Average the embeddings for robust representation
        avg_embedding = np.mean(embeddings, axis=0)
        
        # Normalize the embedding
        avg_embedding = avg_embedding / np.linalg.norm(avg_embedding)
        
        logger.info(f"✅ User '{user_id}' enrolled successfully")
        logger.info(f"   Samples used: {len(embeddings)}")
        logger.info(f"   Embedding shape: {avg_embedding.shape}")
        
        return avg_embedding
    
    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding
            embedding2: Second embedding
            
        Returns:
            Similarity score (0-1, higher = more similar)
        """
        # Ensure embeddings are normalized
        emb1 = embedding1 / np.linalg.norm(embedding1)
        emb2 = embedding2 / np.linalg.norm(embedding2)
        
        # Compute cosine similarity
        similarity = np.dot(emb1, emb2)
        
        # Clip to [0, 1] range
        similarity = np.clip(similarity, 0.0, 1.0)
        
        return float(similarity)
    
    def identify_speaker(
        self, 
        audio_path: str, 
        enrolled_users: Dict[str, np.ndarray]
    ) -> Tuple[Optional[str], float]:
        """
        Identify speaker from audio file
        
        Args:
            audio_path: Path to audio file
            enrolled_users: Dictionary of {user_id: embedding}
            
        Returns:
            Tuple of (user_id, confidence) or (None, best_score) if unknown
        """
        logger.info(f"Identifying speaker from: {audio_path}")
        
        if not enrolled_users:
            logger.warning("No enrolled users in database")
            return None, 0.0
        
        # Extract embedding from query audio
        query_embedding = self.extract_embedding(audio_path)
        
        # Compare with all enrolled users
        best_match = None
        best_score = 0.0
        
        for user_id, enrolled_embedding in enrolled_users.items():
            similarity = self.compute_similarity(query_embedding, enrolled_embedding)
            logger.debug(f"  {user_id}: {similarity:.4f}")
            
            if similarity > best_score:
                best_score = similarity
                best_match = user_id
        
        # Check if best match exceeds threshold
        if best_score >= self.threshold:
            logger.info(f"✅ Identified: {best_match} (confidence: {best_score:.4f})")
            return best_match, best_score
        else:
            logger.info(f"❌ Unknown speaker (best match: {best_match} with {best_score:.4f})")
            return None, best_score
    
    def save_embedding(self, embedding: np.ndarray, file_path: str):
        """
        Save embedding to file
        
        Args:
            embedding: Speaker embedding
            file_path: Path to save the embedding
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'wb') as f:
            pickle.dump(embedding, f)
        
        logger.info(f"Embedding saved to: {file_path}")
    
    def load_embedding(self, file_path: str) -> np.ndarray:
        """
        Load embedding from file
        
        Args:
            file_path: Path to embedding file
            
        Returns:
            Speaker embedding
        """
        with open(file_path, 'rb') as f:
            embedding = pickle.load(f)
        
        logger.info(f"Embedding loaded from: {file_path}")
        return embedding
    
    def load_all_embeddings(self, embeddings_dir: str) -> Dict[str, np.ndarray]:
        """
        Load all user embeddings from directory
        
        Args:
            embeddings_dir: Directory containing embedding files
            
        Returns:
            Dictionary of {user_id: embedding}
        """
        embeddings_dir = Path(embeddings_dir)
        enrolled_users = {}
        
        if not embeddings_dir.exists():
            logger.warning(f"Embeddings directory not found: {embeddings_dir}")
            return enrolled_users
        
        for emb_file in embeddings_dir.glob("*.pkl"):
            user_id = emb_file.stem
            try:
                embedding = self.load_embedding(emb_file)
                enrolled_users[user_id] = embedding
                logger.info(f"Loaded embedding for user: {user_id}")
            except Exception as e:
                logger.error(f"Failed to load embedding for {user_id}: {e}")
        
        logger.info(f"Loaded {len(enrolled_users)} enrolled users")
        return enrolled_users
    
    def verify_speaker(
        self, 
        audio_path: str, 
        user_id: str, 
        enrolled_users: Dict[str, np.ndarray]
    ) -> Tuple[bool, float]:
        """
        Verify if audio matches a specific enrolled user
        
        Args:
            audio_path: Path to audio file
            user_id: User ID to verify against
            enrolled_users: Dictionary of enrolled users
            
        Returns:
            Tuple of (is_match, confidence_score)
        """
        if user_id not in enrolled_users:
            logger.warning(f"User '{user_id}' not found in enrolled users")
            return False, 0.0
        
        # Extract query embedding
        query_embedding = self.extract_embedding(audio_path)
        
        # Compare with target user's embedding
        similarity = self.compute_similarity(query_embedding, enrolled_users[user_id])
        
        is_match = similarity >= self.threshold
        
        logger.info(f"Verification: {user_id} - {'✅ MATCH' if is_match else '❌ NO MATCH'} ({similarity:.4f})")
        
        return is_match, similarity


def main():
    """Demo and testing of Speaker Identification Service"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python speaker_identification.py enroll <user_id> <audio1.wav> [audio2.wav ...]")
        print("  python speaker_identification.py identify <audio.wav>")
        print("  python speaker_identification.py verify <user_id> <audio.wav>")
        return
    
    from src.wikiquote_voice.config import Config
    
    # Initialize service
    speaker_id = SpeakerIdentificationService(threshold=0.7)
    
    # Embeddings directory
    embeddings_dir = Path(Config.DATA_DIR) / "embeddings"
    embeddings_dir.mkdir(parents=True, exist_ok=True)
    
    command = sys.argv[1].lower()
    
    if command == "enroll":
        if len(sys.argv) < 4:
            print("Error: Need user_id and at least one audio file")
            return
        
        user_id = sys.argv[2]
        audio_files = sys.argv[3:]
        
        print(f"\n🎤 Enrolling user: {user_id}")
        print(f"📁 Audio files: {len(audio_files)}")
        
        # Enroll user
        embedding = speaker_id.enroll_speaker(user_id, audio_files)
        
        # Save embedding
        embedding_path = embeddings_dir / f"{user_id}.pkl"
        speaker_id.save_embedding(embedding, embedding_path)
        
        print(f"✅ User '{user_id}' enrolled successfully!")
        print(f"💾 Embedding saved to: {embedding_path}")
    
    elif command == "identify":
        if len(sys.argv) < 3:
            print("Error: Need audio file path")
            return
        
        audio_path = sys.argv[2]
        
        # Load all enrolled users
        enrolled_users = speaker_id.load_all_embeddings(embeddings_dir)
        
        if not enrolled_users:
            print("❌ No enrolled users found. Enroll users first!")
            return
        
        print(f"\n🔍 Identifying speaker from: {audio_path}")
        print(f"👥 Enrolled users: {', '.join(enrolled_users.keys())}")
        
        # Identify
        user_id, confidence = speaker_id.identify_speaker(audio_path, enrolled_users)
        
        if user_id:
            print(f"\n✅ Identified: {user_id}")
            print(f"🎯 Confidence: {confidence:.2%}")
        else:
            print(f"\n❌ Unknown speaker")
            print(f"🎯 Best match score: {confidence:.2%}")
    
    elif command == "verify":
        if len(sys.argv) < 4:
            print("Error: Need user_id and audio file")
            return
        
        user_id = sys.argv[2]
        audio_path = sys.argv[3]
        
        # Load enrolled users
        enrolled_users = speaker_id.load_all_embeddings(embeddings_dir)
        
        print(f"\n🔐 Verifying: {user_id}")
        print(f"📁 Audio: {audio_path}")
        
        # Verify
        is_match, confidence = speaker_id.verify_speaker(audio_path, user_id, enrolled_users)
        
        if is_match:
            print(f"\n✅ VERIFIED: This is {user_id}")
            print(f"🎯 Confidence: {confidence:.2%}")
        else:
            print(f"\n❌ NOT VERIFIED: This is not {user_id}")
            print(f"🎯 Similarity: {confidence:.2%}")
    
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
