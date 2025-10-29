"""
Persistent storage for results history and user preferences.
Credentials are encrypted using Fernet (symmetric encryption).
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd
import base64
from cryptography.fernet import Fernet
import hashlib


class Storage:
    """Handle persistent storage of results and preferences."""
    
    def __init__(self, base_dir: str = "./data"):
        self.base_dir = Path(base_dir)
        self.results_dir = self.base_dir / "results"
        self.prefs_file = self.base_dir / "preferences.json"
        self.key_file = self.base_dir / ".key"
        
        # Create directories if they don't exist
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize encryption key
        self._init_encryption_key()
    
    def _init_encryption_key(self):
        """Initialize or load encryption key."""
        if not self.key_file.exists():
            # Generate a new key based on machine-specific data
            # This ties the key to this specific machine
            import platform
            import uuid
            machine_id = f"{platform.node()}-{uuid.getnode()}".encode()
            key_material = hashlib.sha256(machine_id).digest()
            key = base64.urlsafe_b64encode(key_material)
            
            with open(self.key_file, 'wb') as f:
                f.write(key)
        else:
            with open(self.key_file, 'rb') as f:
                key = f.read()
        
        self.cipher = Fernet(key)
    
    def save_result(self, result: Dict) -> str:
        """
        Save a result to disk.
        
        Args:
            result: Dictionary containing timestamp, domain, total, found, df
        
        Returns:
            Filename of saved result
        """
        timestamp = result['timestamp']
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        
        # Create filename from timestamp
        filename = f"result_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.results_dir / filename
        
        # Convert DataFrame to dict for JSON serialization
        result_copy = result.copy()
        if 'df' in result_copy and isinstance(result_copy['df'], pd.DataFrame):
            result_copy['df'] = result_copy['df'].to_dict('records')
        
        # Convert timestamp to ISO string
        if isinstance(result_copy['timestamp'], datetime):
            result_copy['timestamp'] = result_copy['timestamp'].isoformat()
        
        # Save to JSON
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result_copy, f, indent=2, ensure_ascii=False)
        
        return filename
    
    def load_results(self, limit: int = 50) -> List[Dict]:
        """
        Load recent results from disk.
        
        Args:
            limit: Maximum number of results to load (most recent first)
        
        Returns:
            List of result dictionaries
        """
        results = []
        
        # Get all result files sorted by modification time (newest first)
        result_files = sorted(
            self.results_dir.glob("result_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        for filepath in result_files[:limit]:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                
                # Convert timestamp back to datetime
                if isinstance(result['timestamp'], str):
                    result['timestamp'] = datetime.fromisoformat(result['timestamp'])
                
                # Convert df back to DataFrame
                if 'df' in result and isinstance(result['df'], list):
                    result['df'] = pd.DataFrame(result['df'])
                
                results.append(result)
            except Exception as e:
                print(f"Error loading {filepath}: {e}")
                continue
        
        return results
    
    def delete_result(self, timestamp: datetime) -> bool:
        """
        Delete a specific result.
        
        Args:
            timestamp: Timestamp of the result to delete
        
        Returns:
            True if deleted, False if not found
        """
        filename = f"result_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.results_dir / filename
        
        if filepath.exists():
            filepath.unlink()
            return True
        return False
    
    def clear_all_results(self) -> int:
        """
        Delete all saved results.
        
        Returns:
            Number of results deleted
        """
        count = 0
        for filepath in self.results_dir.glob("result_*.json"):
            filepath.unlink()
            count += 1
        return count
    
    def save_preferences(self, prefs: Dict) -> None:
        """
        Save user preferences (credentials are encrypted).
        
        Args:
            prefs: Dictionary of preferences (e.g., API credentials)
        """
        # Encrypt sensitive fields
        encrypted_prefs = prefs.copy()
        
        if 'user_password' in encrypted_prefs and encrypted_prefs['user_password']:
            password_bytes = encrypted_prefs['user_password'].encode('utf-8')
            encrypted_prefs['user_password'] = self.cipher.encrypt(password_bytes).decode('utf-8')
        
        with open(self.prefs_file, 'w', encoding='utf-8') as f:
            json.dump(encrypted_prefs, f, indent=2)
    
    def load_preferences(self) -> Optional[Dict]:
        """
        Load user preferences (decrypts credentials).
        
        Returns:
            Dictionary of preferences or None if file doesn't exist
        """
        if not self.prefs_file.exists():
            return None
        
        try:
            with open(self.prefs_file, 'r', encoding='utf-8') as f:
                prefs = json.load(f)
            
            # Decrypt sensitive fields
            if 'user_password' in prefs and prefs['user_password']:
                try:
                    encrypted_bytes = prefs['user_password'].encode('utf-8')
                    prefs['user_password'] = self.cipher.decrypt(encrypted_bytes).decode('utf-8')
                except Exception:
                    # If decryption fails, clear the password
                    prefs['user_password'] = ""
            
            return prefs
        except Exception as e:
            print(f"Error loading preferences: {e}")
            return None
    
    def clear_preferences(self) -> bool:
        """
        Delete saved preferences.
        
        Returns:
            True if deleted, False if not found
        """
        if self.prefs_file.exists():
            self.prefs_file.unlink()
            return True
        return False
    
    def get_storage_stats(self) -> Dict:
        """
        Get statistics about stored data.
        
        Returns:
            Dictionary with storage statistics
        """
        result_files = list(self.results_dir.glob("result_*.json"))
        total_size = sum(f.stat().st_size for f in result_files)
        
        return {
            'total_results': len(result_files),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'has_preferences': self.prefs_file.exists()
        }

