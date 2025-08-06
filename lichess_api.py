import yaml
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
import chess


class LichessAPI:
    def __init__(self, api_key: Optional[str]):
        self.base_url = "https://explorer.lichess.ovh"
        self.cache_file = Path("data/cache.json")  # Fixed cache file location
        self.api_key = api_key
        self.api_delay = 0.075  # Hardcoded 0.075 second delay for respectful API usage
        self.cache = self._load_cache()
        self.last_request_time = 0
    
    def _load_cache(self) -> Dict:
        """Load cache with automatic recovery from backup if main file is corrupted."""
        
        # Try to load main cache file
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    if self.cache_file.suffix == '.json':
                        import json
                        return json.load(f)
                    else:
                        return yaml.safe_load(f) or {}
            except (yaml.YAMLError, IOError, json.JSONDecodeError) as e:
                print(f"Warning: Main cache file corrupted: {e}")
                
                # Try to recover from backup
                backup_file = self.cache_file.with_suffix(self.cache_file.suffix + '.backup')
                if backup_file.exists():
                    try:
                        print("Attempting to recover from backup...")
                        with open(backup_file, 'r') as f:
                            if self.cache_file.suffix == '.json':
                                import json
                                recovered_cache = json.load(f)
                            else:
                                recovered_cache = yaml.safe_load(f) or {}
                        
                        print(f"✅ Successfully recovered cache from backup ({len(recovered_cache)} entries)")
                        return recovered_cache
                        
                    except (yaml.YAMLError, IOError, json.JSONDecodeError) as backup_error:
                        print(f"❌ Backup recovery failed: {backup_error}")
                
                print("Starting with empty cache...")
                return {}
        
        return {}
    
    def _save_cache(self):
        """Save cache with atomic write and backup to prevent corruption on interruption."""
        import shutil
        
        # Create backup if cache file exists
        if self.cache_file.exists():
            backup_file = self.cache_file.with_suffix(self.cache_file.suffix + '.backup')
            shutil.copy2(str(self.cache_file), str(backup_file))
        
        # Create temporary file in same directory
        temp_file = self.cache_file.with_suffix(self.cache_file.suffix + '.tmp')
        
        try:
            # Write to temporary file first
            with open(temp_file, 'w') as f:
                if self.cache_file.suffix == '.json':
                    import json
                    json.dump(self.cache, f, indent=2)
                else:
                    yaml.dump(self.cache, f, default_flow_style=False, indent=2)
            
            # Atomic rename (safe on most filesystems)
            shutil.move(str(temp_file), str(self.cache_file))
            
        except Exception as e:
            # Clean up temp file if something went wrong
            if temp_file.exists():
                temp_file.unlink()
            print(f"Warning: Cache save failed: {e}")
            raise e
    
    def _get_cache_key(self, fen: str, min_rating: int, max_rating: int, time_controls: List[str]) -> str:
        key_data = f"{fen}_{min_rating}_{max_rating}_{'_'.join(sorted(time_controls))}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _rate_limit(self):
        """Always apply 0.075 second rate limiting to be respectful to Lichess servers."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.api_delay:
            time.sleep(self.api_delay - time_since_last)
        self.last_request_time = time.time()
    
    def get_position_stats(self, fen: str, min_rating: int, max_rating: int,
                          time_controls: List[str], include_rating_breakdown: bool) -> Optional[Dict]:
        
        cache_key = self._get_cache_key(fen, min_rating, max_rating, time_controls)
        
        if cache_key in self.cache:

            return self.cache[cache_key]
        
        # Lichess ratings are in 100-point brackets: 1600, 1700, 1800, etc.
        rating_brackets = []
        for rating in range(min_rating, max_rating + 1, 100):
            rating_brackets.append(str(rating))
        
        params = {
            "fen": fen,
            "ratings": ",".join(rating_brackets),
            "speeds": ",".join(time_controls)
        }
        
        # Retry logic
        max_retries = 3
        
        for attempt in range(max_retries):
            self._rate_limit()
            
            try:
                headers = {}
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                
                response = requests.get(f"{self.base_url}/lichess", params=params, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                processed_data = self._process_lichess_response(data)
                self.cache[cache_key] = processed_data
                self._save_cache()
                

                return processed_data
                
            except requests.RequestException as e:
                if attempt < max_retries - 1:  # Not the last attempt
                    print(f"API request failed (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"Retrying in 5 seconds...")
                    time.sleep(5)  # Wait 5 seconds before retry
                else:
                    print(f"API request failed after {max_retries} attempts: {e}")
                    return None
        
        return None
    
    def get_comprehensive_position_stats(self, fen: str, min_rating: int, max_rating: int,
                                       time_controls: List[str]) -> Optional[Dict]:
        """Get position stats with high-rating preference data pre-calculated."""
        
        # Create a comprehensive cache key that includes rating breakdown
        comprehensive_key = self._get_cache_key(fen, min_rating, max_rating, time_controls) + "_comprehensive"
        
        if comprehensive_key in self.cache:
            return self.cache[comprehensive_key]
        
        # Get main position data
        main_data = self.get_position_stats(fen, min_rating, max_rating, time_controls, False)
        if not main_data:
            return None
        
        # Get high rating data (2200+) if max_rating > 2200
        high_rating_data = None
        if max_rating > 2200:
            high_rating_data = self.get_position_stats(fen, 2200, max_rating, time_controls, False)
        
        # Get low rating data (min_rating to 2199) if min_rating < 2200
        low_rating_data = None
        if min_rating < 2200:
            low_rating_data = self.get_position_stats(fen, min_rating, min(2199, max_rating), time_controls, False)
        
        # Calculate high-rating preferences for each move
        move_preferences = {}
        if high_rating_data and low_rating_data:
            high_moves = high_rating_data.get('moves', {})
            low_moves = low_rating_data.get('moves', {})
            high_total = high_rating_data.get('total_games', 1)
            low_total = low_rating_data.get('total_games', 1)
            
            for move in main_data.get('moves', {}):
                if move in high_moves and move in low_moves:
                    high_popularity = high_moves[move]['games'] / high_total
                    low_popularity = low_moves[move]['games'] / low_total
                    move_preferences[move] = high_popularity - low_popularity
                else:
                    move_preferences[move] = 0.0
        
        # Create comprehensive data structure
        comprehensive_data = main_data.copy()
        comprehensive_data['high_rating_preferences'] = move_preferences
        comprehensive_data['high_rating_data'] = high_rating_data
        comprehensive_data['low_rating_data'] = low_rating_data
        
        # Cache the comprehensive data
        self.cache[comprehensive_key] = comprehensive_data
        self._save_cache()
        
        return comprehensive_data
    
    def _process_lichess_response(self, data: Dict) -> Dict:
        total_games = data.get("white", 0) + data.get("draws", 0) + data.get("black", 0)
        
        moves = {}
        for move_data in data.get("moves", []):
            san = move_data.get("san", "")
            white_wins = move_data.get("white", 0)
            draws = move_data.get("draws", 0)
            black_wins = move_data.get("black", 0)
            games = white_wins + draws + black_wins
            
            if games > 0:
                moves[san] = {
                    "wins": white_wins,
                    "draws": draws,
                    "losses": black_wins,
                    "games": games
                }
        
        return {
            "total_games": total_games,
            "white": data.get("white", 0),
            "draws": data.get("draws", 0), 
            "black": data.get("black", 0),
            "moves": moves
        }


class MoveStats:
    def __init__(self, wins: int, draws: int, losses: int, games: int):
        self.wins = wins
        self.draws = draws
        self.losses = losses
        self.games = games
    
    @property
    def expected_score(self) -> float:
        if self.games == 0:
            return 0.0
        return (self.wins + 0.5 * self.draws) / self.games
    
    @property
    def win_rate(self) -> float:
        if self.games == 0:
            return 0.0
        return self.wins / self.games
    
    def __repr__(self):
        return f"MoveStats(wins={self.wins}, draws={self.draws}, losses={self.losses}, games={self.games})"