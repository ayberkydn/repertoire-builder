# Chess Repertoire Generator

Generate sophisticated chess opening repertoires using Lichess statistics with advanced move scoring, entropy-based sharpness analysis, and transparent decision making.

## Features

- **Data Source**: Lichess opening explorer API with comprehensive caching
- **Advanced Move Scoring**: Combines expected score, high-rating preference, and entropy-based sharpness
- **Entropy-Based Sharpness**: Uses information theory to identify tactical vs positional moves
- **Transparent Analysis**: Detailed score breakdowns in console output and PGN comments
- **Smart Termination**: Branches terminate based on insufficient games, white advantage, or depth limits
- **Flexible Configuration**: YAML-based configuration with multiple playing styles
- **Clean PGN Output**: Optional score comments with Lichess-compatible formatting

## Directory Structure

```
/repertoire/
├── data/                   # Cache and data files
│   ├── cache.json         # Fixed Lichess API cache location
│   └── README.md          # Data directory documentation
├── output/                # Generated repertoire files
│   ├── *.pgn             # PGN format repertoires
│   └── README.md          # Output directory documentation
├── Core Python Files:
│   ├── repertoire_builder.py  # Main application entry point
│   ├── lichess_api.py         # Lichess API interface and caching
│   ├── move_analyzer.py       # Move scoring with entropy-based sharpness
│   ├── repertoire_node.py     # Tree data structure
│   └── pgn_generator.py       # PGN output with score comments
├── Configuration Files:
│   ├── *.yaml             # Various repertoire configurations
│   └── .env               # API key configuration (optional)
├── Project Files:
│   ├── pyproject.toml     # Python project configuration
│   ├── uv.lock           # Dependency lock file
│   └── README.md          # This documentation
```

## Installation

```bash
# Install dependencies with uv
uv sync
```

## Usage

### YAML Configuration (Recommended)

```bash
# Generate repertoire using YAML configuration
uv run repertoire_builder.py config_custom.yaml
```

### Quick Start Examples

```bash
# Balanced repertoire with entropy-based sharpness
uv run repertoire_builder.py test_entropy_config.yaml

# Tactical repertoire (high sharpness weight)
uv run repertoire_builder.py tactical_test_config.yaml

# Clean PGN without score comments
uv run repertoire_builder.py clean_pgn_config.yaml
```

## Configuration Parameters

### YAML Configuration Structure

```yaml
opening:
  initial_moves: "e4 e5 Nf3"  # Start from a sequence of moves (SAN notation)

analysis:
  depth: 10                      # Maximum depth in moves
  min_rating: 1600              # Minimum player rating
  max_rating: 1600              # Maximum player rating
  time_controls: ["blitz"]      # Time controls to include
  
  # SCORING WEIGHTS (adjust for playing style)
  win_rate_weight: 0.6          # Weight for expected score (0.0-1.0)
  popularity_weight: 0.05       # Weight for high-rating preference (0.0-1.0)
  sharpness_weight: 0.35        # Weight for tactical sharpness (0.0-1.0)
  
  # MOVE FILTERING
  first_move_threshold: 0.05    # Popularity threshold for the 1st move (5%)
  second_move_threshold: 0.10   # Popularity threshold for the 2nd move (10%)
  third_move_threshold: 0.15    # Popularity threshold for the 3rd move (15%)
  other_moves_threshold: 0.20   # Popularity threshold for moves beyond the 3rd (20%)
  
  # QUALITY FILTERS
  min_games: 200               # Minimum games required per position
  white_win_rate_threshold: 0.55  # Minimum win rate to continue line

api:
  # Cache file is fixed at data/cache.json
  # API delay is hardcoded at 0.075 seconds for respectful usage

output:
  pgn_file: "output/repertoire.pgn"     # Output PGN file
  include_score_comments: true          # Include detailed score comments
```

## API Authentication

To avoid rate limiting, you can use a Lichess API key in several ways:

### Method 1: .env File (Recommended)
1. Go to https://lichess.org/account/oauth/token
2. Create a new personal access token
3. Create a `.env` file in the project root:
   ```
   LICHESS_API_KEY=lip_your_token_here
   ```
4. Run commands normally (API key will be loaded automatically)

### Method 2: Command Line
```bash
python repertoire_builder.py --opening e4 --api-key lip_your_token_here
```

### Method 3: Environment Variable
```bash
export LICHESS_API_KEY=lip_your_token_here
python repertoire_builder.py --opening e4
```

**Priority:** Command line > Environment variable > .env file

**Note:** The system always enforces a 0.075 second delay between API requests to be respectful to Lichess servers, regardless of API key usage.

## Advanced Move Scoring

Moves are scored using a sophisticated three-component system:

```
Total Score = (Expected Score × win_rate_weight) + 
              (High Rating Preference × popularity_weight) + 
              (Entropy-Based Sharpness × sharpness_weight)
```

### Scoring Components

1. **Expected Score** = (Wins + 0.5 × Draws) / Total Games
   - Traditional chess scoring based on game results

2. **High Rating Preference** = Popularity among high-rated players vs lower-rated players
   - Identifies moves favored by stronger players

