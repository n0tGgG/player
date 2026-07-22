# Copilot Instructions for Cinema Player Project

## Project Overview

This is a **Terminal User Interface (TUI) media player** built with Python's Textual framework. It's designed as a Spotify-like interface for browsing and controlling media from multiple sources (local files, Netflix, YouTube, Prime Video).

The architecture is simple:
- **main.py**: Entry point that initializes and runs the TUI app
- **tui/**: Modular TUI package using Textual framework (`app.py`, `components.py`, `styles.py`)

### Tech Stack

- **Framework**: Textual (TUI library for Python)
- **Python Version**: 3.x (check exact version during setup)
- **Dependencies**: textual (listed in requirements.txt)

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

## Development Setup

```bash
# Create and activate virtual environment (optional)
python -m venv .venv
.\.venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

## Current Architecture

### Layout System

The TUI uses a CSS Grid layout (4 columns × 10 rows):

1. **Top Bar** (row 1, spans 4 columns)
   - Search input box
   - Help button (shows "Type ?" hint)
   - Settings button (shows "Type Alt+," hint)

2. **Sidebar** (column 1, rows 2-8)
   - Sources list (Local Files, Netflix, YouTube, Prime Video)
   - Categories list (Azione, Commedie, Fantascienza, Anime, Download)

3. **Main Content Area** (columns 2-4, rows 2-8)
   - Displays ASCII art banner, system info, and changelog
   - Scrollable container for future content

4. **Player Bar** (row 9-10, spans 4 columns)
   - Shows playback status and media info
   - Control buttons: Prev, Play/Pause, Next, Stop, Vol-, Vol+

### CSS Styling

The app uses inline CSS with a custom color scheme (One Dark theme):
- Primary accent: `#61afef` (blue)
- Secondary accent: `#c678dd` (purple)
- Tertiary accent: `#56b6c2` (cyan)
- Text highlights: `#e5c07b` (yellow)
- Success: `#98c379` (green)
- Background: black

## Key Conventions

### TUI Component Structure

- All widgets are created in the `compose()` method and organized in containers (Vertical, Horizontal, VerticalScroll)
- Container IDs use kebab-case (#top-bar, #sidebar, #main-content, #player-bar, #controls)
- Widget classes use kebab-case (.list-box, .small-panel, .ascii-art, .info-text)
- Always set `border_title` on containers for visual clarity

### CSS Organization

CSS is organized by section with clear comments:
- Top bar styles
- Sidebar styles
- Main content styles
- Player bar styles
- Individual widget styles

Keep color values consistent with the One Dark palette throughout the codebase.

## Future Development Notes

- Media sources (Netflix, YouTube, etc.) are currently placeholder options
- The mpv engine integration mentioned in logs is not yet implemented
- Button handlers need to be connected via action bindings
- Consider splitting tui.py into multiple modules once it exceeds ~200 lines
