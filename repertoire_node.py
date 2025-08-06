from typing import Optional, TYPE_CHECKING
from lichess_api import MoveStats

if TYPE_CHECKING:
    from move_analyzer import ScoreDetails


class RepertoireNode:
    def __init__(self, move: Optional[str] = None, fen: Optional[str] = None, 
                 move_stats: Optional[MoveStats] = None, score_details: Optional['ScoreDetails'] = None):
        self.move = move
        self.fen = fen
        self.move_stats = move_stats
        self.score_details = score_details
        self.children = []
        self.is_mainline = False
        self.termination_reason = None
    
    @property
    def score(self) -> float:
        """Backward compatibility property for accessing total score."""
        return self.score_details.total_score if self.score_details else 0.0
    
    def add_child(self, child_node):
        self.children.append(child_node)
        if not self.children[0].is_mainline and len(self.children) == 1:
            self.children[0].is_mainline = True
    
    def sort_children(self):
        self.children.sort(key=lambda x: x.score, reverse=True)
        if self.children:
            for child in self.children:
                child.is_mainline = False
            self.children[0].is_mainline = True