3. **Entropy-Based Sharpness** = 1 - (Shannon Entropy of opponent responses)
   - Uses information theory to measure tactical forcing nature
   - High sharpness = few good opponent replies (tactical)
   - Low sharpness = many good opponent replies (positional)

### Playing Style Configuration

**Positional Style** (solid, drawish):
```yaml
win_rate_weight: 0.8
popularity_weight: 0.15
sharpness_weight: 0.05
```

**Balanced Style**:
```yaml
win_rate_weight: 0.6
popularity_weight: 0.1
sharpness_weight: 0.3
```

**Tactical Style** (sharp, forcing):
```yaml
win_rate_weight: 0.4
popularity_weight: 0.05
sharpness_weight: 0.55
```

## Branch Termination

Branches terminate when:
1. **Max depth reached**: Specified depth limit hit
2. **Insufficient games**: Position has fewer than `min-games` games
3. **White advantage**: No Black response scores above `advantage-threshold`
4. **Low popularity**: No moves meet the popularity threshold

## Output Format

### PGN with Score Comments
```
[Event "Nf3 Repertoire"]
[Site "Generated by Chess Repertoire Generator"]
[Date "????.??.??"]
[Round "?"]
[White "?"]
[Black "?"]
[Result "*"]

1. Nf3 Nc6 { Score: 0.440 [Win: 0.538, Pref: 0.500, Sharp: 0.265] } 
(1... d5 { Score: 0.438 [Win: 0.532, Pref: 0.500, Sharp: 0.267] } 
2. d4 { Score: 0.420 [Win: 0.525, Pref: 0.500, Sharp: 0.227] }) *
```

### Clean PGN (No Comments)
```
1. Nf3 Nc6 (1... d5 2. d4 Nc6 3. c4) 2. d4 d5 3. c4 *
```

### Console Output with Score Breakdown
```
Best move at rnbqkbnr/pppppppp/8/8/8/5N2/PP...: Nc6 - 
Total: 0.440 = Score: 0.538*0.6 + Pref: 0.500*0.05 + Sharp: 0.265*0.35
```

## Cache System

The system maintains a persistent JSON cache at `data/cache.json` for Lichess API responses to:
- Avoid redundant API calls
- Speed up subsequent runs
- Respect API rate limits

Cache keys are generated from position FEN, rating filter, and time controls. The cache file location is fixed and cannot be changed.

## Example Configurations

### Tactical Repertoire (High Sharpness)
```yaml
# tactical_config.yaml
opening:
  initial_moves: "e4"

analysis:
  depth: 8
  min_rating: 1600
  max_rating: 1600
  time_controls: ["blitz"]
  win_rate_weight: 0.4      # Lower emphasis on safety
  popularity_weight: 0.05
  sharpness_weight: 0.55    # High emphasis on tactical sharpness
  first_move_threshold: 0.05
  second_move_threshold: 0.10
  third_move_threshold: 0.15
  other_moves_threshold: 0.15
  min_games: 100
  white_win_rate_threshold: 0.55

output:
  pgn_file: "output/e4_tactical.pgn"
  include_score_comments: true
```

### Positional Repertoire (Low Sharpness)
```yaml
# positional_config.yaml
opening:
  initial_moves: "d4"

analysis:
  depth: 10
  min_rating: 2000
  max_rating: 2000
  time_controls: ["classical", "rapid"]
  win_rate_weight: 0.8      # High emphasis on winning
  popularity_weight: 0.15   # Consider high-rated preferences
  sharpness_weight: 0.05    # Low emphasis on tactics
  first_move_threshold: 0.08
  second_move_threshold: 0.15
  third_move_threshold: 0.20
  other_moves_threshold: 0.20
  min_games: 500
  white_win_rate_threshold: 0.58

output:
  pgn_file: "output/d4_positional.pgn"
  include_score_comments: false  # Clean PGN for study
```

### Usage
```bash
uv run repertoire_builder.py tactical_config.yaml
uv run repertoire_builder.py positional_config.yaml
```

## Key Features Explained

### Entropy-Based Sharpness
The system uses Shannon entropy to measure how "sharp" or forcing a move is:
- **High Sharpness (0.8-1.0)**: Move forces opponent into very few good replies
- **Low Sharpness (0.0-0.4)**: Move allows opponent many good options
- **Calculation**: Based on probability distribution of opponent's responses

### Transparent Decision Making
Every move selection is fully explained:
- Console output shows detailed score breakdowns during generation
- PGN comments include all scoring components and weights
- Users can understand exactly why each move was chosen

### Flexible Configuration
- **YAML-based**: Easy to create and share different repertoire styles
- **Multiple Styles**: Tactical, positional, or balanced approaches
- **Comment Control**: Enable/disable score comments in PGN output
- **Rating Filters**: Target specific player strength ranges

## Requirements

- Python 3.10+
- uv (for dependency management)
- Dependencies: requests, python-chess, pyyaml, chess (installed via `uv sync`)

## Installation & Quick Start

```bash
# Clone and setup
git clone <repository>
cd repertoire
uv sync

# Generate your first repertoire
uv run repertoire_builder.py test_entropy_config.yaml

# View the generated PGN
cat output/nf3_entropy_test.pgn
```