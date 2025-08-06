#!/usr/bin/env python3
import chess
import yaml
import os
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from collections import deque
from lichess_api import LichessAPI, MoveStats
from move_analyzer import MoveAnalyzer
from repertoire_node import RepertoireNode


class RepertoireBuilder:
    def __init__(self, lichess_api: LichessAPI, move_analyzer: MoveAnalyzer,
                 min_games: int, white_win_rate_threshold: float):
        self.lichess_api = lichess_api
        self.move_analyzer = move_analyzer
        self.move_analyzer.set_api(lichess_api)  # Set API for high-rating analysis
        self.min_games = min_games
        self.white_win_rate_threshold = white_win_rate_threshold
        self.move_count = 0
    
    def build_repertoire(self, opening_move: Optional[str], fen: Optional[str], max_depth: int,
                        initial_threshold: float, position_threshold: float,
                        min_rating: int, max_rating: int, time_controls: List[str]) -> RepertoireNode:
        self.move_count = 0
        if fen:
            # Build from arbitrary position
            try:
                board = chess.Board(fen)
            except ValueError:
                raise ValueError(f"Invalid FEN: {fen}")
            
            # Determine if it's White's turn to move
            is_white_turn = board.turn == chess.WHITE
            root = RepertoireNode(move="Position", fen=fen)
            
            self._build_repertoire_bfs(root, max_depth, initial_threshold, position_threshold,
                                      min_rating, max_rating, time_controls)
        
        elif opening_move:
            # Build from opening move (original behavior)
            board = chess.Board()
            
            try:
                move = board.parse_san(opening_move)
                board.push(move)
            except ValueError:
                raise ValueError(f"Invalid opening move: {opening_move}")
            
            root = RepertoireNode(move=opening_move, fen=board.fen())
            
            self._build_repertoire_bfs(root, max_depth, initial_threshold, position_threshold,
                                      min_rating, max_rating, time_controls)
        
        else:
            raise ValueError("Either opening_move or fen must be provided")
        
        return root
    
    def _build_repertoire_bfs(self, root: RepertoireNode, max_depth: int, initial_threshold: float, 
                             position_threshold: float, min_rating: int, max_rating: int, 
                             time_controls: List[str]):
        # Queue contains tuples of (node, board, current_depth, is_white_turn)
        queue = deque()
        
        # Initialize queue based on root type
        if root.move == "Position":
            # Starting from arbitrary position
            board = chess.Board(root.fen)
            is_white_turn = board.turn == chess.WHITE
            queue.append((root, board, 0, is_white_turn))
        else:
            # Starting from opening move
            board = chess.Board()
            move = board.parse_san(root.move)
            board.push(move)
            queue.append((root, board, 1, False))  # After opening move, it's Black's turn
        
        while queue:
            current_node, current_board, current_depth, is_white_turn = queue.popleft()
            
            # Process this node and get children to add to queue
            children_to_process = self._process_node_bfs(
                current_node, current_board, current_depth, max_depth,
                initial_threshold, position_threshold, min_rating, max_rating,
                time_controls, is_white_turn
            )
            
            # Add children to queue for processing
            queue.extend(children_to_process)
    
    def _process_node_bfs(self, node: RepertoireNode, board: chess.Board, current_depth: int,
                   max_depth: int, initial_threshold: float, position_threshold: float,
                   min_rating: int, max_rating: int, time_controls: List[str], is_white_turn: bool):
        
        children_to_queue = []
        
        position_data = self.lichess_api.get_position_stats(
            board.fen(), min_rating, max_rating, time_controls, True
        )
        
        if not position_data:
            node.termination_reason = "API error"
            return children_to_queue

        # Check if White has too high a win rate (position is too good for White)
        # This applies to positions where it's Black's turn to move
        if not is_white_turn:
            # Get the raw position stats (not move stats)
            white_wins = position_data.get("white", 0)
            draws = position_data.get("draws", 0) 
            black_wins = position_data.get("black", 0)
            total_position_games = white_wins + draws + black_wins
            
            if total_position_games > 0:
                white_win_rate = white_wins / total_position_games
                if white_win_rate > self.white_win_rate_threshold:
                    node.termination_reason = f"White win rate {white_win_rate:.1%} > {self.white_win_rate_threshold:.0%}"
                    return children_to_queue
        
        if current_depth >= max_depth:
            node.termination_reason = "Max depth reached"
            return children_to_queue
        
        total_games = position_data.get("total_games", 0)
        if total_games < self.min_games:
            node.termination_reason = f"Insufficient games ({total_games} < {self.min_games})"
            return children_to_queue
        
        threshold = initial_threshold if current_depth == 1 else position_threshold
        analyzed_moves = self.move_analyzer.analyze_position(position_data, threshold, 
                                                           board.fen(), min_rating, 
                                                           max_rating, time_controls)
        
        if not analyzed_moves:
            node.termination_reason = f"No moves above {threshold*100:.0f}% threshold"
            return children_to_queue

        
        # Print score breakdown for the best move (first in sorted list)
        if analyzed_moves and self.move_count % 50 == 0:
            best_san, best_stats, best_score = analyzed_moves[0]
            print(f"Best move at {board.fen()[:30]}...: {best_san} - {best_score.format_detailed()}")
        
        for san, move_stats, score_details in analyzed_moves:
            try:
                move = board.parse_san(san)
                board.push(move)
                
                self.move_count += 1
                if self.move_count % 10 == 0:
                    print(f"Processed {self.move_count} moves")
                
                child_node = RepertoireNode(
                    move=san,
                    fen=board.fen(),
                    move_stats=move_stats,
                    score_details=score_details
                )
                
                node.add_child(child_node)
                
                if is_white_turn:
                    # Add child to queue for BFS processing
                    child_board = board.copy()
                    children_to_queue.append((child_node, child_board, current_depth + 1, False))
                else:
                    best_white_move = self._get_best_white_response(
                        board, min_rating, max_rating, time_controls, position_threshold
                    )
                    
                    if best_white_move:
                        white_san, white_move_stats, white_score_details = best_white_move
                        try:
                            white_move = board.parse_san(white_san)
                            board.push(white_move)
                            
                            self.move_count += 1
                            if self.move_count % 10 == 0:
                                print(f"Processed {self.move_count} moves")
                            
                            white_node = RepertoireNode(
                                move=white_san,
                                fen=board.fen(),
                                move_stats=white_move_stats,
                                score_details=white_score_details
                            )
                            
                            child_node.add_child(white_node)
                            white_node.is_mainline = True
                            
                            # Add white node to queue for BFS processing
                            white_board = board.copy()
                            children_to_queue.append((white_node, white_board, current_depth + 2, False))
                            
                            board.pop()
                        except ValueError:
                            pass
                
                board.pop()
                
            except ValueError:
                continue
        
        node.sort_children()
        return children_to_queue
    
    def _get_best_white_response(self, board: chess.Board, min_rating: int, max_rating: int,
                               time_controls: List[str], threshold: float) -> Optional[Tuple[str, MoveStats, float]]:
        position_data = self.lichess_api.get_comprehensive_position_stats(
            board.fen(), min_rating, max_rating, time_controls
        )
        
        if not position_data:
            return None
        
        analyzed_moves = self.move_analyzer.analyze_position(position_data, threshold,
                                                           board.fen(), min_rating,
                                                           max_rating, time_controls)
        return self.move_analyzer.get_best_move(analyzed_moves)


