from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import math
import chess
from lichess_api import MoveStats, LichessAPI


@dataclass
class ScoreDetails:
    total_score: float
    expected_score: float
    high_rating_pref: float
    sharpness: float
    expected_score_weighted: float
    high_rating_pref_weighted: float
    sharpness_weighted: float
    win_rate_weight: float
    popularity_weight: float
    sharpness_weight: float
    
    def format_comment(self, include_details: bool = True) -> str:
        """Format score details as PGN comment."""
        if not include_details:
            return ""
        
        # Use conservative format for maximum PGN compatibility
        # Avoid special characters that might interfere with PGN parsing
        return (f"{{ Score: {self.total_score:.3f} "
                f"[Win: {self.expected_score:.3f}, "
                f"Pref: {self.high_rating_pref:.3f}, "
                f"Sharp: {self.sharpness:.3f}] }}")
    
    def format_detailed(self) -> str:
        """Format score details for console output."""
        return (f"Total: {self.total_score:.3f} = "
                f"Score: {self.expected_score:.3f}*{self.win_rate_weight} + "
                f"Pref: {self.high_rating_pref:.3f}*{self.popularity_weight} + "
                f"Sharp: {self.sharpness:.3f}*{self.sharpness_weight}")


class MoveAnalyzer:
    def __init__(self, win_rate_weight: float, popularity_weight: float, sharpness_weight: float = 0.0):
        # win_rate_weight: weight for expected score
        # popularity_weight: weight for high-rating preference
        # sharpness_weight: weight for tactical sharpness
        self.win_rate_weight = win_rate_weight
        self.popularity_weight = popularity_weight
        self.sharpness_weight = sharpness_weight
        self.lichess_api = None
    
    def set_api(self, api: LichessAPI):
        """Set the LichessAPI instance for high-rating analysis."""
        self.lichess_api = api
    
    def calculate_entropy_sharpness(self, board: chess.Board, move_san: str, 
                                   min_rating: int, max_rating: int, time_controls: List[str]) -> float:
        """
        Calculate move sharpness based on entropy of opponent's response probabilities.
        Sharp moves limit opponent's good options (low entropy = high sharpness).
        Returns value between 0 (many good replies) and 1 (few good replies).
        """
        if not self.lichess_api:
            return 0.0
        
        # Make the move to get the resulting position
        temp_board = board.copy()
        try:
            move = temp_board.parse_san(move_san)
            temp_board.push(move)
        except:
            return 0.0
        
        # Get opponent's response data from the resulting position
        position_data = self.lichess_api.get_position_stats(
            temp_board.fen(), min_rating, max_rating, time_controls, False
        )
        
        if not position_data or position_data.get("total_games", 0) < 50:
            return 0.0  # Not enough data to calculate entropy
        
        moves_data = position_data.get("moves", {})
        if len(moves_data) < 2:
            return 1.0  # Only one response = maximum sharpness
        
        # Calculate probabilities of each opponent response
        total_games = position_data["total_games"]
        probabilities = []
        
        for move_data in moves_data.values():
            prob = move_data["games"] / total_games
            if prob > 0:  # Avoid log(0)
                probabilities.append(prob)
        
        if len(probabilities) < 2:
            return 1.0
        
        # Calculate Shannon entropy: H = -Σ(p_i * log2(p_i))
        entropy = -sum(p * math.log2(p) for p in probabilities)
        
        # Normalize entropy to [0, 1] range
        # Maximum entropy occurs when all moves are equally likely
        max_entropy = math.log2(len(probabilities))
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
        
        # Sharpness is inverse of entropy (low entropy = high sharpness)
        sharpness = 1.0 - normalized_entropy
        
        return max(0.0, min(1.0, sharpness))

    def calculate_move_score(self, move_stats: MoveStats, total_games: int, high_rating_preference: float,
                           board: chess.Board, move_san: str, min_rating: int, max_rating: int, 
                           time_controls: List[str]) -> ScoreDetails:
        if total_games == 0 or move_stats.games == 0:
            return ScoreDetails(
                total_score=0.0, expected_score=0.0, high_rating_pref=0.0, sharpness=0.0,
                expected_score_weighted=0.0, high_rating_pref_weighted=0.0, sharpness_weighted=0.0,
                win_rate_weight=self.win_rate_weight, popularity_weight=self.popularity_weight,
                sharpness_weight=self.sharpness_weight
            )
        
        # Calculate individual components
        expected_score = move_stats.expected_score
        
        # Normalize high_rating_preference to be in similar range as expected_score
        # High rating preference is typically in range [-0.2, 0.2], normalize to [0, 1]
        normalized_high_pref = (high_rating_preference + 0.2) / 0.4
        normalized_high_pref = max(0.0, min(1.0, normalized_high_pref))  # Clamp to [0, 1]
        
        # Calculate entropy-based sharpness
        sharpness = self.calculate_entropy_sharpness(board, move_san, min_rating, max_rating, time_controls)
        
        # Calculate weighted components
        expected_score_weighted = expected_score * self.win_rate_weight
        high_rating_pref_weighted = normalized_high_pref * self.popularity_weight
        sharpness_weighted = sharpness * self.sharpness_weight
        
        # Total score
        total_score = expected_score_weighted + high_rating_pref_weighted + sharpness_weighted
        
        return ScoreDetails(
            total_score=total_score,
            expected_score=expected_score,
            high_rating_pref=normalized_high_pref,
            sharpness=sharpness,
            expected_score_weighted=expected_score_weighted,
            high_rating_pref_weighted=high_rating_pref_weighted,
            sharpness_weighted=sharpness_weighted,
            win_rate_weight=self.win_rate_weight,
            popularity_weight=self.popularity_weight,
            sharpness_weight=self.sharpness_weight
        )
    
    def get_high_rating_preference(self, move: str, position_data: Dict) -> float:
        """Get pre-calculated high-rating preference from cached data."""
        if not position_data:
            return 0.0
        
        # Get pre-calculated preferences from comprehensive cache
        preferences = position_data.get('high_rating_preferences', {})
        return preferences.get(move, 0.0)
    
    def analyze_position(self, position_data: Dict, threshold: float, fen: Optional[str], 
                        min_rating: int, max_rating: int, time_controls: List[str]) -> List[Tuple[str, MoveStats, ScoreDetails]]:
        total_games = position_data.get("total_games", 0)
        moves_data = position_data.get("moves", {})
        
        if total_games == 0:
            return []
        
        # Create board from FEN for sharpness calculation
        board = chess.Board(fen) if fen else chess.Board()
        
        analyzed_moves = []
        
        for san, move_data in moves_data.items():
            move_stats = MoveStats(
                wins=move_data["wins"],
                draws=move_data["draws"],
                losses=move_data["losses"],
                games=move_data["games"]
            )
            
            popularity = move_stats.games / total_games
            if popularity >= threshold:
                # Get high rating preference from cached data
                high_rating_pref = self.get_high_rating_preference(san, position_data)
                
                # Calculate detailed score with entropy-based sharpness
                score_details = self.calculate_move_score(
                    move_stats, total_games, high_rating_pref,
                    board, san, min_rating, max_rating, time_controls
                )
                analyzed_moves.append((san, move_stats, score_details))
        
        # Sort by total score
        analyzed_moves.sort(key=lambda x: x[2].total_score, reverse=True)
        return analyzed_moves
    
    def get_best_move(self, analyzed_moves: List[Tuple[str, MoveStats, ScoreDetails]]) -> Optional[Tuple[str, MoveStats, ScoreDetails]]:
        if not analyzed_moves:
            return None
        return analyzed_moves[0]
    