def load_config(config_path: str) -> Dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def load_env_file():
    """Load environment variables from .env file."""
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

def main():
    import sys
    from pgn_generator import PGNGenerator
    
    load_env_file()
    
    # Load configuration (allow custom config file as argument)
    config_file = sys.argv[1] if len(sys.argv) > 1 else 'config.yaml'
    config = load_config(config_file)
    
    # Extract configuration values
    opening = config['opening']['move']
    fen = config['opening']['fen']
    depth = config['analysis']['depth']
    min_rating = config['analysis']['min_rating']
    max_rating = config['analysis']['max_rating']
    time_controls = config['analysis']['time_controls']
    win_rate_weight = config['analysis']['win_rate_weight']
    popularity_weight = config['analysis']['popularity_weight']
    sharpness_weight = config['analysis'].get('sharpness_weight', 0.0)
    initial_threshold = config['analysis']['initial_threshold']
    position_threshold = config['analysis']['position_threshold']
    min_games = config['analysis']['min_games']
    white_win_rate_threshold = config['analysis']['white_win_rate_threshold']
    cache_file = config['api']['cache_file']
    api_key = os.getenv('LICHESS_API_KEY')
    api_delay = config['api']['api_delay']
    output_pgn = config['output']['pgn_file']

    # Validate configuration
    if not opening and not fen:
        raise ValueError("Either opening.move or opening.fen must be provided in config")
    if opening and fen:
        raise ValueError("Cannot specify both opening.move and opening.fen in config")
    
    if fen:
        print(f"Generating repertoire from FEN position for {depth} moves deep...")
    else:
        print(f"Generating {opening} repertoire for {depth} moves deep...")

    print(f"Parameters: depth={depth}, min_rating={min_rating}, max_rating={max_rating}, time_controls={time_controls}")
    print(f"Thresholds: initial={initial_threshold}, position={position_threshold}")
    print(f"Min games: {min_games}, white win rate threshold: {white_win_rate_threshold}")
    print()
    
    # Initialize components
    lichess_api = LichessAPI(cache_file, api_key, api_delay)
    move_analyzer = MoveAnalyzer(win_rate_weight, popularity_weight, sharpness_weight)
    repertoire_builder = RepertoireBuilder(lichess_api, move_analyzer, 
                                         min_games, 
                                         white_win_rate_threshold)
    
    try:
        print("Building repertoire tree...")
        root = repertoire_builder.build_repertoire(
            opening,
            fen,
            depth,
            initial_threshold,
            position_threshold,
            min_rating,
            max_rating,
            time_controls
        )
        
        print("Repertoire built successfully!")
        
        # Generate PGN
        print(f"Generating PGN: {output_pgn}")
        include_comments = config.get('output', {}).get('include_score_comments', True)
        pgn_generator = PGNGenerator(include_score_comments=include_comments)
        title = f"{opening} Repertoire" if opening else "Position Repertoire"
        pgn_content = pgn_generator.generate_pgn(root, title)
        
        with open(output_pgn, 'w') as f:
            f.write(pgn_content)
        print(f"PGN saved to {output_pgn}")
        
        print("\nRepertoire generation completed!")
        
    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == '__main__':
    main()
